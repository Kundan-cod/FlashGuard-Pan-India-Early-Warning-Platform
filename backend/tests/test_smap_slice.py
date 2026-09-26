"""SMAP vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx/pydantic absent in the
portable sandbox) — that the SMAP bridge collector honours every constraint:

  1. A discovery run stores CMR granule metadata into `smap_discovery` with
     surface_sm=NULL, rootzone_sm=NULL and stage='DISCOVERY_ONLY'.
  2. A discovery record NEVER enters soil_moisture_observations, so it can never
     masquerade as a soil-moisture number in the ML feature pipeline.
  3. No token -> honest NOT_CONFIGURED health status (one of the unchanged 7
     states), NOT an error, and NO rows written -> replay stays untouched.
  3b. A placeholder token (your_token_here, changeme, ...) counts as NOT
      configured — no doomed authenticated request, no ERROR.
  3c. A genuine-looking token IS honoured (guards against over-filtering).
  4. Unverified source -> refuses to fetch (ERROR), no invented endpoints.
  5. Successful discovery reports NRT; there is NO raster/HDF5 parse stage, so
     no soil-moisture value is ever produced (discovery-only, honestly).
  6. The pure-Python CMR-granule->discovery mapping keeps surface_sm/rootzone_sm
     = None.

The discovery adapter is injected as a tiny fake exposing `.search_granules(**kw)`,
mirroring the vendored SmapCollector's interface, so the honesty-critical logic is
provable in-sandbox (the vendored collector imports httpx at module load).
"""
import os
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import smap_mapping as M
from app.collectors.smap_collector import SmapCollector


# A minimal, realistic CMR granule (plain-dict shape the bridge produces from a
# vendored SmapGranule): concept id, producer granule id, temporal window, and a
# documented GET DATA URL.
def _sample_granules():
    return [
        {
            "concept_id": "G1234567890-NSIDC_CPRD",
            "producer_granule_id": "SMAP_L4_SM_aup_20240801T013000_Vv8010_001.h5",
            "title": "SPL4SMAU V008 granule 20240801",
            "start_time": "2024-08-01T01:30:00Z",
            "end_time": "2024-08-01T04:30:00Z",
            "downloadable_urls": [
                "https://n5eil01u.ecs.nsidc.org/DP4/SMAP/SPL4SMAU.008/"
                "SMAP_L4_SM_aup_20240801T013000_Vv8010_001.h5",
            ],
        }
    ]


class _FakeDiscovery:
    """Stand-in for the vendored SmapCollector: returns canned granules and
    records the search kwargs. No network, no httpx, no pydantic."""
    def __init__(self, granules):
        self._granules = granules
        self.calls = []

    def search_granules(self, **kwargs):
        self.calls.append(kwargs)
        return self._granules


class SmapSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)
        os.environ.pop("EARTHDATA_TOKEN", None)

    def tearDown(self):
        os.environ.pop("EARTHDATA_TOKEN", None)

    # ---- 1 + 2: discovery stores metadata, never soil moisture ----
    def test_discovery_stores_metadata_and_never_soil_moisture(self):
        os.environ["EARTHDATA_TOKEN"] = "test-token"
        c = SmapCollector(verified=True,
                          discovery=_FakeDiscovery(_sample_granules()))
        res = c.run()
        self.assertEqual(res.stored, 1, "one discovery record expected")

        disc = repo.smap_discovery_recent()
        self.assertEqual(len(disc), 1)
        rec = disc[0]
        self.assertIsNone(rec["surface_sm"],
                          "discovery record must carry NO surface soil-moisture value")
        self.assertIsNone(rec["rootzone_sm"],
                          "discovery record must carry NO root-zone soil-moisture value")
        self.assertEqual(rec["stage"], "DISCOVERY_ONLY")
        self.assertEqual(rec["concept_id"], "G1234567890-NSIDC_CPRD")
        self.assertTrue(rec["download_url"].endswith("_001.h5"))

        # The feature pipeline reads soil_moisture_observations — it must stay empty.
        soil = db.query("SELECT COUNT(*) AS n FROM soil_moisture_observations")
        self.assertEqual(soil[0]["n"], 0,
                         "a discovery record must NEVER reach soil_moisture_observations")

    # ---- 3: no token -> NOT_CONFIGURED, no rows, replay untouched ----
    def test_no_token_is_not_configured_not_error(self):
        c = SmapCollector(verified=True,
                          discovery=_FakeDiscovery(_sample_granules()))
        res = c.run()
        self.assertEqual(res.stored, 0)

        health = repo.get_source_health("smap")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "NOT_CONFIGURED")
        self.assertIsNone(health["last_success_at"],
                          "NOT_CONFIGURED is not a success")
        self.assertEqual(len(repo.smap_discovery_recent()), 0)
        self.assertEqual(
            db.query("SELECT COUNT(*) AS n FROM soil_moisture_observations")[0]["n"], 0)

    # ---- 3b: placeholder token counts as NOT configured (honest, no ERROR) ----
    def test_placeholder_token_is_not_configured(self):
        for placeholder in ("your_token_here", "changeme", "CHANGEME",
                            "  ", "placeholder", "<token>", "TODO",
                            "earthdata_token"):
            with self.subTest(placeholder=placeholder):
                db.init_db(reset=True)
                os.environ["EARTHDATA_TOKEN"] = placeholder
                c = SmapCollector(verified=True,
                                  discovery=_FakeDiscovery(_sample_granules()))
                self.assertFalse(c.has_token(),
                                 f"'{placeholder}' must not count as a token")
                res = c.run()
                self.assertEqual(res.stored, 0)
                health = repo.get_source_health("smap")
                self.assertEqual(health["status"], "NOT_CONFIGURED",
                                 f"'{placeholder}' should yield NOT_CONFIGURED")
                self.assertEqual(len(repo.smap_discovery_recent()), 0)

    # ---- 3c: a genuine-looking token IS honoured (guards against over-filtering) ----
    def test_real_looking_token_is_honoured(self):
        os.environ["EARTHDATA_TOKEN"] = "eyJ0eXAiOiabc123.realish.TOKEN-value"
        c = SmapCollector(verified=True,
                          discovery=_FakeDiscovery(_sample_granules()))
        self.assertTrue(c.has_token(), "a real-looking token must be accepted")
        res = c.run()
        self.assertEqual(res.stored, 1)
        self.assertEqual(repo.get_source_health("smap")["status"], "NRT")

    # ---- 4: unverified source refuses to fetch (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        os.environ["EARTHDATA_TOKEN"] = "test-token"
        c = SmapCollector(verified=False,
                          discovery=_FakeDiscovery(_sample_granules()))
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("smap")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")

    # ---- 5: successful discovery reports NRT; no parse stage, no measurement ----
    def test_successful_discovery_reports_nrt_and_no_parse_stage(self):
        os.environ["EARTHDATA_TOKEN"] = "test-token"
        c = SmapCollector(verified=True,
                          discovery=_FakeDiscovery(_sample_granules()))
        c.run()
        health = repo.get_source_health("smap")
        self.assertEqual(health["status"], "NRT")
        self.assertIsNotNone(health["last_success_at"])
        # A per-stage note must record that the parse stage was skipped (there is
        # no verified HDF5/NetCDF parser — discovery-only).
        self.assertTrue(any("parse" in n and "discovery-only" in n
                            for n in c._stage_notes),
                        f"expected a discovery-only parse note; got {c._stage_notes}")
        # Still zero soil-moisture rows after a *successful* run.
        self.assertEqual(
            db.query("SELECT COUNT(*) AS n FROM soil_moisture_observations")[0]["n"], 0)

    # ---- 6: pure-Python mapping keeps surface_sm/rootzone_sm=None ----
    def test_mapping_invariant_soil_moisture_is_none(self):
        recs = M.granules_to_discovery_records(
            _sample_granules(), version="008", grid="9 km EASE-Grid",
            retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(len(recs), 1)
        self.assertIsNone(recs[0]["surface_sm"])
        self.assertIsNone(recs[0]["rootzone_sm"])
        self.assertEqual(recs[0]["stage"], M.DISCOVERY_ONLY)
        self.assertEqual(recs[0]["quality_flag"], "UNKNOWN")

    # ---- granule with no download URL still yields a (non-measurement) record ----
    def test_granule_without_download_still_discovered(self):
        granules = _sample_granules()
        granules[0]["downloadable_urls"] = []  # no GET DATA URL
        os.environ["EARTHDATA_TOKEN"] = "test-token"
        c = SmapCollector(verified=True,
                          discovery=_FakeDiscovery(granules))
        res = c.run()
        self.assertEqual(res.stored, 1)
        rec = repo.smap_discovery_recent()[0]
        self.assertIsNone(rec["download_url"])
        self.assertIsNone(rec["surface_sm"])
        self.assertIsNone(rec["rootzone_sm"])

    # ---- multiple GET DATA URLs -> one discovery record each ----
    def test_multiple_urls_yield_multiple_records(self):
        granules = _sample_granules()
        granules[0]["downloadable_urls"] = [
            "https://example.invalid/a.h5",
            "https://example.invalid/b.h5",
        ]
        os.environ["EARTHDATA_TOKEN"] = "test-token"
        c = SmapCollector(verified=True, discovery=_FakeDiscovery(granules))
        res = c.run()
        self.assertEqual(res.stored, 2)
        for rec in repo.smap_discovery_recent():
            self.assertIsNone(rec["surface_sm"])
            self.assertIsNone(rec["rootzone_sm"])
            self.assertEqual(rec["stage"], "DISCOVERY_ONLY")


if __name__ == "__main__":
    unittest.main()
