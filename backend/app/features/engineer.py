"""
Feature engineering (master prompt section 15).

Builds a feature vector for a location from normalized internal tables ONLY
(never from an external API — section 2). Every feature carries an availability
flag so the risk engine can compute data completeness and confidence, and so a
missing source lowers confidence instead of silently becoming a fake zero
(section 5).

Returns a FeatureSet with:
  values     : dict feature_name -> float (missing -> None)
  available  : dict source_key -> bool
  provenance : dict feature_name -> {source, resolution_m, realtime_class, quality}
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.database import repositories as repo
from app.processing.validate import parse_ts

# Sources we *expect* for a full picture (for data-completeness = have/expected).
EXPECTED_SOURCES = ["rainfall", "soil", "river", "terrain", "susceptibility"]


@dataclass
class FeatureSet:
    location_id: int
    values: dict = field(default_factory=dict)
    available: dict = field(default_factory=dict)
    provenance: dict = field(default_factory=dict)
    as_of: str = ""

    def completeness(self) -> float:
        have = sum(1 for s in EXPECTED_SOURCES if self.available.get(s))
        return have / len(EXPECTED_SOURCES)


def _hours_between(a: str, b: str) -> float:
    da, db_ = parse_ts(a), parse_ts(b)
    if not da or not db_:
        return 0.0
    return abs((da - db_).total_seconds()) / 3600.0


def _accumulate(series: list[dict], ref_ts: datetime, hours: float, field_: str) -> float | None:
    """Sum a per-observation field over the last `hours` before ref_ts.
    For window fields already representing accumulation (rainfall_3h etc.) we
    instead take the most recent non-null within the window."""
    best = None
    for row in series:  # newest first
        dt = parse_ts(row["ts"])
        if not dt:
            continue
        age_h = (ref_ts - dt).total_seconds() / 3600.0
        if age_h < 0 or age_h > hours:
            continue
        v = row.get(field_)
        if v is not None:
            best = v
            break
    return best


def build_features(location_id: int, as_of: str | None = None) -> FeatureSet:
    loc = repo.get_location(location_id)
    if not loc:
        raise ValueError(f"unknown location {location_id}")
    lat, lon = loc["latitude"], loc["longitude"]
    ref = parse_ts(as_of) if as_of else datetime.now(timezone.utc)
    fs = FeatureSet(location_id=location_id,
                    as_of=(as_of or ref.strftime("%Y-%m-%dT%H:%M:%SZ")))

    # ---- Rainfall ----
    rain = [r for r in repo.rainfall_series(lat, lon)
            if parse_ts(r["ts"]) and parse_ts(r["ts"]) <= ref]
    if rain:
        latest = rain[0]
        fs.available["rainfall"] = True
        fs.values["rain_30m"] = latest.get("rainfall_30m")
        fs.values["rain_3h"] = latest.get("rainfall_3h")
        fs.values["rain_24h"] = latest.get("rainfall_24h")
        # intensity & change
        fs.values["rain_intensity"] = latest.get("rainfall_30m")
        if len(rain) > 1:
            prev = rain[1]
            if latest.get("rainfall_3h") is not None and prev.get("rainfall_3h") is not None:
                fs.values["rain_change_3h"] = latest["rainfall_3h"] - prev["rainfall_3h"]
        fs.provenance["rainfall"] = {
            "source": latest["source"], "resolution_m": latest.get("resolution_m"),
            "realtime_class": latest.get("realtime_class"),
            "quality": latest.get("quality_flag"), "ts": latest["ts"],
        }
    else:
        fs.available["rainfall"] = False

    # ---- Soil moisture (respect as_of cutoff to prevent future leakage) ----
    soil = repo.soil_latest(lat, lon, up_to_ts=fs.as_of)
    if soil and (soil.get("surface_moisture") is not None):
        fs.available["soil"] = True
        fs.values["soil_moisture"] = soil["surface_moisture"]
        fs.values["soil_saturation_index"] = min(1.0, (soil["surface_moisture"] or 0) / 100.0)
        fs.provenance["soil"] = {
            "source": soil["source"], "resolution_m": soil.get("resolution_m"),
            "realtime_class": soil.get("realtime_class"),
            "quality": soil.get("quality_flag"), "ts": soil["ts"],
        }
    else:
        fs.available["soil"] = False

    # ---- River ----
    river = [r for r in repo.river_series_near(lat, lon)
             if parse_ts(r["ts"]) and parse_ts(r["ts"]) <= ref]
    if river:
        latest = river[0]
        fs.available["river"] = True
        fs.values["river_level"] = latest.get("water_level")
        # rate of rise over ~1h from series if not precomputed
        ror = latest.get("rate_of_rise")
        if ror is None and len(river) > 1:
            for older in river[1:]:
                dh = _hours_between(latest["ts"], older["ts"])
                if dh >= 0.4 and latest.get("water_level") is not None \
                        and older.get("water_level") is not None:
                    ror = (latest["water_level"] - older["water_level"]) / dh
                    break
        fs.values["river_rate_of_rise_1h"] = ror
        fs.provenance["river"] = {
            "source": latest["source"], "realtime_class": latest.get("realtime_class"),
            "quality": latest.get("quality_flag"), "ts": latest["ts"],
        }
    else:
        fs.available["river"] = False

    # ---- Terrain (static) ----
    terr = repo.get_terrain(location_id)
    if terr and terr.get("slope") is not None:
        fs.available["terrain"] = True
        for k in ("elevation", "slope", "aspect", "curvature",
                  "flow_accumulation", "drainage_density", "distance_to_drainage",
                  "relative_relief"):
            fs.values[k] = terr.get(k)
        fs.provenance["terrain"] = {"source": terr.get("source"),
                                    "realtime_class": "static",
                                    "synthetic": bool(terr.get("is_synthetic"))}
    else:
        fs.available["terrain"] = False

    # ---- Historical susceptibility ----
    susc = repo.latest_susceptibility(lat, lon)
    if susc is not None:
        fs.available["susceptibility"] = True
        fs.values["susceptibility"] = susc
    else:
        fs.available["susceptibility"] = False

    return fs
