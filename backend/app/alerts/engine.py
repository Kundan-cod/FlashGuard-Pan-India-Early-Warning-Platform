"""
Alert engine (master prompt section 28, 48; SIH 26192 Alert & Evacuation Guidance).

Maps risk results to actionable, multi-language alerts and evacuation guidance.
Adheres to strict safety rules:
1. Decision support only — always defer to official disaster management authorities.
2. Deduplication & Escalation: suppresses duplicate SMS if risk is unchanged; escalates
   priority on MODERATE -> HIGH or HIGH -> CRITICAL transitions.
3. LOW risk: logged to dashboard only; SMS suppressed.
4. Integrates verified evacuation centres and multi-language predefined safety templates.
"""
from __future__ import annotations

import hashlib
from typing import Dict, Any, Optional, Tuple
from app.risk.engine import RiskResult
from app.alerts.templates import render_alert_message, render_short_sms, SUPPORTED_LANGUAGES
from app.services.evacuation_service import EvacuationService
from app.database import repositories as repo


# Severity hierarchy for escalation check
RISK_RANK = {
    "LOW": 0,
    "MODERATE": 1,
    "HIGH": 2,
    "CRITICAL": 3,
}


def _alert_severity(r: RiskResult) -> str | None:
    p = max(r.flood_probability, r.landslide_probability)
    if r.risk_level == "CRITICAL" or p >= 0.75:
        return "CRITICAL"
    if r.risk_level == "HIGH" or p >= 0.55:
        return "WARNING"
    if r.risk_level == "MODERATE" or p >= 0.30:
        return "WATCH"
    return None  # LOW -> no alert (INFO only on demand)


def generate_alert_fingerprint(village: str, hazard: str, risk_level: str, window: str) -> str:
    """Generate deterministic fingerprint for deduplication."""
    raw = f"{village.strip().lower()}|{hazard.strip().lower()}|{risk_level.strip().upper()}|{window.strip().lower()}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def should_dispatch_alert(
    location_id: int,
    village: str,
    hazard: str,
    risk_level: str,
    window: str,
) -> Tuple[bool, str]:
    """Check alert deduplication and escalation policy.
    Returns (should_dispatch: bool, reason: str).
    """
    risk = risk_level.upper()
    if risk == "LOW":
        return False, "LOW risk — logged to dashboard only; emergency SMS suppressed"

    fp = generate_alert_fingerprint(village, hazard, risk, window)
    existing = repo.get_latest_active_alert_by_fingerprint(fp)
    if existing:
        return False, f"Duplicate alert suppressed — active alert #{existing['id']} already exists for {risk_level} {hazard}"

    # Check for escalation: find the most recent active alert for this location
    active_alerts = repo.active_alerts()
    loc_alerts = [a for a in active_alerts if a.get("location_id") == location_id]
    if loc_alerts:
        prev = loc_alerts[0]
        prev_risk = prev.get("risk_level") or ("CRITICAL" if prev.get("severity") == "CRITICAL" else "HIGH" if prev.get("severity") == "WARNING" else "MODERATE")
        prev_rank = RISK_RANK.get(prev_risk.upper(), 0)
        curr_rank = RISK_RANK.get(risk, 0)
        if curr_rank > prev_rank:
            return True, f"Priority escalation dispatch ({prev_risk} -> {risk})"

    return True, "Initial hazard detection dispatch"


