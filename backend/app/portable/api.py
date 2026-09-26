"""
Track A portable HTTP API (stdlib http.server only) — master prompt section 23.

Implements the same route surface as the Track B FastAPI app so the frontend is
identical against either. JSON in/out, CORS enabled for the local dashboard.
No external dependencies.

Routes:
  GET  /health
  GET  /system/status
  GET  /data-sources/status
  GET  /locations                         ?level=&parent_id=
  GET  /locations/{id}
  GET  /risk                              (all latest village predictions)
  GET  /risk/{location_id}
  GET  /risk/map                          (GeoJSON FeatureCollection w/ risk)
  GET  /predictions/history?location_id=
  GET  /rainfall?location_id=
  GET  /river-level?location_id=
  GET  /alerts
  POST /prediction/run                    {location_id?, as_of?, mode?}
  POST /replay/run                        {dataset?, reseed?}
  POST /iot/observations                  {sensor_id, ts, ...}
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Ensure backend root directory is in sys.path regardless of how the script is launched
_backend_dir = str(Path(__file__).resolve().parent.parent.parent)
if _backend_dir not in sys.path:
    sys.path.insert(0, _backend_dir)

# Load .env file (project root or backend root) so GEMINI_API_KEY etc. are available
def _load_dotenv():
    """Minimal .env loader — no external dependencies."""
    for candidate in [Path(_backend_dir).parent / ".env", Path(_backend_dir) / ".env"]:
        if candidate.is_file():
            with open(candidate, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    key, _, val = line.partition("=")
                    key, val = key.strip(), val.strip()
                    if key and key not in os.environ:
                        os.environ[key] = val
            break

_load_dotenv()

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

from app.database import db, repositories as repo
from app.features.engineer import build_features, EXPECTED_SOURCES
from app.services import prediction_service as psvc
from app.services import replay_driver

MODEL_DISCLAIMER = ("DEMO MODEL — not scientifically validated; trained on "
                    "synthetic/replay data. Decision support only.")
DEFAULT_REPLAY = "../data/replay/uttarakhand_flash_flood_event.json"


def _risk_payload(location_id: int) -> dict | None:
    p = repo.latest_prediction(location_id)
    loc = repo.get_location(location_id)
    if not p or not loc:
        return None
    
    top_factors = p.get("top_factors", [])
    explanation = [
        f"{tf.get('factor', tf.get('feature', ''))} (contribution: {tf.get('contribution', 0):+.3f})"
        for tf in top_factors
    ]

    return {
        # Core identification & spatial
        "location_id": location_id, "name": loc["name"], "level": loc["level"],
        "state": loc.get("state"), "district": loc.get("district"),
        "latitude": loc.get("latitude"), "longitude": loc.get("longitude"),
        "ts": p["ts"],
        
        # Backward-compatible scalar metrics
        "flood_probability": p["flood_probability"],
        "landslide_probability": p["landslide_probability"],
        "risk_level": p["risk_level"],
        "confidence": p["confidence"],
        "lead_time_min_lo": p["lead_time_min_lo"],
        "lead_time_min_hi": p["lead_time_min_hi"],
        "data_completeness": p["data_completeness"],
        "top_factors": top_factors,
        "model_version": p["model_version"],
        "mode": p["mode"],
        "is_synthetic": bool(loc.get("is_synthetic")),

        # Phase C structured AI blocks (master prompt section 20)
        "flood": {
            "probability": p["flood_probability"],
            "risk": "HIGH" if p["flood_probability"] >= 0.55 else ("CRITICAL" if p["flood_probability"] >= 0.75 else "MODERATE"),
            "drivers": [f.get("raw_factor", f.get("factor", "")) for f in top_factors if isinstance(f, dict)][:3],
        },
        "landslide": {
            "probability": p["landslide_probability"],
            "risk": "HIGH" if p["landslide_probability"] >= 0.55 else ("CRITICAL" if p["landslide_probability"] >= 0.75 else "MODERATE"),
            "drivers": [f.get("raw_factor", f.get("factor", "")) for f in top_factors if isinstance(f, dict)][:3],
        },
        "combined": {
            "risk": p["risk_level"],
            "severity": max(p["flood_probability"], p["landslide_probability"]),
            "drivers": [f.get("raw_factor", f.get("factor", "")) for f in top_factors if isinstance(f, dict)][:4],
        },
        "lead_time": {
            "min_minutes": p["lead_time_min_lo"],
            "max_minutes": p["lead_time_min_hi"],
            "window_label": (
                f"{p['lead_time_min_lo']}–{p['lead_time_min_hi']} minutes"
                if p["lead_time_min_lo"] is not None else "UNKNOWN / NOT AVAILABLE"
            ),
        },
        "explanation": explanation,
        "data_quality": {
            "completeness": p["data_completeness"],
            "status": str(p.get("mode", "REPLAY")).upper(),
        },
        "model": {
            "version": p["model_version"],
            "validated": False,
            "status": "NOT VALIDATED",
        },
    }



class Handler(BaseHTTPRequestHandler):
    server_version = "FlashGuardPortable/0.1"

    # ---- helpers ----
    def _send(self, code: int, payload) -> None:
        body = json.dumps(payload, default=str).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-cache, no-store, must-revalidate")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", 0) or 0)
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n).decode("utf-8"))
        except json.JSONDecodeError:
            return {}

    def log_message(self, fmt, *args):  # quieter logging
        return

    def do_OPTIONS(self):
        self._send(204, {})

    # ---- routing ----
    def do_GET(self):
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "api" and parts[1] == "v1":
            parts = parts[2:]
        q = parse_qs(u.query)
        try:
            if not parts:
                return self._send(200, {
                    "service": "flashguard-portable",
                    "status": "online",
                    "endpoints": [
                        "/model/info",
                        "/model/feature-importance",
                        "/health",
                        "/risk",
                        "/system/status"
                    ]
                })

            if parts == ["health"]:
                return self._send(200, {"status": "ok", "service": "flashguard-portable"})

            if parts == ["system", "status"]:
                return self._send(200, {
                    "status": "ok",
                    "mode_note": "Portable Track-A core (stdlib). Demo/replay data.",
                    "model_disclaimer": MODEL_DISCLAIMER,
                    "locations": len(repo.list_locations()),
                    "villages": len(repo.list_locations(level="village")),
                    "sources": repo.all_source_health(),
                })

            if parts == ["data-sources", "status"]:
                return self._send(200, {"sources": repo.all_source_health()})

            if parts == ["locations"]:
                level = q.get("level", [None])[0]
                parent = q.get("parent_id", [None])[0]
                locs = repo.list_locations(level=level,
                                           parent_id=int(parent) if parent else None)
                for l in locs:
                    l.pop("geometry_geojson", None)
                return self._send(200, {"locations": locs})

            if len(parts) == 2 and parts[0] == "locations":
                loc = repo.get_location(int(parts[1]))
                if not loc:
                    return self._send(404, {"error": "not found"})
                loc["terrain"] = repo.get_terrain(int(parts[1]))
                return self._send(200, loc)

            if parts == ["risk"]:
                out = [_risk_payload(l["id"]) for l in repo.list_locations(level="village")]
                return self._send(200, {"risks": [r for r in out if r]})

            if len(parts) == 2 and parts[0] == "risk" and parts[1] != "map":
                r = _risk_payload(int(parts[1]))
                return self._send(200, r or {"error": "no prediction"})

            if parts == ["risk", "map"]:
                return self._send(200, self._risk_map())

            if parts == ["predictions", "history"]:
                lid = q.get("location_id", [None])[0]
                if not lid:
                    return self._send(400, {"error": "location_id required"})
                return self._send(200, {"history": repo.prediction_history(int(lid))})

            if parts == ["rainfall"]:
                lid = q.get("location_id", [None])[0]
                loc = repo.get_location(int(lid)) if lid else None
                if not loc:
                    return self._send(400, {"error": "location_id required"})
                return self._send(200, {"series": repo.rainfall_series(
                    loc["latitude"], loc["longitude"])})

            if parts == ["river-level"]:
                lid = q.get("location_id", [None])[0]
                loc = repo.get_location(int(lid)) if lid else None
                if not loc:
                    return self._send(400, {"error": "location_id required"})
                return self._send(200, {"series": repo.river_series_near(
                    loc["latitude"], loc["longitude"])})

            if parts in (["alerts"], ["api", "alerts"]):
                status = q.get("status", [None])[0]
                limit = int(q.get("limit", [50])[0])
                return self._send(200, {"alerts": repo.list_alerts(status=status, limit=limit)})

            if len(parts) >= 2 and parts[-2] == "alerts" and parts[-1].isdigit():
                a = repo.get_alert(int(parts[-1]))
                if not a:
                    return self._send(404, {"error": "alert not found"})
                return self._send(200, a)

            if parts in (["evacuation-centres"], ["api", "evacuation-centres"]):
                v = q.get("village", [None])[0]
                d = q.get("district", [None])[0]
                act = q.get("active", ["true"])[0].lower() == "true"
                return self._send(200, {"centres": repo.list_evacuation_centres(village=v, district=d, active_only=act)})

            if parts in (["evacuation-centres", "nearby"], ["api", "evacuation-centres", "nearby"]):
                loc_id_s = q.get("location_id", [None])[0]
                lat_s = q.get("latitude", [None])[0]
                lon_s = q.get("longitude", [None])[0]
                limit = int(q.get("limit", [5])[0])
                lat = float(lat_s) if lat_s is not None else None
                lon = float(lon_s) if lon_s is not None else None
                if loc_id_s is not None:
                    loc = repo.get_location(int(loc_id_s))
                    if loc:
                        lat = loc.get("latitude")
                        lon = loc.get("longitude")
                if lat is None or lon is None:
                    return self._send(400, {"error": "location_id or latitude+longitude required"})
                from app.services.evacuation_service import EvacuationService
                return self._send(200, {"centres": EvacuationService.get_nearby_centres(lat, lon, limit=limit)})

            if parts in (["recipients", "affected"], ["api", "recipients", "affected"]):
                loc_id_s = q.get("location_id", [None])[0]
                v_name = q.get("village", [None])[0]
                if loc_id_s is not None:
                    loc = repo.get_location(int(loc_id_s))
                    if loc:
                        v_name = loc.get("village") or loc.get("name")
                if not v_name:
                    return self._send(400, {"error": "location_id or village required"})
                recipients = repo.list_recipients_for_village(v_name, active_only=True)
                from app.services.sms_service import mask_phone_number
                lang_counts = {"en": 0, "hi": 0, "ta": 0}
                masked_samples = []
                for r in recipients:
                    l = r.get("preferred_language", "en")
                    lang_counts[l] = lang_counts.get(l, 0) + 1
                    if len(masked_samples) < 5:
                        masked_samples.append({
                            "name": r.get("name"),
                            "masked_phone": mask_phone_number(r.get("phone_number", "")),
                            "language": l,
                        })
                return self._send(200, {
                    "village": v_name,
                    "total_recipients": len(recipients),
                    "language_breakdown": lang_counts,
                    "sample_masked_contacts": masked_samples,
                })

            if len(parts) == 2 and parts[0] == "briefing":
                loc_id = int(parts[1])
                persona = q.get("persona", ["PUBLIC_ALERT"])[0]
                loc = repo.get_location(loc_id)
                if not loc:
                    return self._send(404, {"error": "location not found"})
                pred = repo.latest_prediction(loc_id) or {}
                fs = build_features(loc_id)
                telem = fs.values if fs else {}
                from app.llm.service import LLMBriefingService
                res = LLMBriefingService.generate_briefing(loc, pred, telem, persona=persona)
                return self._send(200, res)

            if parts == ["model", "info"]:
                return self._send(200, self._model_info())

            if parts == ["model", "feature-importance"]:
                return self._send(200, self._model_feature_importance())

            if parts == ["model", "status"]:
                return self._send(200, self._model_status())

            if parts == ["model", "metrics"]:
                return self._send(200, self._model_metrics())

            if len(parts) == 3 and parts[0] == "model" and parts[1] == "explain":
                return self._send(200, self._model_explain(int(parts[2])))

            if parts == ["weather", "live"]:
                from app.services import weather_service as ws
                return self._send(200, ws.get_live_satellite_weather())

            if parts == ["weather", "mode"]:
                from app.services import weather_service as ws
                live_info = ws.get_live_satellite_weather()
                return self._send(200, {
                    "supported_modes": ["live", "replay"],
                    "live_source": live_info["source"],
                    "granule_id": live_info["granule_id"],
                    "observed_at": live_info["observed_at"],
                    "total_stations": live_info["total_stations"],
                })

            if parts == ["iot", "thingspeak", "latest"]:
                cid = q.get("channel_id", ["3368421"])[0]
                raw = repo.latest_iot_raw(cid)
                canonical = repo.iot_latest(f"thingspeak-{cid}")
                return self._send(200, {
                    "channel_id": cid,
                    "classification": "EXTERNAL_PUBLIC_IOT",
                    "is_simulated": 0,
                    "raw_telemetry": raw,
                    "canonical_observation": canonical,
                })

            return self._send(404, {"error": f"no route for /{'/'.join(parts)}"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        parts = [p for p in u.path.split("/") if p]
        if len(parts) >= 2 and parts[0] == "api" and parts[1] == "v1":
            parts = parts[2:]
        body = self._body()
        try:
            if parts == ["prediction", "run"]:
                mode = body.get("mode", "replay")
                if body.get("location_id"):
                    r = psvc.run_for_location(int(body["location_id"]),
                                              as_of=body.get("as_of"), mode=mode)
                    return self._send(200, r.__dict__)
                rs = psvc.run_all(as_of=body.get("as_of"), mode=mode)
                return self._send(200, {"count": len(rs)})

            if parts == ["replay", "run"]:
                dataset = body.get("dataset", DEFAULT_REPLAY)
                summary = replay_driver.run_replay(dataset,
                                                   reseed=body.get("reseed", True))
                return self._send(200, summary)

            if parts == ["iot", "observations"]:
                from app.processing import normalize as N
                from app.processing import validate as V
                issues = V.check_iot(body)
                if any(lvl == "BAD" for lvl, _ in issues):
                    return self._send(400, {"error": "validation failed",
                                            "issues": issues})
                o = N.norm_iot(body)
                repo.upsert_iot(o)
                return self._send(201, {"stored": True, "sensor_id": o["sensor_id"]})

            if parts == ["iot", "thingspeak", "sync"]:
                from app.collectors.thingspeak_adapter import ThingSpeakAdapter
                adapter = ThingSpeakAdapter()
                res = adapter.run({"results": int(body.get("results", 5))})
                return self._send(200, {
                    "synced": True,
                    "received": res.received,
                    "stored": res.stored,
                    "rejected": res.rejected,
                    "latest": repo.latest_iot_raw(adapter.channel_id),
                })

            if parts == ["briefing", "generate"]:
                loc_id = int(body.get("location_id", 1))
                persona = body.get("persona", "PUBLIC_ALERT")
                loc = repo.get_location(loc_id)
                if not loc:
                    return self._send(404, {"error": "location not found"})
                pred = repo.latest_prediction(loc_id) or {}
                fs = build_features(loc_id)
                telem = fs.values if fs else {}
                from app.llm.service import LLMBriefingService
                res = LLMBriefingService.generate_briefing(loc, pred, telem, persona=persona)
                return self._send(200, res)

            if parts in (["alerts", "generate"], ["api", "alerts", "generate"]):
                loc_id = int(body.get("location_id", 1))
                loc = repo.get_location(loc_id)
                if not loc:
                    return self._send(404, {"error": "location not found"})
                village = body.get("village") or loc.get("village") or loc.get("name")
                p = repo.latest_prediction(loc_id) or {}
                prob = float(body.get("probability")) if body.get("probability") is not None else max(p.get("flood_probability") or 0.75, p.get("landslide_probability") or 0.75)
                win = body.get("risk_window") or ("Next 2–3 hours" if not p.get("lead_time_min_lo") else f"{p['lead_time_min_lo']}–{p['lead_time_min_hi']} min")
                factors = p.get("top_factors") or []

                from app.alerts.engine import build_actionable_alert
                alert_res = build_actionable_alert(
                    location_id=loc_id,
                    village=village,
                    hazard=body.get("hazard_type", "flood"),
                    risk_level=body.get("risk_level", "CRITICAL"),
                    probability=prob,
                    window=win,
                    top_factors=factors,
                    language=body.get("language", "en"),
                    lat=loc.get("latitude"),
                    lon=loc.get("longitude"),
                )
                return self._send(200, alert_res)

            if parts in (["alerts", "send"], ["api", "alerts", "send"]):
                loc_id = int(body.get("location_id", 1))
                loc = repo.get_location(loc_id)
                if not loc:
                    return self._send(404, {"error": "location not found"})
                village = body.get("village") or loc.get("village") or loc.get("name")
                p = repo.latest_prediction(loc_id) or {}
                prob = float(body.get("probability")) if body.get("probability") is not None else max(p.get("flood_probability") or 0.75, p.get("landslide_probability") or 0.75)
                win = body.get("risk_window") or ("Next 2–3 hours" if not p.get("lead_time_min_lo") else f"{p['lead_time_min_lo']}–{p['lead_time_min_hi']} min")
                factors = p.get("top_factors") or []
                haz = body.get("hazard_type", "flood")
                r_level = body.get("risk_level", "CRITICAL")

                from app.alerts.engine import build_actionable_alert
                alert_data = build_actionable_alert(
                    location_id=loc_id,
                    village=village,
                    hazard=haz,
                    risk_level=r_level,
                    probability=prob,
                    window=win,
                    top_factors=factors,
                    language=body.get("language", "en"),
                    lat=loc.get("latitude"),
                    lon=loc.get("longitude"),
                )

                from app.services.sms_service import alert_service
                recipients = repo.list_recipients_for_village(village, active_only=True)
                dispatch_res = alert_service.dispatch_alert(
                    village=village,
                    hazard=haz,
                    risk_level=r_level,
                    full_message=alert_data["message"],
                    short_sms=alert_data["short_sms"],
                    recipients=recipients,
                )

                aid = repo.insert_alert({
                    "location_id": loc_id,
                    "severity": alert_data["severity"],
                    "hazard_type": haz,
                    "message": alert_data["message"],
                    "prediction_id": p.get("id"),
                    "status": "active",
                    "mode": "live",
                    "risk_level": r_level,
                    "risk_probability": prob,
                    "lead_time_window": win,
                    "evacuation_centre_id": alert_data.get("evacuation_centre_id"),
                    "evacuation_guidance": alert_data.get("evacuation_guidance"),
                    "recipient_count": len(recipients),
                    "sms_status": dispatch_res["sms_status"],
                    "push_status": dispatch_res["push_status"],
                    "fingerprint": alert_data["fingerprint"],
                })

                return self._send(200, {
                    "alert_id": aid,
                    "village": village,
                    "hazard_type": haz,
                    "risk_level": r_level,
                    "dispatched": True,
                    "sms_status": dispatch_res["sms_status"],
                    "push_status": dispatch_res["push_status"],
                    "recipient_count": len(recipients),
                    "is_mock": dispatch_res["is_mock"],
                    "preview_message": alert_data["message"],
                    "short_sms": alert_data["short_sms"],
                    "receipts": dispatch_res["receipts"][:5],
                    "evacuation_centre": alert_data.get("evacuation_centre"),
                })

            return self._send(404, {"error": f"no route for POST /{'/'.join(parts)}"})
        except Exception as e:  # noqa: BLE001
            return self._send(500, {"error": f"{type(e).__name__}: {e}"})

    # ---- risk map as GeoJSON ----
    def _risk_map(self) -> dict:
        feats = []
        for loc in repo.list_locations(level="village"):
            p = repo.latest_prediction(loc["id"])
            geom = loc.get("geometry")
            if not geom:
                continue
            feats.append({
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "location_id": loc["id"], "name": loc["name"],
                    "risk_level": p["risk_level"] if p else "UNKNOWN",
                    "flood_probability": p["flood_probability"] if p else None,
                    "landslide_probability": p["landslide_probability"] if p else None,
                    "confidence": p["confidence"] if p else None,
                    "is_synthetic": bool(loc.get("is_synthetic")),
                },
            })
        return {"type": "FeatureCollection", "features": feats,
                "meta": {"model_disclaimer": MODEL_DISCLAIMER}}

    # ---- model info / explainability (section 16, 47) ----
    def _model_info(self) -> dict:
        from app.ml.provider import get_model, use_trained
        out = {"use_trained_models": use_trained(), "hazards": {}}
        for hazard in ("flood", "landslide"):
            m = get_model(hazard)
            entry = {
                "version": m.version,
                "validated": bool(getattr(m, "validated", False)),
                "is_demo": m.is_demo() if hasattr(m, "is_demo") else True,
                "implementation": type(m).__name__,
            }
            card = getattr(m, "card", None)
            if callable(card):
                entry["card"] = m.card()
            out["hazards"][hazard] = entry
        return out

    def _model_feature_importance(self) -> dict:
        from app.ml.provider import get_model
        out = {}
        for hazard in ("flood", "landslide"):
            m = get_model(hazard)
            art = getattr(m, "_art", None)
            if art and "feature_importance" in art:
                out[hazard] = {"type": "gain", "features": art["feature_importance"]}
            else:
                out[hazard] = {"type": "demo-weights",
                               "note": "transparent demo scorer; see /model/info"}
        return out

    def _model_status(self) -> dict:
        from app.ml.provider import get_model, use_trained
        models_out = {}
        for hazard in ("flood", "landslide"):
            m = get_model(hazard)
            val = bool(getattr(m, "validated", False))
            models_out[hazard] = {
                "version": m.version,
                "validated": val,
                "status": "VALIDATED" if val else "NOT VALIDATED",
                "is_demo": m.is_demo() if hasattr(m, "is_demo") else True,
                "operating_threshold": getattr(m, "operating_threshold", 0.5),
                "implementation": type(m).__name__,
            }
        return {
            "status": "ok",
            "use_trained_models": use_trained(),
            "models": models_out,
            "disclaimer": MODEL_DISCLAIMER,
        }

    def _model_metrics(self) -> dict:
        from app.ml.provider import get_model
        out = {}
        for hazard in ("flood", "landslide"):
            m = get_model(hazard)
            card = m.card() if callable(getattr(m, "card", None)) else {}
            out[hazard] = {
                "hazard": hazard,
                "version": m.version,
                "status": card.get("status", "NOT VALIDATED"),
                "validated": card.get("validated", False),
                "data_source": card.get("data_source", "SIMULATED"),
                "operating_threshold": card.get("validation_metrics", {}).get("threshold", getattr(m, "operating_threshold", 0.5)),
                "validation_metrics": card.get("validation_metrics", {}),
                "test_metrics": card.get("test_metrics", {}),
                "calibration_summary": card.get("calibration_summary", {}),
                "samples": {
                    "total": card.get("n_samples"),
                    "train": card.get("n_train"),
                    "validation": card.get("n_val"),
                    "test": card.get("n_test"),
                    "class_balance": card.get("class_balance"),
                },
            }
        return out

    def _model_explain(self, location_id: int) -> dict:
        loc = repo.get_location(location_id)
        if not loc:
            return {"error": "location not found"}
        from app.features.engineer import build_features
        from app.risk.engine import assess
        fs = build_features(location_id)
        res = assess(fs)
        return {
            "location_id": location_id,
            "name": loc.get("name"),
            "risk_level": res.risk_level,
            "flood": res.flood,
            "landslide": res.landslide,
            "combined": res.combined,
            "explanation": res.explanation,
            "top_factors": res.top_factors,
            "data_quality": res.data_quality,
        }


def serve(host: str = "127.0.0.1", port: int = 8000):
    httpd = ThreadingHTTPServer((host, port), Handler)
    print(f"FlashGuard portable API on http://{host}:{port}")
    httpd.serve_forever()


if __name__ == "__main__":
    serve()

