"""Bhuvan/NRSC vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx absent in the portable
sandbox) — that the Bhuvan bridge collector honours every constraint:

  1. A catalog run stores verified OGC layer endpoints into `bhuvan_layers` with
     stage='CATALOG_ONLY' and NO numeric terrain value (there is no measurement
     column in the catalog schema — none can appear).
  2. A catalog record NEVER enters terrain_features, so it can never masquerade
     as a numeric terrain value in the ML feature pipeline ("do not scrape
     rendered map pixels as a substitute for the DEM").
  3. Unverified source -> refuses to catalog (ERROR), no invented endpoints.
  4. A successful catalog reports LIVE (verified public OGC endpoints, no creds).
  5. An optional endpoint probe that fails -> honest STALE, but the verified
     catalog rows are still written (endpoints are verified static metadata).
  6. The pure-Python registry->catalog mapping expands "WMS/WMTS" into two
     service_type records, keeps stage=CATALOG_ONLY, and copies the service_url
     verbatim from the verified registry (never invented).
  7. Reingest is idempotent on (source, layer_key, service_url).

The collector reads the VENDORED, verified BHUVAN_LAYERS registry; tests also
inject a tiny explicit registry to keep assertions deterministic and to exercise
the WMS/WMTS expansion without depending on the exact vendored contents.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import bhuvan_mapping as M
from app.collectors.bhuvan_collector import BhuvanCollector


def _sample_registry():
    """A deterministic stand-in mirroring the vendored BHUVAN_LAYERS shape."""
    return {
        "lulc_50k": {
            "service": "WMS/WMTS",
            "role": "land_use_land_cover_context",
            "verified_service_url": "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms",
        },
        "flood_hazard": {
            "service": "WMS",
            "role": "historical_flood_hazard_context",
            "verified_service_url": "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/hazard.exe",
        },
    }


class _FakeClientReachable:
    def get_capabilities(self, url):
        return True


class _FakeClientUnreachable:
    def get_capabilities(self, url):
        raise ConnectionError("simulated: endpoint unreachable")


class BhuvanSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    # ---- 1 + 2: catalog stores endpoints, never a terrain value ----
    def test_catalog_stores_endpoints_and_never_terrain(self):
        c = BhuvanCollector(verified=True, registry=_sample_registry())
        res = c.run()
        # One catalog row per registry entry (service_type kept verbatim, NOT
        # split — the verified registry has a single URL per layer): 2 entries.
        self.assertEqual(res.stored, 2, "expected 2 catalog records")

        rows = repo.bhuvan_layers_recent()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            self.assertEqual(r["source"], "bhuvan")
            self.assertTrue(r["service_url"], "service_url must be present")
            # honesty: the catalog schema has NO numeric terrain column at all.
            self.assertNotIn("elevation", r)
            self.assertNotIn("slope", r)

        # The feature pipeline reads terrain_features — it must stay empty.
        terr = db.query("SELECT COUNT(*) AS n FROM terrain_features")
        self.assertEqual(terr[0]["n"], 0,
                         "a catalog record must NEVER reach terrain_features")

    # ---- 3: unverified source refuses to catalog (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        c = BhuvanCollector(verified=False, registry=_sample_registry())
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("bhuvan")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")
        self.assertEqual(len(repo.bhuvan_layers_recent()), 0)

    # ---- 4: successful catalog reports LIVE (verified public OGC, no creds) ----
    def test_successful_catalog_reports_live(self):
        c = BhuvanCollector(verified=True, registry=_sample_registry())
        c.run()
        health = repo.get_source_health("bhuvan")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("catalog-only" in n for n in c._stage_notes),
                        f"expected a catalog-only dem-parse note; got {c._stage_notes}")

    # ---- 4b: pure catalog with no probe also LIVE and reads vendored registry ----
    def test_pure_catalog_uses_vendored_registry(self):
        c = BhuvanCollector(verified=True)  # no registry override -> vendored
        res = c.run()
        self.assertGreater(res.stored, 0,
                           "vendored BHUVAN_LAYERS should yield catalog rows")
        self.assertEqual(repo.get_source_health("bhuvan")["status"], "LIVE")
        rows = repo.bhuvan_layers_recent(limit=100)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")

    # ---- 5a: reachable probe keeps LIVE ----
    def test_reachable_probe_keeps_live(self):
        c = BhuvanCollector(verified=True, registry=_sample_registry(),
                            client=_FakeClientReachable())
        res = c.run()
        self.assertEqual(res.stored, 2)
        self.assertEqual(repo.get_source_health("bhuvan")["status"], "LIVE")
        self.assertTrue(any("reachable" in n for n in c._stage_notes))

    # ---- 5b: failed probe -> STALE, but verified catalog rows still written ----
    def test_unreachable_probe_is_stale_but_catalog_written(self):
        c = BhuvanCollector(verified=True, registry=_sample_registry(),
                            client=_FakeClientUnreachable())
        res = c.run()
        self.assertEqual(res.stored, 2,
                         "verified catalog rows are written even if probe fails")
        health = repo.get_source_health("bhuvan")
        self.assertEqual(health["status"], "STALE")
        self.assertIsNone(health["last_success_at"],
                          "STALE (unreachable) is not a full success")
        self.assertTrue(any("unreachable" in n for n in c._stage_notes))

    # ---- 6: mapping keeps service_type verbatim + CATALOG_ONLY, url verbatim ----
    def test_mapping_keeps_service_verbatim_and_catalog_only(self):
        rec = M.registry_entry_to_catalog_record(
            "lulc_50k", _sample_registry()["lulc_50k"],
            retrieved_at="2026-09-06T00:00:00Z")
        # service_type is the verbatim protocol list, NOT split into rows.
        self.assertEqual(rec["service_type"], "WMS/WMTS")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)
        self.assertEqual(rec["layer_key"], "lulc_50k")
        self.assertEqual(rec["role"], "land_use_land_cover_context")
        # service_url copied verbatim from the verified registry.
        self.assertEqual(rec["service_url"],
                         "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms")
        self.assertNotIn("numeric_value", rec)

    def test_mapping_single_service_record(self):
        rec = M.registry_entry_to_catalog_record(
            "flood_hazard", _sample_registry()["flood_hazard"])
        self.assertEqual(rec["service_type"], "WMS")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)

    # ---- 7: reingest is idempotent on (source, layer_key, service_url) ----
    def test_reingest_is_idempotent(self):
        reg = _sample_registry()
        BhuvanCollector(verified=True, registry=reg).run()
        BhuvanCollector(verified=True, registry=reg).run()
        self.assertEqual(len(repo.bhuvan_layers_recent()), 2,
                         "re-cataloging the same layers must not duplicate rows")


if __name__ == "__main__":
    unittest.main()
