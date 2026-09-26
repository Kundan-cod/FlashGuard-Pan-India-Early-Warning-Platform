"""IMD vertical-slice tests (master prompt sections 7, 11, 34, 66).

Prove — with zero network and zero Track B deps (httpx/pydantic absent in the
portable sandbox) — that the IMD bridge collector honours every constraint that
makes IMD DIFFERENT from the discovery-only satellite sources (GPM/SMAP):

  1. IMD returns REAL numeric government weather/rainfall/warnings, so a
     successful run DOES store values — but into imd_observations ONLY.
  2. An IMD record NEVER enters rainfall_observations (a point table read by the
     ML feature pipeline as village-level rainfall). No coordinate is fabricated
     for a district/station figure ("Do not treat district rainfall as
     village-level rainfall").
  3. Warning codes/colors are preserved VERBATIM and never converted to an ML
     probability ("Do not convert IMD warning color into our ML probability").
  4. A 5-day district warning explodes into one row per warning_day (1..5).
  5. No token (when auth is required) -> honest NOT_CONFIGURED, NOT an error,
     no rows written -> replay stays untouched.
  5b. A placeholder token counts as NOT configured.
  6. Unverified source -> refuses to fetch (ERROR), no invented endpoints.
  7. Successful fetch reports LIVE (IMD is a live government source).

The vendored IMD client is injected as a tiny fake exposing the same method
names (current_weather/district_rainfall/district_warning/district_nowcast +
normalize_*), mirroring the vendored IMDCollector, so the honesty-critical logic
is provable in-sandbox (the vendored collector imports httpx at module load).
"""
import os
import unittest
from _util import bootstrap
bootstrap()

from app.database import db, repositories as repo
from app.collectors import imd_mapping as M
from app.collectors.imd_collector import ImdCollector


# ---- canned IMD payloads (already-normalized contract dicts) ----
def _current_weather_rows():
    return [{
        "station_id": "42182", "station": "New Delhi (Safdarjung)",
        "observation_date": "2024-08-01", "observation_time_utc": "2024-08-01T03:00:00Z",
        "temperature_c": 31.2, "humidity_pct": 78.0, "wind_speed_kmph": 12.0,
        "wind_direction_code": 90.0, "pressure_hpa": 1002.4,
        "rainfall_24h_mm": 46.5, "weather_code": "RA",
        "raw": {"Station Id": 42182, "Temperature": "31.2"},
    }]


def _district_rainfall_rows():
    return [{
        "district_id": "512", "district": "Chamoli", "date": "2024-08-01",
        "daily_actual_mm": 88.0, "daily_normal_mm": 20.0,
        "daily_departure_pct": 340.0, "daily_category": "Large Excess",
        "cumulative_actual_mm": 640.0, "cumulative_normal_mm": 500.0,
        "cumulative_departure_pct": 28.0, "cumulative_category": "Excess",
        "raw": {"OBJ_ID": 512, "District": "Chamoli"},
    }]


def _warning_rows():
    return [{
        "district_id": "512", "district": "Chamoli",
        "issued_date": "2024-08-01", "issued_utc": "2024-08-01T06:00:00Z",
        "day1": "Heavy rain", "day2": "Heavy rain", "day3": "Very heavy rain",
        "day4": None, "day5": None,
        "day1_color": 2, "day2_color": 2, "day3_color": 3,
        "day4_color": None, "day5_color": None,
        "raw": {"Obj_id": 512, "Day_1": "Heavy rain"},
    }]


def _nowcast_rows():
    return [{
        "station": "Dehradun", "date": "2024-08-01", "issue_time": "2024-08-01T05:30:00Z",
        "valid_upto": "2024-08-01T08:30:00Z", "color": 3,
        "message": "Thunderstorm with heavy rain likely",
        "raw": {"Station": "Dehradun", "color": 3},
    }]


