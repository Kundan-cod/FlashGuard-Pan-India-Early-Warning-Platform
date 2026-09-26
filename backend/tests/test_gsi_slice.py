"""GSI/Bhusanket vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx absent in the portable
sandbox) — that the GSI bridge collector honours every constraint:

  1. A catalog run stores verified portal layer endpoints into `gsi_layers` with
     stage='CATALOG_ONLY' and NO numeric landslide value (there is no measurement
     column in the catalog schema — none can appear).
  2. A catalog record NEVER enters landslide_data, so it can never masquerade as
     a numeric susceptibility/probability in the ML landslide pipeline ("does not
     hard-code an undocumented JSON API").
  3. Unverified source -> refuses to catalog (ERROR), no invented endpoints.
  4. A successful catalog reports LIVE (verified public portal, no creds).
  5. An optional portal probe that fails -> honest STALE, but the verified catalog
     rows are still written (portal layers are verified static metadata).
  6. The pure-Python registry->catalog mapping keeps stage=CATALOG_ONLY, copies
     the service_url verbatim, and PRESERVES the verified geographic_scope COVERAGE
     note (GSI forecasting is REGIONAL, not nationwide).
  7. Reingest is idempotent on (source, layer_key, service_url).

The collector reads the VENDORED, verified GSI_LAYERS registry; tests also inject
a tiny explicit registry to keep assertions deterministic without depending on the
exact vendored contents.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import gsi_mapping as M
from app.collectors.gsi_collector import GsiCollector


def _sample_registry():
    """A deterministic stand-in mirroring the vendored GSI_LAYERS shape. Note the
    verified registry deliberately uses the SAME portal url for every layer, so
    the natural key that keeps rows distinct is layer_key (the app must never
    invent per-layer URLs)."""
    return {
        "lsm_10k": {
            "role": "susceptibility",
            "url": "https://bhusanket.gsi.gov.in/",
            "geographic_scope": "mapped areas; not assumed nationwide",
        },
        "forecast_bulletin": {
            "role": "forecast_bulletin",
            "url": "https://bhusanket.gsi.gov.in/",
            "geographic_scope": "regional operational/experimental coverage",
        },
    }


class _FakeClientReachable:
    def fetch_portal(self):
        return "<html>Bhusanket portal</html>"


class _FakeClientUnreachable:
    def fetch_portal(self):
        raise ConnectionError("simulated: portal unreachable")


class GsiSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    # ---- 1 + 2: catalog stores endpoints, never a landslide value ----
    def test_catalog_stores_endpoints_and_never_landslide(self):
        c = GsiCollector(verified=True, registry=_sample_registry())
        res = c.run()
        # One catalog row per registry entry; two entries -> two rows (distinct
        # layer_key even though they share the verified portal url).
        self.assertEqual(res.stored, 2, "expected 2 catalog records")

        rows = repo.gsi_layers_recent()
        self.assertEqual(len(rows), 2)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")
            self.assertEqual(r["source"], "gsi")
            self.assertTrue(r["service_url"], "service_url must be present")
            # Verified regional COVERAGE note preserved (not fabricated away).
            self.assertTrue(r["geographic_scope"],
                            "geographic_scope coverage note must be preserved")
            # honesty: the catalog schema has NO numeric landslide column at all.
            self.assertNotIn("susceptibility", r)
            self.assertNotIn("impact_probability", r)

        # The landslide ML pipeline reads landslide_data — it must stay empty.
        ls = db.query("SELECT COUNT(*) AS n FROM landslide_data")
        self.assertEqual(ls[0]["n"], 0,
                         "a catalog record must NEVER reach landslide_data")

    # ---- 3: unverified source refuses to catalog (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        c = GsiCollector(verified=False, registry=_sample_registry())
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("gsi")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")
        self.assertEqual(len(repo.gsi_layers_recent()), 0)

    # ---- 4: successful catalog reports LIVE (verified public portal, no creds) ----
    def test_successful_catalog_reports_live(self):
        c = GsiCollector(verified=True, registry=_sample_registry())
        c.run()
        health = repo.get_source_health("gsi")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("catalog-only" in n for n in c._stage_notes),
                        f"expected a catalog-only parse note; got {c._stage_notes}")

    # ---- 4b: pure catalog with no probe also LIVE and reads vendored registry ----
    def test_pure_catalog_uses_vendored_registry(self):
        c = GsiCollector(verified=True)  # no registry override -> vendored
        res = c.run()
        self.assertGreater(res.stored, 0,
                           "vendored GSI_LAYERS should yield catalog rows")
        self.assertEqual(repo.get_source_health("gsi")["status"], "LIVE")
        rows = repo.gsi_layers_recent(limit=100)
        for r in rows:
            self.assertEqual(r["stage"], "CATALOG_ONLY")

    # ---- 5a: reachable probe keeps LIVE ----
    def test_reachable_probe_keeps_live(self):
        c = GsiCollector(verified=True, registry=_sample_registry(),
                         client=_FakeClientReachable())
        res = c.run()
        self.assertEqual(res.stored, 2)
        self.assertEqual(repo.get_source_health("gsi")["status"], "LIVE")
        self.assertTrue(any("reachable" in n for n in c._stage_notes))

    # ---- 5b: failed probe -> STALE, but verified catalog rows still written ----
    def test_unreachable_probe_is_stale_but_catalog_written(self):
        c = GsiCollector(verified=True, registry=_sample_registry(),
                         client=_FakeClientUnreachable())
        res = c.run()
        self.assertEqual(res.stored, 2,
                         "verified catalog rows are written even if probe fails")
        health = repo.get_source_health("gsi")
        self.assertEqual(health["status"], "STALE")
        self.assertIsNone(health["last_success_at"],
                          "STALE (unreachable) is not a full success")
        self.assertTrue(any("unreachable" in n for n in c._stage_notes))

    # ---- 6: mapping keeps CATALOG_ONLY, url verbatim, preserves coverage note ----
    def test_mapping_preserves_coverage_and_catalog_only(self):
        rec = M.registry_entry_to_catalog_record(
            "lsm_10k", _sample_registry()["lsm_10k"],
            retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(rec["stage"], M.CATALOG_ONLY)
        self.assertEqual(rec["layer_key"], "lsm_10k")
        self.assertEqual(rec["role"], "susceptibility")
        # service_url copied verbatim from the verified registry.
        self.assertEqual(rec["service_url"], "https://bhusanket.gsi.gov.in/")
        # verified regional COVERAGE note preserved verbatim.
        self.assertEqual(rec["geographic_scope"],
                         "mapped areas; not assumed nationwide")
        self.assertNotIn("numeric_value", rec)

    # ---- 7: reingest is idempotent on (source, layer_key, service_url) ----
    def test_reingest_is_idempotent(self):
        reg = _sample_registry()
        GsiCollector(verified=True, registry=reg).run()
        GsiCollector(verified=True, registry=reg).run()
        self.assertEqual(len(repo.gsi_layers_recent()), 2,
                         "re-cataloging the same layers must not duplicate rows")


if __name__ == "__main__":
    unittest.main()
