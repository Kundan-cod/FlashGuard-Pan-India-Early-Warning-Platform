"""
Normalization to canonical internal units/CRS/time (master prompt section 12).

Canonical conventions (documented, enforced here):
  rainfall     -> mm
  soil moisture-> % (0..100)
  water level  -> metres
  temperature  -> °C
  coordinates  -> WGS84 (EPSG:4326), decimal degrees
  timestamps   -> UTC ISO-8601 with trailing 'Z'

Each normalizer returns a canonical dict ready for the repository upsert. Unit
hints may be supplied by the collector's raw meta (e.g. soil as fraction 0..1).
"""
from __future__ import annotations

from datetime import datetime, timezone


def to_utc_iso(ts: str) -> str:
    s = ts.replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def norm_rainfall(rec: dict, source: str, realtime_class: str,
                  resolution_m: float | None = None) -> dict:
    return {
        "source": source,
        "ts": to_utc_iso(rec["ts"]),
        "latitude": float(rec["latitude"]),
        "longitude": float(rec["longitude"]),
        "rainfall_30m": _f(rec.get("rainfall_30m")),
        "rainfall_3h": _f(rec.get("rainfall_3h")),
        "rainfall_24h": _f(rec.get("rainfall_24h")),
        "quality_flag": rec.get("quality_flag", "GOOD"),
        "resolution_m": resolution_m,
        "realtime_class": realtime_class,
    }


def norm_soil(rec: dict, source: str, realtime_class: str,
              resolution_m: float | None = None, unit: str = "percent") -> dict:
    sm = _f(rec.get("surface_moisture"))
    rz = _f(rec.get("root_zone_moisture"))
    if unit == "fraction":   # convert 0..1 -> %
        sm = sm * 100.0 if sm is not None else None
        rz = rz * 100.0 if rz is not None else None
    return {
        "source": source,
        "ts": to_utc_iso(rec["ts"]),
        "latitude": float(rec["latitude"]),
        "longitude": float(rec["longitude"]),
        "surface_moisture": sm,
        "root_zone_moisture": rz,
        "quality_flag": rec.get("quality_flag", "GOOD"),
        "resolution_m": resolution_m,
        "realtime_class": realtime_class,
    }


def norm_river(rec: dict, source: str, realtime_class: str) -> dict:
    return {
        "source": source,
        "station_id": rec.get("station_id"),
        "ts": to_utc_iso(rec["ts"]),
        "latitude": _f(rec.get("latitude")),
        "longitude": _f(rec.get("longitude")),
        "water_level": _f(rec.get("water_level")),
        "flow": _f(rec.get("flow")),
        "rate_of_rise": _f(rec.get("rate_of_rise")),
        "quality_flag": rec.get("quality_flag", "GOOD"),
        "realtime_class": realtime_class,
    }


def norm_iot(rec: dict) -> dict:
    return {
        "sensor_id": rec["sensor_id"],
        "ts": to_utc_iso(rec["ts"]),
        "latitude": _f(rec.get("latitude")),
        "longitude": _f(rec.get("longitude")),
        "rainfall": _f(rec.get("rainfall_mm", rec.get("rainfall"))),
        "soil_moisture": _f(rec.get("soil_moisture")),
        "water_level": _f(rec.get("water_level_m", rec.get("water_level"))),
        "temperature": _f(rec.get("temperature")),
        "quality_flag": rec.get("quality_flag", "GOOD"),
        "is_simulated": int(rec.get("is_simulated", 1)),
    }


def _f(v):
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
