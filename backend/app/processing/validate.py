"""
Data quality / validation checks (master prompt section 11).

Pure functions that inspect a raw record dict and return a list of problems.
Collectors call these in validate(). Physical bounds are prototype sanity
limits, not official meteorological limits — labelled as such.

Quality flags: GOOD | WARNING | BAD | MISSING | STALE
  BAD     -> record dropped before it enters the DB
  WARNING -> stored but flagged (used to lower confidence)
  MISSING -> field absent
  STALE   -> timestamp too old for its realtime class
"""
from __future__ import annotations

from datetime import datetime, timezone

# --- prototype sanity bounds (NOT official thresholds) ---------------------
RAIN_MAX_30M_MM = 250.0     # extreme but physically plausible upper sanity bound
RAIN_MAX_24H_MM = 2000.0
LEVEL_MAX_M = 100.0
SOIL_MIN, SOIL_MAX = 0.0, 100.0
LAT_MIN, LAT_MAX = 6.0, 38.0     # India bounding sanity (incl. margin)
LON_MIN, LON_MAX = 67.0, 98.0
TEMP_MIN, TEMP_MAX = -40.0, 60.0


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def parse_ts(ts) -> datetime | None:
    if not ts:
        return None
    # Track B (PostGIS timestamptz) hands back real datetime objects, whereas
    # Track A (SQLite) returns ISO strings. Accept both so shared consumers
    # (feature engineering, etc.) are storage-agnostic.
    if isinstance(ts, datetime):
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    try:
        s = str(ts).replace("Z", "+00:00")
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def check_geo(rec: dict) -> list[tuple[str, str]]:
    out = []
    lat, lon = _num(rec.get("latitude")), _num(rec.get("longitude"))
    if lat is None or lon is None:
        out.append(("BAD", "missing/invalid coordinates"))
        return out
    if not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
        out.append(("WARNING", f"coordinates outside India sanity box ({lat},{lon})"))
    return out


def check_rainfall(rec: dict) -> list[tuple[str, str]]:
    out = check_geo(rec)
    for k, mx in (("rainfall_30m", RAIN_MAX_30M_MM),
                  ("rainfall_3h", RAIN_MAX_24H_MM),
                  ("rainfall_24h", RAIN_MAX_24H_MM)):
        v = _num(rec.get(k))
        if v is None:
            continue
        if v < 0:
            out.append(("BAD", f"{k} negative ({v})"))
        elif v > mx:
            out.append(("WARNING", f"{k} exceeds prototype sanity bound ({v}>{mx})"))
    if parse_ts(rec.get("ts")) is None:
        out.append(("BAD", "missing/invalid timestamp"))
    return out


def check_soil(rec: dict) -> list[tuple[str, str]]:
    out = check_geo(rec)
    v = _num(rec.get("surface_moisture"))
    if v is not None and not (SOIL_MIN <= v <= SOIL_MAX):
        out.append(("WARNING", f"surface_moisture out of 0..100 ({v})"))
    if parse_ts(rec.get("ts")) is None:
        out.append(("BAD", "missing/invalid timestamp"))
    return out


def check_river(rec: dict) -> list[tuple[str, str]]:
    out = []
    v = _num(rec.get("water_level"))
    if v is not None:
        if v < 0:
            out.append(("BAD", f"water_level negative ({v})"))
        elif v > LEVEL_MAX_M:
            out.append(("WARNING", f"water_level exceeds sanity bound ({v})"))
    if parse_ts(rec.get("ts")) is None:
        out.append(("BAD", "missing/invalid timestamp"))
    return out


def check_iot(rec: dict) -> list[tuple[str, str]]:
    out = check_geo(rec)
    if not rec.get("sensor_id"):
        out.append(("BAD", "missing sensor_id"))
    t = _num(rec.get("temperature"))
    if t is not None and not (TEMP_MIN <= t <= TEMP_MAX):
        out.append(("WARNING", f"temperature out of range ({t})"))
    r = _num(rec.get("rainfall"))
    if r is not None and r < 0:
        out.append(("BAD", f"rainfall negative ({r})"))
    if parse_ts(rec.get("ts")) is None:
        out.append(("BAD", "missing/invalid timestamp"))
    return out


def is_stale(ts: str, max_age_minutes: float) -> bool:
    dt = parse_ts(ts)
    if dt is None:
        return True
    age = (datetime.now(timezone.utc) - dt).total_seconds() / 60.0
    return age > max_age_minutes
