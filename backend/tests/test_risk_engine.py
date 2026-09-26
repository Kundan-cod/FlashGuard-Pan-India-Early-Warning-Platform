"""Risk engine fusion: bands, physical-rule floors, confidence separation,
lead-time window (master prompt sections 18-21, 35, 47, 48)."""
import unittest
from _util import bootstrap
bootstrap()

from app.features.engineer import FeatureSet
from app.risk import engine


def _fs(values, available=None):
    av = available or {k: True for k in ("rainfall", "soil", "river",
                                         "terrain", "susceptibility")}
    prov = {k: {"quality": "GOOD"} for k, ok in av.items() if ok}
    return FeatureSet(location_id=1, values=values, available=av,
                      provenance=prov, as_of="2024-08-01T09:00:00Z")


class TestBands(unittest.TestCase):
    def test_band_thresholds(self):
        self.assertEqual(engine._band(0.9), "CRITICAL")
        self.assertEqual(engine._band(0.6), "HIGH")
        self.assertEqual(engine._band(0.4), "MODERATE")
        self.assertEqual(engine._band(0.1), "LOW")


class TestRuleFloors(unittest.TestCase):
    def test_two_extremes_cannot_be_low(self):
        # rain 3h extreme + soil saturated, but pretend base level is LOW
        level, reasons = engine._apply_rules(
            _fs({"rain_3h": 100, "soil_saturation_index": 0.9,
                 "river_rate_of_rise_1h": 0.0}), "LOW")
        self.assertIn(level, ("HIGH", "CRITICAL"))
        self.assertGreaterEqual(len(reasons), 2)

    def test_three_extremes_floor_critical(self):
        level, _ = engine._apply_rules(
            _fs({"rain_3h": 100, "soil_saturation_index": 0.9,
                 "river_rate_of_rise_1h": 1.0}), "LOW")
        self.assertEqual(level, "CRITICAL")

    def test_one_extreme_does_not_floor(self):
        level, _ = engine._apply_rules(
            _fs({"rain_3h": 100, "soil_saturation_index": 0.1,
                 "river_rate_of_rise_1h": 0.0}), "LOW")
        self.assertEqual(level, "LOW")


class TestConfidence(unittest.TestCase):
    def test_confidence_scales_with_completeness(self):
        full = _fs({}, {k: True for k in
                        ("rainfall", "soil", "river", "terrain", "susceptibility")})
        partial = _fs({}, {"rainfall": True, "soil": False, "river": False,
                           "terrain": False, "susceptibility": False})
        c_full, _ = engine._confidence(full)
        c_part, _ = engine._confidence(partial)
        self.assertGreater(c_full, c_part)

    def test_confidence_independent_of_risk(self):
        # same completeness, different hazard values => same confidence
        a = _fs({"rain_3h": 5})
        b = _fs({"rain_3h": 120})
        self.assertAlmostEqual(engine._confidence(a)[0],
                               engine._confidence(b)[0], places=6)


class TestAssess(unittest.TestCase):
    def test_full_result_shape_and_disclaimer(self):
        r = engine.assess(_fs({"rain_3h": 100, "rain_24h": 200, "rain_intensity": 40,
                               "soil_saturation_index": 0.9, "river_level": 6,
                               "river_rate_of_rise_1h": 0.8, "slope": 40,
                               "susceptibility": 0.8}), mode="replay")
        self.assertIn(r.risk_level, ("MODERATE", "HIGH", "CRITICAL"))
        self.assertTrue(0.0 <= r.confidence <= 1.0)
        self.assertTrue(0.0 <= r.flood_probability <= 1.0)
        self.assertTrue(any("DEMO MODEL" in n for n in r.notes))
        self.assertTrue(any("REPLAY" in n for n in r.notes))
        self.assertTrue(r.top_factors)  # explainability present

    def test_lead_time_window_or_none(self):
        r = engine.assess(_fs({"rain_intensity": 55, "river_rate_of_rise_1h": 1.2}),
                          mode="replay")
        self.assertIsNotNone(r.lead_time_min_lo)
        self.assertLess(r.lead_time_min_lo, r.lead_time_min_hi)
        # no signals => no window
        r2 = engine.assess(_fs({"slope": 30}), mode="replay")
        self.assertIsNone(r2.lead_time_min_lo)


if __name__ == "__main__":
    unittest.main()
