"""Validation / QC checks (master prompt section 11)."""
import unittest
from _util import bootstrap
bootstrap()

from app.processing import validate as V


class TestValidate(unittest.TestCase):
    def test_good_rainfall_passes(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "rainfall_30m": 12.0, "rainfall_3h": 40.0, "rainfall_24h": 90.0}
        issues = V.check_rainfall(rec)
        self.assertEqual([lvl for lvl, _ in issues], [])  # no problems

    def test_negative_rainfall_is_bad(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "rainfall_30m": -3.0}
        levels = [lvl for lvl, _ in V.check_rainfall(rec)]
        self.assertIn("BAD", levels)

    def test_extreme_rainfall_is_warning_not_dropped(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "rainfall_30m": 999.0}
        levels = [lvl for lvl, _ in V.check_rainfall(rec)]
        self.assertIn("WARNING", levels)
        self.assertNotIn("BAD", levels)

    def test_missing_timestamp_is_bad(self):
        rec = {"latitude": 30.05, "longitude": 78.05, "rainfall_30m": 5.0}
        levels = [lvl for lvl, _ in V.check_rainfall(rec)]
        self.assertIn("BAD", levels)

    def test_missing_coords_is_bad(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "rainfall_30m": 5.0}
        levels = [lvl for lvl, _ in V.check_rainfall(rec)]
        self.assertIn("BAD", levels)

    def test_coords_outside_india_warns(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 51.5, "longitude": -0.1}
        levels = [lvl for lvl, _ in V.check_geo(rec)]
        self.assertIn("WARNING", levels)

    def test_soil_out_of_range_warns(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "surface_moisture": 140.0}
        levels = [lvl for lvl, _ in V.check_soil(rec)]
        self.assertIn("WARNING", levels)

    def test_river_negative_level_bad(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "water_level": -1.0}
        levels = [lvl for lvl, _ in V.check_river(rec)]
        self.assertIn("BAD", levels)

    def test_iot_missing_sensor_id_bad(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05}
        levels = [lvl for lvl, _ in V.check_iot(rec)]
        self.assertIn("BAD", levels)

    def test_parse_ts_handles_z_and_naive(self):
        self.assertIsNotNone(V.parse_ts("2024-08-01T06:00:00Z"))
        self.assertIsNotNone(V.parse_ts("2024-08-01T06:00:00"))
        self.assertIsNone(V.parse_ts("not-a-date"))
        self.assertIsNone(V.parse_ts(""))

    def test_is_stale(self):
        self.assertTrue(V.is_stale("2000-01-01T00:00:00Z", 60))
        self.assertTrue(V.is_stale("bad", 60))


if __name__ == "__main__":
    unittest.main()
