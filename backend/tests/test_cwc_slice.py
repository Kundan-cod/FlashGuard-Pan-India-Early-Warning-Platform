"""CWC/NWIC vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx absent in the portable
sandbox) — that the CWC bridge collector honours every constraint:

  1. A catalog run stores verified NWDP dataset pages into `cwc_resources` with
     stage='CATALOG_ONLY' and NO numeric hydro value (there is no measurement
     column in the catalog schema — none can appear).
  2. A catalog record NEVER enters river_observations / rainfall_observations, so
     it can never masquerade as a numeric water-level/rainfall value ("does not
     invent an undocumented API URL").
  3. Unverified source -> refuses to catalog (ERROR), no invented endpoints.
  4. A successful catalog reports LIVE (verified public NWDP portal, no creds).
  5. An optional dataset-page probe that fails -> honest STALE, but the verified
     catalog rows are still written (dataset pages are verified static metadata).
  6. The pure-Python registry->catalog mapping keeps stage=CATALOG_ONLY, builds
     the dataset_url as the verified NWDP base_url + verified registry path (never
     an invented API endpoint), and copies role/format/frequency verbatim.
  7. Reingest is idempotent on (source, dataset_key, dataset_url).

The collector reads the VENDORED, verified CWC_NWIC_DATASETS registry; tests also
inject a tiny explicit registry to keep assertions deterministic without depending
on the exact vendored contents.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import cwc_mapping as M
from app.collectors.cwc_collector import CwcCollector


def _sample_registry():
    """A deterministic stand-in mirroring the vendored CWC_NWIC_DATASETS shape.
    Unlike GSI, each dataset has a DISTINCT path, so dataset_urls differ per row."""
    return {
        "river_water_level_telemetry_hourly": {
            "path": "/en/dataset/river-water-level-telemetry-hourly-cwc",
            "role": "real_time_hydrological_observation",
            "frequency": "hourly",
            "format": "CSV/API",
        },
        "reservoir_water_storage_manual_daily": {
            "path": "/en/dataset/reservoir-water-level-manual-daily-cwc",
            "role": "reservoir_context",
            "frequency": "daily/manual",
            "format": "CSV/API",
        },
    }


class _FakeClientReachable:
    def fetch_dataset_page(self, path):
        return "<html>NWDP dataset page</html>"


class _FakeClientUnreachable:
    def fetch_dataset_page(self, path):
        raise ConnectionError("simulated: NWDP unreachable")


class CwcSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    # ---- 1 + 2: catalog stores dataset pages, never a hydro value ----
    def test_catalog_stores_datasets_and_never_observations(self):
        c = CwcCollector(verified=True, registry=_sample_registry())
        res = c.run()
        self.assertEqual(res.stored, 2, "expected 2 catalog records")

        rows = repo.cwc_resources_recent()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            self.assertEqual(r["source"], "cwc")
            self.assertTrue(r["dataset_url"], "dataset_url must be present")
            # honesty: the catalog schema has NO numeric hydro column at all.
            self.assertNotIn("water_level", r)
            self.assertNotIn("rainfall_mm", r)

        # The ML feature pipeline reads these — they must stay empty of CWC rows.
        riv = db.query("SELECT COUNT(*) AS n FROM river_observations "
                       "WHERE source='cwc'")
        self.assertEqual(riv[0]["n"], 0,
                         "a catalog record must NEVER reach river_observations")
        rain = db.query("SELECT COUNT(*) AS n FROM rainfall_observations "
                        "WHERE source='cwc'")
        self.assertEqual(rain[0]["n"], 0,
                         "a catalog record must NEVER reach rainfall_observations")

    # ---- 3: unverified source refuses to catalog (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        c = CwcCollector(verified=False, registry=_sample_registry())
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("cwc")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")
        self.assertEqual(len(repo.cwc_resources_recent()), 0)

    # ---- 4: successful catalog reports LIVE (verified public portal, no creds) --
    def test_successful_catalog_reports_live(self):
        c = CwcCollector(verified=True, registry=_sample_registry())
        c.run()
        health = repo.get_source_health("cwc")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("catalog-only" in n for n in c._stage_notes),
                        f"expected a catalog-only parse note; got {c._stage_notes}")

    # ---- 4b: pure catalog with no probe also LIVE and reads vendored registry ----
    def test_pure_catalog_uses_vendored_registry(self):
        c = CwcCollector(verified=True)  # no registry override -> vendored
        res = c.run()
        self.assertGreater(res.stored, 0,
                           "vendored CWC_NWIC_DATASETS should yield catalog rows")
        self.assertEqual(repo.get_source_health("cwc")["status"], "LIVE")
        rows = repo.cwc_resources_recent(limit=100)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            # every dataset_url must be a verified nwdp.nwic.gov.in host.
            self.assertIn("nwdp.nwic.gov.in", r["dataset_url"])

    # ---- 5a: reachable probe keeps LIVE ----
    def test_reachable_probe_keeps_live(self):
        c = CwcCollector(verified=True, registry=_sample_registry(),
                         client=_FakeClientReachable())
        res = c.run()
        self.assertEqual(res.stored, 2)
        self.assertEqual(repo.get_source_health("cwc")["status"], "LIVE")
        self.assertTrue(any("reachable" in n for n in c._stage_notes))

    # ---- 5b: failed probe -> STALE, but verified catalog rows still written ----
    def test_unreachable_probe_is_stale_but_catalog_written(self):
        c = CwcCollector(verified=True, registry=_sample_registry(),
                         client=_FakeClientUnreachable())
        res = c.run()
        self.assertEqual(res.stored, 2,
                         "verified catalog rows are written even if probe fails")
        health = repo.get_source_health("cwc")
        self.assertEqual(health["status"], "STALE")
        self.assertIsNone(health["last_success_at"],
                          "STALE (unreachable) is not a full success")
        self.assertTrue(any("unreachable" in n for n in c._stage_notes))

    # ---- 6: mapping keeps CATALOG_ONLY, builds dataset_url, copies fields verbatim
    def test_mapping_builds_url_and_catalog_only(self):
        rec = M.registry_entry_to_catalog_record(
            "river_water_level_telemetry_hourly",
            _sample_registry()["river_water_level_telemetry_hourly"],
            base_url="https://www.nwdp.nwic.gov.in",
            retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)
        self.assertEqual(rec["dataset_key"], "river_water_level_telemetry_hourly")
        self.assertEqual(rec["role"], "real_time_hydrological_observation")
        # dataset_url = verified base_url + verified path (never an invented API).
        self.assertEqual(
            rec["dataset_url"],
            "https://www.nwdp.nwic.gov.in/en/dataset/"
            "river-water-level-telemetry-hourly-cwc")
        self.assertEqual(rec["resource_format"], "CSV/API")
        self.assertEqual(rec["frequency"], "hourly")
        self.assertNotIn("water_level_m", rec)

    def test_mapping_default_base_url(self):
        # Default base_url is the verified vendored NWDP portal.
        rec = M.registry_entry_to_catalog_record(
            "reservoir_water_storage_manual_daily",
            _sample_registry()["reservoir_water_storage_manual_daily"])
        self.assertTrue(rec["dataset_url"].startswith(
            "https://www.nwdp.nwic.gov.in"))
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)

    # ---- 7: reingest is idempotent on (source, dataset_key, dataset_url) ----
    def test_reingest_is_idempotent(self):
        reg = _sample_registry()
        CwcCollector(verified=True, registry=reg).run()
        CwcCollector(verified=True, registry=reg).run()
        self.assertEqual(len(repo.cwc_resources_recent()), 2,
                         "re-cataloging the same datasets must not duplicate rows")


if __name__ == "__main__":
    unittest.main()
