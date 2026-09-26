"""Normalization to canonical units / CRS / time (master prompt section 12)."""
import unittest
from _util import bootstrap
bootstrap()

from app.processing import normalize as N


class TestNormalize(unittest.TestCase):
    def test_ts_to_utc_z(self):
        self.assertEqual(N.to_utc_iso("2024-08-01T11:30:00+05:30"),
                         "2024-08-01T06:00:00Z")
        self.assertEqual(N.to_utc_iso("2024-08-01T06:00:00Z"),
                         "2024-08-01T06:00:00Z")
        # naive is assumed UTC
        self.assertEqual(N.to_utc_iso("2024-08-01T06:00:00"),
                         "2024-08-01T06:00:00Z")

    def test_norm_rainfall_shape(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "rainfall_30m": 10, "rainfall_3h": 40, "rainfall_24h": 90}
        o = N.norm_rainfall(rec, "replay", "replay", resolution_m=10000)
        self.assertEqual(o["source"], "replay")
        self.assertEqual(o["realtime_class"], "replay")
        self.assertEqual(o["resolution_m"], 10000)
        self.assertEqual(o["rainfall_3h"], 40.0)
        self.assertIsInstance(o["rainfall_30m"], float)

    def test_norm_soil_fraction_to_percent(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "surface_moisture": 0.42}
        o = N.norm_soil(rec, "smap", "replay", unit="fraction")
        self.assertAlmostEqual(o["surface_moisture"], 42.0, places=6)

    def test_norm_soil_percent_passthrough(self):
        rec = {"ts": "2024-08-01T06:00:00Z", "latitude": 30.05, "longitude": 78.05,
               "surface_moisture": 42.0}
        o = N.norm_soil(rec, "iot", "replay", unit="percent")
        self.assertAlmostEqual(o["surface_moisture"], 42.0, places=6)

    def test_norm_iot_accepts_aliased_keys(self):
        rec = {"sensor_id": "s1", "ts": "2024-08-01T06:00:00Z",
               "latitude": 30.05, "longitude": 78.05,
               "rainfall_mm": 5.0, "water_level_m": 1.2}
        o = N.norm_iot(rec)
        self.assertEqual(o["rainfall"], 5.0)
        self.assertEqual(o["water_level"], 1.2)
        self.assertEqual(o["is_simulated"], 1)

    def test_none_handling(self):
        self.assertIsNone(N._f(None))
        self.assertIsNone(N._f(""))
        self.assertIsNone(N._f("abc"))
        self.assertEqual(N._f("3.5"), 3.5)


if __name__ == "__main__":
    unittest.main()