def build_actionable_alert(
    location_id: int,
    village: str,
    hazard: str = "flood",
    risk_level: str = "CRITICAL",
    probability: float = 0.85,
    window: str = "Next 2–3 hours",
    top_factors: list | None = None,
    language: str = "en",
    lat: Optional[float] = None,
    lon: Optional[float] = None,
) -> Dict[str, Any]:
    """Build comprehensive, actionable alert with multi-language templates and verified shelter."""
    risk = risk_level.upper() if risk_level else "MODERATE"
    haz = hazard.lower() if hazard in ("flood", "landslide", "combined") else "flood"
    factors = top_factors or []
    lang = language.lower() if language in SUPPORTED_LANGUAGES else "en"

    # 1. Resolve nearest verified evacuation shelter
    evac_info = EvacuationService.get_evacuation_guidance(
        village=village,
        hazard=haz,
        risk_level=risk,
        lat=lat,
        lon=lon,
    )
    shelter = evac_info.get("shelter")

    # 2. Render multi-language messages
    messages = {
        l: render_alert_message(
            village=village,
            hazard=haz,
            risk_level=risk,
            probability=probability,
            window=window,
            language=l,
            shelter=shelter,
        )
        for l in SUPPORTED_LANGUAGES
    }

    # 3. Short SMS payload (160 chars)
    short_sms = render_short_sms(
        village=village,
        hazard=haz,
        risk_level=risk,
        window=window,
        shelter_name=shelter["name"] if shelter else None,
        language=lang,
    )

    # 4. Count affected recipients
    recipient_count = repo.count_recipients_for_village(village, active_only=True)

    # 5. Deduplication check
    fp = generate_alert_fingerprint(village, haz, risk, window)
    should_send, reason = should_dispatch_alert(location_id, village, haz, risk, window)

    # Backward-compatible severity mapping
    severity_map = {"CRITICAL": "CRITICAL", "HIGH": "WARNING", "MODERATE": "WATCH", "LOW": "INFO"}
    sev = severity_map.get(risk, "WATCH")

    return {
        "location_id": location_id,
        "village": village,
        "hazard_type": haz,
        "risk_level": risk,
        "severity": sev,
        "probability": probability,
        "risk_window": window,
        "evacuation_centre": shelter,
        "evacuation_centre_id": shelter["id"] if shelter else None,
        "evacuation_guidance": evac_info["guidance_text"],
        "has_verified_shelter": evac_info["has_verified_shelter"],
        "messages": messages,
        "message": messages[lang],
        "short_sms": short_sms,
        "language": lang,
        "recipient_count": recipient_count,
        "fingerprint": fp,
        "should_dispatch": should_send,
        "dispatch_reason": reason,
        "factors": factors,
    }


def build_alert(r: RiskResult, location_name: str) -> dict | None:
    """Backward-compatible alert builder called by prediction_service."""
    sev = _alert_severity(r)
    if sev is None:
        return None
    hazard = "flood" if r.flood_probability >= r.landslide_probability else "landslide"
    prob = r.flood_probability if hazard == "flood" else r.landslide_probability

    window = ""
    if r.lead_time_min_lo is not None:
        window = f" Estimated high-risk window ~{r.lead_time_min_lo}-{r.lead_time_min_hi} min."
    reasons = "; ".join(f["factor"] for f in r.top_factors[:3]) or "multiple factors"

    msg = (
        f"[{sev}] Estimated {hazard} risk {int(prob*100)}% at {location_name}. "
        f"Confidence {int(r.confidence*100)}% (data {int(r.data_completeness*100)}%)."
        f"{window} Main factors: {reasons}. "
        f"Decision support only — follow official NDRF/SDRF/district instructions."
    )

    # Enrich with actionable evacuation details
    win_str = f"{r.lead_time_min_lo}–{r.lead_time_min_hi} min" if r.lead_time_min_lo else "Next 2–3 hours"
    evac = EvacuationService.get_evacuation_guidance(location_name, hazard, r.risk_level)
    shelter = evac.get("shelter")
    fp = generate_alert_fingerprint(location_name, hazard, r.risk_level, win_str)

    return {
        "location_id": r.location_id,
        "severity": sev,
        "hazard_type": hazard,
        "message": msg,
        "risk_level": r.risk_level,
        "risk_probability": prob,
        "lead_time_window": win_str,
        "evacuation_centre_id": shelter["id"] if shelter else None,
        "evacuation_guidance": evac["guidance_text"],
        "recipient_count": repo.count_recipients_for_village(location_name),
        "fingerprint": fp,
        "sms_status": "MOCK_SENT" if r.risk_level in ("HIGH", "CRITICAL") else "PENDING",
    }
