"""Demo model inference behaviour (master prompt sections 16, 35, 68).

These do NOT assert scientific accuracy (the models are unvalidated demos).
They assert the *structural* properties the architecture guarantees:
  - monotonicity (more rain => higher flood probability),
  - landslide risk is GATED by a rainfall/soil trigger (dry steep slope is low),
  - missing features contribute 0 (absence is not faked to a neutral value),
  - contributions are returned sorted for explainability.
"""
import unittest
from _util import bootstrap
bootstrap()

from app.models.demo_models import FloodDemoModel, LandslideDemoModel


class TestFloodModel(unittest.TestCase):
    def setUp(self):
        self.m = FloodDemoModel()

    def test_prob_in_range(self):
        p = self.m.predict({}).probability
        self.assertTrue(0.0 <= p <= 1.0)

    def test_monotonic_in_rain(self):
        low = self.m.predict({"rain_3h": 5}).probability
        high = self.m.predict({"rain_3h": 110}).probability
        self.assertGreater(high, low)

    def test_missing_feature_contributes_zero(self):
        # a feature that's absent must not appear in contributions at all
        contribs = self.m.predict({"rain_3h": 40}).contributions
        feats = {c["feature"] for c in contribs}
        self.assertIn("rain_3h", feats)
        self.assertNotIn("river_level", feats)  # not supplied => omitted, not zero-faked

    def test_contributions_sorted_desc(self):
        contribs = self.m.predict({"rain_3h": 100, "soil_saturation_index": 0.9,
                                   "river_level": 8}).contributions
        vals = [c["contribution"] for c in contribs]
        self.assertEqual(vals, sorted(vals, reverse=True))

    def test_not_validated(self):
        self.assertFalse(self.m.validated)
        self.assertTrue(self.m.is_demo())


class TestLandslideModel(unittest.TestCase):
    def setUp(self):
        self.m = LandslideDemoModel()

    def test_dry_steep_slope_is_low(self):
        # high predisposition, NO trigger => gated down to low risk
        dry = self.m.predict({"slope": 55, "susceptibility": 0.9,
                              "relative_relief": 1200}).probability
        self.assertLess(dry, 0.35, f"dry steep slope should be low, got {dry}")

    def test_trigger_raises_risk(self):
        base = {"slope": 55, "susceptibility": 0.9, "relative_relief": 1200}
        dry = self.m.predict(base).probability
        wet = self.m.predict({**base, "rain_24h": 250, "rain_3h": 100,
                              "soil_saturation_index": 0.95}).probability
        self.assertGreater(wet, dry)

    def test_flat_ground_stays_low_even_wet(self):
        # low predisposition even with heavy rain shouldn't be extreme
        p = self.m.predict({"slope": 2, "susceptibility": 0.05,
                            "relative_relief": 50, "rain_24h": 250,
                            "rain_3h": 100, "soil_saturation_index": 0.95}).probability
        self.assertLess(p, 0.6, f"flat ground should stay moderate-ish, got {p}")

    def test_prob_in_range(self):
        p = self.m.predict({"slope": 40, "susceptibility": 0.7,
                            "rain_3h": 90}).probability
        self.assertTrue(0.0 <= p <= 1.0)


if __name__ == "__main__":
    unittest.main()
