"""
Prediction service — orchestrates feature build -> risk assess -> persist ->
alert (master prompt sections 19, 22). Called by the API (/prediction/run) and
by the replay driver. Keeps expensive logic OUT of the HTTP handler path
(section 55: no heavy work in request handlers beyond invoking this service).
"""
from __future__ import annotations

from app.features.engineer import build_features
from app.risk.engine import assess, RiskResult
from app.alerts.engine import build_alert
from app.database import repositories as repo


def run_for_location(location_id: int, as_of: str | None = None,
                     mode: str = "replay", emit_alert: bool = True) -> RiskResult:
    fs = build_features(location_id, as_of=as_of)
    result = assess(fs, mode=mode)

    pid = repo.insert_prediction({
        "location_id": result.location_id, "ts": result.ts, "horizon": "now",
        "flood_probability": result.flood_probability,
        "landslide_probability": result.landslide_probability,
        "risk_level": result.risk_level, "confidence": result.confidence,
        "lead_time_min_lo": result.lead_time_min_lo,
        "lead_time_min_hi": result.lead_time_min_hi,
        "data_completeness": result.data_completeness,
        "top_factors": result.top_factors, "model_version": result.model_version,
        "mode": mode,
    })

    if emit_alert:
        loc = repo.get_location(location_id)
        alert = build_alert(result, loc["name"] if loc else f"loc-{location_id}")
        if alert:
            alert["prediction_id"] = pid
            alert["mode"] = mode
            repo.insert_alert(alert)

    return result


def run_all(as_of: str | None = None, mode: str = "replay") -> list[RiskResult]:
    results = []
    for loc in repo.list_locations(level="village"):
        results.append(run_for_location(loc["id"], as_of=as_of, mode=mode))
    return results
