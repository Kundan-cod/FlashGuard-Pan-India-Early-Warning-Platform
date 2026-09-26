"""
IMD (India Meteorological Department) normalized rows -> internal
`imd_observations` record shape. Pure Python (no httpx, no pydantic) so the
honesty-critical logic is provable in any environment.

WHY THIS IS NOT DISCOVERY-ONLY (unlike gpm_mapping / smap_mapping):
IMD returns REAL numeric government weather/rainfall/warnings — a temperature,
a district rainfall figure, a warning color — not a dataset footprint. So these
values ARE stored (in imd_observations). What we deliberately do NOT do:

  * We never place an IMD value in rainfall_observations (a point table the ML
    feature pipeline reads as village-level rainfall). IMD is district/station
    granularity WITHOUT coordinates; treating a district figure as a village
    value would violate the verified spec ("Do not treat district rainfall as
    village-level rainfall"). So latitude/longitude are simply absent here — we
    never fabricate a coordinate.
  * We never convert an IMD warning code/color into an ML probability (verified
    spec: "Do not convert IMD warning color into our ML probability"). The code
    and color int are preserved verbatim in warning_code/warning_color.
  * The full original row is preserved in raw_reference (JSON) for provenance.

The bridge collector converts each vendored pydantic contract into a plain dict
(via .model_dump()/.dict()) before calling these functions, so this module never
imports the vendored package or its deps.

record_type values: current_weather | district_rainfall | district_warning |
nowcast  (mirrors schema_sqlite.sql imd_observations.record_type comment).
"""
from __future__ import annotations

import json
from typing import Any

CURRENT_WEATHER = "current_weather"
DISTRICT_RAINFALL = "district_rainfall"
DISTRICT_WARNING = "district_warning"
NOWCAST = "nowcast"

# Sentinels for the idempotency natural key (source, record_type, area_id,
# observed_at, warning_day). BOTH SQLite and PostgreSQL treat NULL as DISTINCT in
# a UNIQUE constraint, so a NULL key column would defeat the ON CONFLICT dedup
# and let re-ingestion duplicate rows. We therefore never place a NULL in a
# key column: a missing area id / observed time collapses to a stable sentinel,
# and non-warning records use warning_day=0 ("not a warning day"). These
# sentinels affect ONLY the key columns; no measured value is ever invented.
_NO_AREA = "_"          # area_id sentinel when a record has no reported area id
_NO_TIME = "_"          # observed_at sentinel when a record has no reported time
_NOT_A_WARNING_DAY = 0  # warning_day sentinel for non-warning records


def _key_area(*candidates: Any) -> str:
    for c in candidates:
        if c not in (None, ""):
            return str(c)
    return _NO_AREA


def _key_time(*candidates: Any) -> str:
    for c in candidates:
        if c not in (None, ""):
            return str(c)
    return _NO_TIME


def _raw_json(d: dict[str, Any] | None) -> str | None:
    if not d:
        return None
    return json.dumps(d, sort_keys=True, default=str)


def current_weather_to_records(
    rows: list[dict[str, Any]], *, retrieved_at: str | None = None,
) -> list[dict]:
    """Map normalized IMDCurrentWeather dicts -> imd_observations records.

    Station-level real weather. Numeric values are preserved as-is; no
    coordinate is fabricated (IMD current_wx has no lat/lon)."""
    out: list[dict] = []
    for r in rows or []:
        out.append({
            "source": "imd",
            "record_type": CURRENT_WEATHER,
            "area_kind": "station",
            "area_id": _key_area(r.get("station_id"), r.get("station")),
            "area_name": r.get("station"),
            "observed_at": _key_time(r.get("observation_time_utc"),
                                     r.get("observation_date")),
            "valid_upto": None,
            "temperature_c": r.get("temperature_c"),
            "humidity_pct": r.get("humidity_pct"),
            "wind_speed_kmph": r.get("wind_speed_kmph"),
            "pressure_hpa": r.get("pressure_hpa"),
            "rainfall_24h_mm": r.get("rainfall_24h_mm"),
            "daily_actual_mm": None,
            "daily_normal_mm": None,
            "cumulative_actual_mm": None,
            "cumulative_normal_mm": None,
            "rainfall_category": None,
            # weather_code preserved verbatim as an IMD code (NOT an ML value).
            "warning_code": r.get("weather_code"),
            "warning_color": None,
            "warning_day": _NOT_A_WARNING_DAY,
            "message": None,
            "quality_flag": "GOOD",
            "realtime_class": "real_time",
            "raw_reference": _raw_json(r.get("raw")),
            "retrieved_at": retrieved_at,
        })
    return out