class _FakeImdClient:
    """Stand-in for the vendored IMDCollector: returns canned payloads and
    normalizes them to plain dicts. No network, no httpx, no pydantic."""
    def __init__(self):
        self.calls = []

    # fetch methods (payload is opaque; the normalize_* below ignore it)
    def current_weather(self, station_id=None):
        self.calls.append(("current_weather", station_id)); return {}

    def district_rainfall(self, district_id=None):
        self.calls.append(("district_rainfall", district_id)); return {}

    def district_warning(self, district_id=None):
        self.calls.append(("district_warning", district_id)); return {}

    def district_nowcast(self, district_id=None):
        self.calls.append(("district_nowcast", district_id)); return {}

    # normalize methods return already-shaped contract dicts
    def normalize_current_weather(self, payload):
        return _current_weather_rows()

    def normalize_district_rainfall(self, payload):
        return _district_rainfall_rows()

    def normalize_warning(self, payload):
        return _warning_rows()

    def normalize_nowcast(self, payload):
        return _nowcast_rows()


def _collector(**kw):
    kw.setdefault("verified", True)
    kw.setdefault("auth_env_var", "IMD_API_TOKEN")
    kw.setdefault("client", _FakeImdClient())
    return ImdCollector(**kw)


class ImdSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)
        os.environ.pop("IMD_API_TOKEN", None)

    def tearDown(self):
        os.environ.pop("IMD_API_TOKEN", None)

    # ---- 1 + 2: real values stored to imd_observations, NEVER rainfall_observations ----
    def test_stores_real_values_only_in_imd_observations(self):
        os.environ["IMD_API_TOKEN"] = "real-imd-token"
        c = _collector()
        res = c.run()
        # 1 current_weather + 1 district_rainfall + 3 warning-days + 1 nowcast = 6
        self.assertEqual(res.stored, 6, f"expected 6 IMD rows, got {res.stored}")

        rows = repo.imd_recent(limit=100)
        self.assertEqual(len(rows), 6)

        # The ML feature pipeline reads rainfall_observations — IMD must NEVER
        # land there (no fabricated village coordinate for a district figure).
        rain = db.query("SELECT COUNT(*) AS n FROM rainfall_observations")
        self.assertEqual(rain[0]["n"], 0,
                         "IMD must NEVER reach rainfall_observations")
        soil = db.query("SELECT COUNT(*) AS n FROM soil_moisture_observations")
        self.assertEqual(soil[0]["n"], 0)

    # ---- current weather preserves numeric values + station identity ----
    def test_current_weather_values_preserved(self):
        os.environ["IMD_API_TOKEN"] = "t"
        _collector(record_kinds=("current_weather",)).run()
        rows = [r for r in repo.imd_recent(100) if r["record_type"] == "current_weather"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["area_kind"], "station")
        self.assertEqual(r["area_id"], "42182")
        self.assertAlmostEqual(r["temperature_c"], 31.2)
        self.assertAlmostEqual(r["rainfall_24h_mm"], 46.5)
        self.assertIsNone(r["warning_color"])

    # ---- 3: warning code + color preserved verbatim, never an ML probability ----
    def test_warning_codes_and_colors_preserved_verbatim(self):
        os.environ["IMD_API_TOKEN"] = "t"
        _collector(record_kinds=("district_warning",)).run()
        rows = sorted(
            (r for r in repo.imd_recent(100) if r["record_type"] == "district_warning"),
            key=lambda r: r["warning_day"])
        # 4: three populated days (day4/day5 are None -> skipped)
        self.assertEqual([r["warning_day"] for r in rows], [1, 2, 3])
        self.assertEqual(rows[0]["warning_code"], "Heavy rain")
        self.assertEqual(rows[0]["warning_color"], 2)
        self.assertEqual(rows[2]["warning_code"], "Very heavy rain")
        self.assertEqual(rows[2]["warning_color"], 3)
        for r in rows:
            self.assertEqual(r["area_kind"], "district")
            self.assertEqual(r["area_id"], "512")
            # color is a raw IMD int in [0..5], NOT a 0..1 probability
            self.assertIsInstance(r["warning_color"], int)

    # ---- district rainfall keeps IMD's own category (not our ML threshold) ----
    def test_district_rainfall_category_is_imd_label(self):
        os.environ["IMD_API_TOKEN"] = "t"
        _collector(record_kinds=("district_rainfall",)).run()
        rows = [r for r in repo.imd_recent(100) if r["record_type"] == "district_rainfall"]
        self.assertEqual(len(rows), 1)
        r = rows[0]
        self.assertEqual(r["rainfall_category"], "Large Excess")
        self.assertAlmostEqual(r["daily_actual_mm"], 88.0)
        self.assertAlmostEqual(r["cumulative_actual_mm"], 640.0)
        # a district figure carries no point coordinate
        self.assertNotIn("latitude", r)

    # ---- 5: no token -> NOT_CONFIGURED, no rows, replay untouched ----
    def test_no_token_is_not_configured_not_error(self):
        c = _collector()
        res = c.run()
        self.assertEqual(res.stored, 0)
        health = repo.get_source_health("imd")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "NOT_CONFIGURED")
        self.assertIsNone(health["last_success_at"])
        self.assertEqual(len(repo.imd_recent(100)), 0)

    # ---- 5b: placeholder token counts as NOT configured ----
    def test_placeholder_token_is_not_configured(self):
        for placeholder in ("your_token_here", "changeme", "  ", "<token>",
                            "imd_api_token", "TODO"):
            with self.subTest(placeholder=placeholder):
                db.init_db(reset=True)
                os.environ["IMD_API_TOKEN"] = placeholder
                c = _collector()
                self.assertFalse(c.has_token())
                res = c.run()
                self.assertEqual(res.stored, 0)
                self.assertEqual(repo.get_source_health("imd")["status"],
                                 "NOT_CONFIGURED")

    # ---- public-endpoint mode: auth_env_var=None -> configured without a token ----
    def test_public_mode_without_token_is_configured(self):
        c = _collector(auth_env_var=None)
        self.assertTrue(c.is_configured())
        res = c.run()
        self.assertEqual(res.stored, 6)
        self.assertEqual(repo.get_source_health("imd")["status"], "LIVE")

    # ---- 6: unverified source refuses to fetch (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        os.environ["IMD_API_TOKEN"] = "t"
        c = _collector(verified=False)
        with self.assertRaises(RuntimeError):
            c.run()
        self.assertEqual(repo.get_source_health("imd")["status"], "ERROR")

    # ---- 7: successful fetch reports LIVE ----
    def test_successful_fetch_reports_live(self):
        os.environ["IMD_API_TOKEN"] = "t"
        c = _collector()
        c.run()
        health = repo.get_source_health("imd")
        self.assertEqual(health["status"], "LIVE")
        self.assertIsNotNone(health["last_success_at"])

    # ---- idempotency: re-running does not duplicate rows ----
    def test_reingest_is_idempotent(self):
        os.environ["IMD_API_TOKEN"] = "t"
        _collector().run()
        first = len(repo.imd_recent(100))
        _collector().run()
        second = len(repo.imd_recent(100))
        self.assertEqual(first, second,
                         "re-ingesting the same IMD payload must not duplicate rows")

    # ---- mapping invariant: warning explosion + verbatim color, pure Python ----
    def test_mapping_warning_explosion_and_verbatim(self):
        recs = M.warning_to_records(_warning_rows(), retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual([r["warning_day"] for r in recs], [1, 2, 3])
        self.assertEqual(recs[0]["warning_color"], 2)
        self.assertEqual(recs[2]["warning_code"], "Very heavy rain")
        for r in recs:
            self.assertEqual(r["record_type"], M.DISTRICT_WARNING)
            self.assertEqual(r["source"], "imd")
            # never a probability field
            self.assertNotIn("flood_probability", r)


if __name__ == "__main__":
    unittest.main()
