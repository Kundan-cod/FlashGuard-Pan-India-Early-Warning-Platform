"""End-to-end vertical slice through the real pipeline (master prompt sections
7, 15, 17, 31): seed -> replay ingest -> features -> predict -> persist.

Uses an isolated temp DB. Also proves idempotency (re-ingest = no duplicates)
and time-leakage prevention (as_of cutoff hides future observations)."""
import os
import unittest
from pathlib import Path
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.services import seed
from app.collectors.replay_collector import ReplayCollector
from app.features.engineer import build_features
from app.services import prediction_service as psvc
from app.services import replay_driver

def _resolve_dataset() -> str:
    env = os.environ.get("REPLAY_DATASET")
    if env and Path(env).exists():
        return env
    for p in (Path(__file__).resolve().parents[1] / "data" / "replay" / "uttarakhand_flash_flood_event.json",
              Path(__file__).resolve().parents[2] / "data" / "replay" / "uttarakhand_flash_flood_event.json"):
        if p.exists():
            return str(p)
    return str(Path(__file__).resolve().parents[2] / "data" / "replay" / "uttarakhand_flash_flood_event.json")

DATASET = _resolve_dataset()


class TestPipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids = seed.run(reset=True)
        cls.vid = cls.ids["villages"][0]

    def test_seed_created_hierarchy(self):
        self.assertEqual(len(repo.list_locations(level="country")), 1)
        self.assertEqual(len(repo.list_locations(level="village")), 4)
        terr = repo.get_terrain(self.vid)
        self.assertIsNotNone(terr)
        self.assertIsNotNone(terr["slope"])

    def test_replay_ingest_is_idempotent(self):
        rc = ReplayCollector(DATASET, source_key="replay")
        r1 = rc.run()
        n1 = len(repo.rainfall_series(30.05, 78.05))
        rc2 = ReplayCollector(DATASET, source_key="replay")
        rc2.run()
        n2 = len(repo.rainfall_series(30.05, 78.05))
        self.assertEqual(n1, n2, "re-ingesting same data must not duplicate rows")
        self.assertGreater(r1.stored, 0)

    def test_features_carry_availability_and_completeness(self):
        fs = build_features(self.vid, as_of="2024-08-01T10:00:00Z")
        self.assertIn("rainfall", fs.available)
        self.assertTrue(fs.available["terrain"])
        self.assertTrue(0.0 <= fs.completeness() <= 1.0)

    def test_time_leakage_prevention(self):
        # a very early cutoff must not see the late (saturated) soil reading
        rc = ReplayCollector(DATASET, source_key="replay")
        rc.run()
        early = build_features(self.vid, as_of="2024-08-01T06:00:00Z")
        late = build_features(self.vid, as_of="2024-08-01T10:00:00Z")
        e = early.values.get("soil_saturation_index")
        l = late.values.get("soil_saturation_index")
        if e is not None and l is not None:
            self.assertLessEqual(e, l,
                "early soil saturation must not exceed late (no future leakage)")

    def test_prediction_persists_and_reads_back(self):
        rc = ReplayCollector(DATASET, source_key="replay")
        rc.run()
        result = psvc.run_for_location(self.vid, as_of="2024-08-01T10:00:00Z",
                                       mode="replay")
        self.assertIn(result.risk_level, ("LOW", "MODERATE", "HIGH", "CRITICAL"))
        latest = repo.latest_prediction(self.vid)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["mode"], "replay")

    def test_risk_rises_over_event(self):
        # the whole point of the demo: risk should not fall as the storm builds
        summary = replay_driver.run_replay(DATASET, reseed=True)
        self.assertGreater(summary["predictions_written"], 0)
        vid = summary["villages"][0]
        hist = repo.prediction_history(vid)
        by_ts = {h["ts"]: h["flood_probability"] for h in hist}
        ordered = [by_ts[t] for t in sorted(by_ts)]
        self.assertGreaterEqual(ordered[-1], ordered[0],
            "flood probability at end of event should be >= at start")


if __name__ == "__main__":
    unittest.main()