def district_rainfall_to_records(
    rows: list[dict[str, Any]], *, retrieved_at: str | None = None,
) -> list[dict]:
    """Map normalized IMDDistrictRainfall dicts -> imd_observations records.

    District-level real rainfall context (actual/normal, daily + cumulative).
    IMD's own category label is preserved in rainfall_category — it is NOT our
    ML threshold. No coordinate is fabricated for the district."""
    out: list[dict] = []
    for r in rows or []:
        out.append({
            "source": "imd",
            "record_type": DISTRICT_RAINFALL,
            "area_kind": "district",
            "area_id": _key_area(r.get("district_id"), r.get("district")),
            "area_name": r.get("district"),
            "observed_at": _key_time(r.get("date")),
            "valid_upto": None,
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_kmph": None,
            "pressure_hpa": None,
            "rainfall_24h_mm": None,
            "daily_actual_mm": r.get("daily_actual_mm"),
            "daily_normal_mm": r.get("daily_normal_mm"),
            "cumulative_actual_mm": r.get("cumulative_actual_mm"),
            "cumulative_normal_mm": r.get("cumulative_normal_mm"),
            # IMD's own label (e.g. its daily category); NOT our ML threshold.
            "rainfall_category": r.get("daily_category") or r.get("cumulative_category"),
            "warning_code": None,
            "warning_color": None,
            "warning_day": _NOT_A_WARNING_DAY,
            "message": None,
            "quality_flag": "GOOD",
            "realtime_class": "real_time",
            "raw_reference": _raw_json(r.get("raw")),
            "retrieved_at": retrieved_at,
        })
    return out


def warning_to_records(
    rows: list[dict[str, Any]], *, retrieved_at: str | None = None,
) -> list[dict]:
    """Map normalized IMDWarning dicts -> imd_observations records, EXPLODING
    the 5-day forecast into one row per warning_day (1..5).

    warning_code (the Day_N text code) and warning_color (the Day_N color int)
    are preserved verbatim. They are NEVER converted to an ML probability. A
    day with neither a code nor a color is skipped (nothing to record)."""
    out: list[dict] = []
    for r in rows or []:
        raw = _raw_json(r.get("raw"))
        for day in range(1, 6):
            code = r.get(f"day{day}")
            color = r.get(f"day{day}_color")
            if code is None and color is None:
                continue
            out.append({
                "source": "imd",
                "record_type": DISTRICT_WARNING,
                "area_kind": "district",
                "area_id": _key_area(r.get("district_id"), r.get("district")),
                "area_name": r.get("district"),
                "observed_at": _key_time(r.get("issued_utc"), r.get("issued_date")),
                "valid_upto": None,
                "temperature_c": None,
                "humidity_pct": None,
                "wind_speed_kmph": None,
                "pressure_hpa": None,
                "rainfall_24h_mm": None,
                "daily_actual_mm": None,
                "daily_normal_mm": None,
                "cumulative_actual_mm": None,
                "cumulative_normal_mm": None,
                "rainfall_category": None,
                # Verbatim IMD code + color; never an ML probability.
                "warning_code": code,
                "warning_color": color,
                "warning_day": day,
                "message": None,
                "quality_flag": "GOOD",
                "realtime_class": "real_time",
                "raw_reference": raw,
                "retrieved_at": retrieved_at,
            })
    return out


def nowcast_to_records(
    rows: list[dict[str, Any]], *, retrieved_at: str | None = None,
) -> list[dict]:
    """Map normalized IMDNowcast dicts -> imd_observations records.

    Nowcast color int + message text are preserved verbatim; color is NOT an ML
    probability. valid_upto is the IMD-reported validity."""
    out: list[dict] = []
    for r in rows or []:
        out.append({
            "source": "imd",
            "record_type": NOWCAST,
            "area_kind": "station",
            "area_id": _key_area(r.get("station")),
            "area_name": r.get("station"),
            "observed_at": _key_time(r.get("issue_time"), r.get("date")),
            "valid_upto": r.get("valid_upto"),
            "temperature_c": None,
            "humidity_pct": None,
            "wind_speed_kmph": None,
            "pressure_hpa": None,
            "rainfall_24h_mm": None,
            "daily_actual_mm": None,
            "daily_normal_mm": None,
            "cumulative_actual_mm": None,
            "cumulative_normal_mm": None,
            "rainfall_category": None,
            "warning_code": None,
            # Nowcast color preserved verbatim; never an ML probability.
            "warning_color": r.get("color"),
            "warning_day": _NOT_A_WARNING_DAY,
            "message": r.get("message"),
            "quality_flag": "GOOD",
            "realtime_class": "real_time",
            "raw_reference": _raw_json(r.get("raw")),
            "retrieved_at": retrieved_at,
        })
    return out
