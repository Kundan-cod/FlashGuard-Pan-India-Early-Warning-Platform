"""
Risk engine (master prompt sections 18-21, 35, 47, 48, 69).

Fuses:
  ML probability (demo models)
  + physical/environmental rules (override floors)
  + data quality / source confidence
  + historical susceptibility
into a final risk level, a SEPARATE confidence score, and an estimated
high-risk *window* (never an exact arrival time).

All thresholds here are PROTOTYPE thresholds, explicitly labelled, configurable,
and NOT presented as official government rules (section 18).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from app.features.engineer import FeatureSet
from app.ml.provider import get_model

# ---- PROTOTYPE thresholds (not official) ----------------------------------
RISK_BANDS = [(0.75, "CRITICAL"), (0.55, "HIGH"), (0.30, "MODERATE"), (0.0, "LOW")]

# Physical-rule floors: if extreme conditions co-occur, risk cannot be LOW
# regardless of the model output (section 18 worked example).
RULE_RAIN_3H_EXTREME = 80.0     # mm
RULE_SOIL_SAT_HIGH = 0.85       # index 0..1
RULE_RIVER_RISE_FAST = 0.5      # m/h


@dataclass
class RiskResult:
    location_id: int
    ts: str
    flood_probability: float
    landslide_probability: float
    risk_level: str
    confidence: float
    lead_time_min_lo: int | None
    lead_time_min_hi: int | None
    data_completeness: float
    top_factors: list = field(default_factory=list)
    model_version: str = ""
    rule_triggered: list = field(default_factory=list)
    notes: list = field(default_factory=list)
    # Phase C structured fields (additive, backwards compatible)
    flood: dict = field(default_factory=dict)
    landslide: dict = field(default_factory=dict)
    combined: dict = field(default_factory=dict)
    lead_time: dict = field(default_factory=dict)
    explanation: list = field(default_factory=list)
    data_quality: dict = field(default_factory=dict)
    model_meta: dict = field(default_factory=dict)


def _band(p: float, thr_critical: float = 0.75, thr_high: float = 0.55, thr_mod: float = 0.30) -> str:
    if p >= thr_critical:
        return "CRITICAL"
    if p >= thr_high:
        return "HIGH"
    if p >= thr_mod:
        return "MODERATE"
    return "LOW"


def _apply_rules(fs: FeatureSet, base_level: str) -> tuple[str, list]:
    """Raise the floor when extreme precursors co-occur. Returns (level, reasons)."""
    v = fs.values
    reasons = []
    rain3 = v.get("rain_3h") or 0
    intensity = v.get("rain_intensity") or 0
    soil = v.get("soil_saturation_index") or 0
    rise = v.get("river_rate_of_rise_1h") or 0

    extreme_count = 0
    if rain3 >= RULE_RAIN_3H_EXTREME:
        extreme_count += 1
        reasons.append(f"3h rainfall ≥ {RULE_RAIN_3H_EXTREME}mm (prototype physical floor rule)")
    if intensity >= 50.0:
        extreme_count += 1
        reasons.append(f"rain intensity ≥ 50mm/h (prototype physical floor rule)")
    if soil >= RULE_SOIL_SAT_HIGH:
        extreme_count += 1
        reasons.append(f"soil saturation ≥ {RULE_SOIL_SAT_HIGH} (prototype physical floor rule)")
    if rise >= RULE_RIVER_RISE_FAST:
        extreme_count += 1
        reasons.append(f"river rising ≥ {RULE_RIVER_RISE_FAST} m/h (prototype physical floor rule)")

    order = ["LOW", "MODERATE", "HIGH", "CRITICAL"]
    level = base_level
    if extreme_count >= 2:
        # floor at HIGH (or CRITICAL if 3+ indicators)
        floor = "CRITICAL" if extreme_count >= 3 else "HIGH"
        if order.index(level) < order.index(floor):
            level = floor
    return level, reasons


def _confidence(fs: FeatureSet, validated: bool = False,
                missing_critical: list | None = None,
                out_of_range: list | None = None) -> tuple[float, list]:
    """Confidence from availability + freshness + quality + model validation state.
    Kept STRICTLY SEPARATE from risk probability (section 12).
    """
    notes = []
    completeness = fs.completeness()
    conf = 0.30 + 0.45 * completeness   # scales with completeness of expected sources

    # quality penalty
    bad = sum(1 for p in fs.provenance.values()
              if p.get("quality") in ("WARNING", "BAD", "STALE"))
    if bad:
        conf -= 0.08 * bad
        notes.append(f"{bad} source(s) flagged non-GOOD telemetry quality")

    # missing critical features penalty
    if missing_critical:
        conf -= 0.06 * len(missing_critical)
        notes.append(f"critical feature(s) missing/imputed: {', '.join(missing_critical)}")

    # out of range / OOD penalty
    if out_of_range:
        conf -= 0.04 * len(out_of_range)
        notes.append(f"feature(s) outside physical expected range: {', '.join(out_of_range)}")

    # synthetic terrain note
    if fs.provenance.get("terrain", {}).get("synthetic"):
        notes.append("terrain elevation/slope is synthetic")

    # model validation state penalty: if unvalidated demo model, confidence is capped
    if not validated:
        conf = min(0.85, conf)
        notes.append("model is NOT VALIDATED on real observations (confidence capped at 0.85)")

    conf = max(0.05, min(0.99, conf))
    return conf, notes


def _lead_time(fs: FeatureSet, flood_p: float) -> tuple[int | None, int | None, str]:
    """Estimated high-risk WINDOW in minutes (section 16, 20).
    Never an exact arrival time; maps intensity + rise rate + flood probability to a window.
    Returns (lo, hi, label).
    """
    v = fs.values
    rise = v.get("river_rate_of_rise_1h")
    intensity = v.get("rain_intensity")
    if rise is None and intensity is None:
        return None, None, "UNKNOWN / NOT AVAILABLE"
    urgency = 0.0
    if rise is not None:
        urgency += min(1.0, rise / 1.5)
    if intensity is not None:
        urgency += min(1.0, intensity / 60.0)
    urgency = min(1.0, urgency / 2 + 0.5 * flood_p)
    # map urgency (0..1) to a window; higher urgency -> sooner & tighter
    if urgency >= 0.8:
        return 15, 45, "15–45 minutes (imminent surge)"
    if urgency >= 0.6:
        return 30, 60, "30–60 minutes (rapid onset)"
    if urgency >= 0.4:
        return 60, 180, "1–3 hours (developing hazard)"
    return 180, 360, "3–6 hours (watch window)"


def assess(fs: FeatureSet, mode: str = "replay") -> RiskResult:
    ts = fs.as_of or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    flood_model = get_model("flood")
    landslide_model = get_model("landslide")

    flood = flood_model.predict(fs.values)
    land = landslide_model.predict(fs.values)

    flood_cal = getattr(flood, "calibrated_probability", None) or flood.probability
    land_cal = getattr(land, "calibrated_probability", None) or land.probability
    flood_thr = getattr(flood, "operating_threshold", 0.5) or 0.5
    land_thr = getattr(land, "operating_threshold", 0.5) or 0.5

    # Determine hazard-specific risk level
    flood_risk = _band(flood_cal, thr_critical=max(0.75, flood_thr + 0.2),
                       thr_high=flood_thr, thr_mod=max(0.25, flood_thr - 0.2))
    land_risk = _band(land_cal, thr_critical=max(0.75, land_thr + 0.2),
                      thr_high=land_thr, thr_mod=max(0.25, land_thr - 0.2))

    # Multi-hazard fusion: highest of calibrated hazard probabilities
    combined_severity = max(flood_cal, land_cal)
    base_level = _band(combined_severity)
    level, rule_reasons = _apply_rules(fs, base_level)

    # Collect OOD / Schema reports
    fl_rep = getattr(flood, "schema_report", {}) or {}
    ls_rep = getattr(land, "schema_report", {}) or {}
    all_imputed = sorted(list(set(fl_rep.get("imputed", []) + ls_rep.get("imputed", []))))
    all_out_of_range = sorted(list(set(fl_rep.get("out_of_range", []) + ls_rep.get("out_of_range", []))))
    all_missing_critical = sorted(list(set(fl_rep.get("missing_critical", []) + ls_rep.get("missing_critical", []))))

    is_validated = bool(getattr(flood_model, "validated", False) and getattr(landslide_model, "validated", False))
    conf, conf_notes = _confidence(fs, validated=is_validated,
                                   missing_critical=all_missing_critical,
                                   out_of_range=all_out_of_range)
    lo, hi, window_label = _lead_time(fs, flood_cal)

    # Dominant hazard for explanation
    dominant = flood if flood_cal >= land_cal else land
    top = dominant.contributions[:5]

    # Readable explanation lines
    explanation_lines = []
    for c in top:
        factor = c.get("factor", c.get("feature", ""))
        val = c.get("contribution", 0.0)
        direction = "increasing" if val > 0 else "reducing"
        explanation_lines.append(f"{factor} ({direction} risk by {abs(val):.3f} log-odds)")

    notes = list(conf_notes)
    if is_validated:
        notes.append("VALIDATED MODEL")
    elif flood_model.version.startswith("flood-gbt") or landslide_model.version.startswith("landslide-gbt"):
        notes.append("DEMO MODEL — TRAINED (GBT) on SIMULATED data — NOT VALIDATED")
    else:
        notes.append("DEMO MODEL — NOT VALIDATED")
    if mode in ("replay", "simulation"):
        notes.append(f"{mode.upper()} data — not live observations")

    return RiskResult(
        location_id=fs.location_id, ts=ts,
        flood_probability=round(flood_cal, 4),
        landslide_probability=round(land_cal, 4),
        risk_level=level, confidence=round(conf, 3),
        lead_time_min_lo=lo, lead_time_min_hi=hi,
        data_completeness=round(fs.completeness(), 3),
        top_factors=top,
        model_version=f"{flood_model.version}+{landslide_model.version}",
        rule_triggered=rule_reasons, notes=notes,
        # Phase C detailed components
        flood={
            "hazard": "flash_flood",
            "probability": round(flood_cal, 4),
            "raw_probability": round(flood.probability, 4),
            "calibrated_probability": round(flood_cal, 4),
            "confidence": round(conf, 3),
            "risk": flood_risk,
            "threshold": round(flood_thr, 4),
            "threshold_type": "ML decision threshold",
            "drivers": getattr(flood, "drivers", None) or [c.get("raw_factor", c.get("factor")) for c in flood.contributions if c.get("contribution", 0) > 0][:4],
        },
        landslide={
            "hazard": "landslide",
            "probability": round(land_cal, 4),
            "raw_probability": round(land.probability, 4),
            "calibrated_probability": round(land_cal, 4),
            "confidence": round(conf, 3),
            "risk": land_risk,
            "threshold": round(land_thr, 4),
            "threshold_type": "ML decision threshold",
            "drivers": getattr(land, "drivers", None) or [c.get("raw_factor", c.get("factor")) for c in land.contributions if c.get("contribution", 0) > 0][:4],
        },
        combined={
            "hazard": "flash_flood" if flood_cal >= land_cal else "landslide",
            "risk": level,
            "probability": round(combined_severity, 4),
            "severity": round(combined_severity, 4),
            "confidence": round(conf, 3),
            "drivers": getattr(dominant, "drivers", None) or [c.get("raw_factor", c.get("factor")) for c in top if c.get("contribution", 0) > 0][:4],
            "rule_triggered": rule_reasons,
        },
        lead_time={
            "min_minutes": lo,
            "max_minutes": hi,
            "window_label": window_label,
        },
        explanation=explanation_lines,
        data_quality={
            "completeness": round(fs.completeness(), 3),
            "status": mode.upper(),
            "imputed": all_imputed,
            "out_of_range": all_out_of_range,
            "missing_critical": all_missing_critical,
        },
        model_meta={
            "flood_version": flood_model.version,
            "landslide_version": landslide_model.version,
            "validated": is_validated,
            "is_demo": not is_validated,
            "status": "VALIDATED" if is_validated else "NOT VALIDATED",
        },
    )

