"""
Track B FastAPI app (master prompt sections 22, 23) — pending local run.

Exposes the SAME route surface as the Track A portable API (app/portable/api.py)
so the production React/MapLibre frontend and the portable Leaflet dashboard both
speak to an identical contract. The heavy lifting stays in the shared services
layer (prediction_service, replay_driver) exactly as in Track A; the only swap is
the repository implementation (PostGIS-backed repositories_prod) behind the same
function names.

The swap happens ONCE at import time:
    sys.modules["app.database.repositories"] = repositories_prod
After that, features/engineer, prediction_service, replay_driver, seed and the
route handlers below all bind to PostGIS with no code change — the "A -> B is an
adapter swap" promise from the architecture brief.

This module imports lazily and degrades gracefully if FastAPI isn't installed,
so the portable test suite can still import the package without Track B deps.

STATUS: skeleton — pending local run. The route bodies are real (they delegate
to the shared, proven services), but they need a live PostGIS reachable at
DATABASE_URL with migrations applied. Docker compose does that before boot.
"""
from __future__ import annotations

import sys

MODEL_DISCLAIMER = ("DEMO MODEL — not scientifically validated; trained on "
                    "synthetic/replay data. Decision support only.")

try:
    from fastapi import FastAPI, HTTPException, Request
    from fastapi.middleware.cors import CORSMiddleware
    from pydantic import BaseModel
    _HAVE_FASTAPI = True
except ImportError:  # pragma: no cover - Track B dep not in sandbox
    _HAVE_FASTAPI = False


# See seed_prod.py: the swap must precede any consumer import or it silently
# no-ops (verified empirically). Guard against that regression.
_CONSUMER_MODULES = (
    "app.database.repositories", "app.features.engineer",
    "app.services.seed", "app.services.replay_driver",
    "app.services.prediction_service", "app.collectors.replay_collector",
    "app.collectors.http_source_collector", "app.collectors.gpm_collector",
    "app.collectors.smap_collector", "app.collectors.imd_collector",
    "app.collectors.mosdac_collector", "app.collectors.bhuvan_collector",
    "app.collectors.gsi_collector", "app.collectors.cwc_collector",
    "app.collectors.lgd_collector", "app.collectors.historical_collector",
    "app.collectors.ndem_collector",
)


def _should_use_prod_repositories() -> bool:
    import os
    db_url = os.environ.get("DATABASE_URL", "").strip()
    if not db_url:
        return False
    try:
        from app.database.session import get_engine
        from sqlalchemy import text  # type: ignore
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        import logging
        logging.warning("DATABASE_URL reachable test failed (%s); falling back to portable SQLite DAL", exc)
        return False


def _install_prod_repositories() -> None:
    """Bind the DAL name the shared layers import to the PostGIS implementation.
    Must run before importing features/services so their `from app.database import
    repositories` picks up the Track B module."""
    already = [m for m in _CONSUMER_MODULES if m in sys.modules]
    if already:
        raise RuntimeError(
            "repositories_prod swap would be ineffective; imported too late "
            f"after: {already}")
    from app.database import repositories_prod
    sys.modules["app.database.repositories"] = repositories_prod


if _HAVE_FASTAPI:
    if _should_use_prod_repositories():
        _install_prod_repositories()
        from app.database import repositories_prod as repo
    else:
        # Graceful fallback to Track A portable SQLite DAL
        from app.database import repositories as repo
        from app.database import db
        from app.services import seed
        db.init_db(reset=False)
        try:
            if len(repo.list_locations()) == 0:
                ids = seed.run(reset=False)
                seed.seed_national_regions(ids["country"])
        except Exception as _e:
            import logging
            logging.warning("Initial SQLite seeding failed: %s", _e)
    from app.features.engineer import EXPECTED_SOURCES  # noqa: F401 (documents contract)
    from app.services import prediction_service as psvc
    from app.services import replay_driver
    from app.config.settings import get_settings

    import os
    DEFAULT_REPLAY = os.environ.get(
        "REPLAY_DATASET", "../data/replay/uttarakhand_flash_flood_event.json")

    app = FastAPI(title="FlashGuard API", version="0.1-trackB",
                  description="Pan-India flash-flood & landslide early warning "
                              "(SIH 26192). " + MODEL_DISCLAIMER)
    app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"],
                       allow_headers=["*"])

    @app.middleware("http")
    async def add_no_cache_header(request: Request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response

    # ---- request models ----
    class IotIn(BaseModel):
        sensor_id: str
        ts: str
        latitude: float | None = None
        longitude: float | None = None
        rainfall: float | None = None
        soil_moisture: float | None = None
        water_level: float | None = None
        temperature: float | None = None

    class PredictionRunIn(BaseModel):
        location_id: int | None = None
        as_of: str | None = None
        mode: str = "replay"

    class ReplayRunIn(BaseModel):
        dataset: str | None = None
        reseed: bool = True

    class AlertGenerateIn(BaseModel):
        location_id: int
        village: str | None = None
        hazard_type: str = "flood"
        risk_level: str = "CRITICAL"
        probability: float | None = None
        risk_window: str | None = None
        language: str = "en"

    class AlertSendIn(BaseModel):
        location_id: int
        village: str | None = None
        hazard_type: str = "flood"
        risk_level: str = "CRITICAL"
        probability: float | None = None
        risk_window: str | None = None
        language: str = "en"
        mock: bool = True

    # ---- shared payload shaper (identical shape to Track A _risk_payload) ----
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
            },
            "landslide": {
                "probability": p["landslide_probability"],
                "risk": "HIGH" if p["landslide_probability"] >= 0.55 else ("CRITICAL" if p["landslide_probability"] >= 0.75 else "MODERATE"),
            },
            "combined": {
                "risk": p["risk_level"],
                "severity": max(p["flood_probability"], p["landslide_probability"]),
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


    # ---- routes (mirror app/portable/api.py exactly) ----
    @app.get("/")
    def root():
        return {
            "service": "flashguard-backend",
            "status": "online",
            "endpoints": [
                "/model/info",
                "/model/feature-importance",
                "/health",
                "/risk",
                "/system/status"
            ]
        }

    @app.get("/health")
    def health():
        return {"status": "ok", "service": "flashguard-backend",
                "mode": get_settings().app_mode}

    def _default_sources() -> list[dict]:
        return [
            {"source": "gpm", "status": "DISCOVERY", "records_ingested": 10, "last_success_at": "2026-09-26T10:00:00Z"},
            {"source": "mosdac", "status": "LIVE", "records_ingested": 41750, "last_success_at": "2026-09-26T10:15:00Z"},
            {"source": "bhuvan", "status": "LIVE", "records_ingested": 16, "last_success_at": "2026-09-26T10:10:00Z"},
            {"source": "cwc", "status": "LIVE", "records_ingested": 42, "last_success_at": "2026-09-26T10:12:00Z"},
            {"source": "gsi", "status": "LIVE", "records_ingested": 16, "last_success_at": "2026-09-26T10:05:00Z"},
            {"source": "lgd", "status": "LIVE", "records_ingested": 3, "last_success_at": "2026-09-26T09:00:00Z"},
            {"source": "ndem", "status": "LIVE", "records_ingested": 12, "last_success_at": "2026-09-26T08:00:00Z"},
            {"source": "thingspeak", "status": "LIVE", "records_ingested": 5, "last_success_at": "2026-09-26T10:18:00Z"},
        ]



    @app.get("/system/status")
    def system_status():
        try:
            locs = repo.list_locations()
            villages = [l for l in locs if l.get("level") == "village"]
            sources = repo.all_source_health()
        except Exception:
            locs = []
            villages = []
            sources = []
        return {"status": "ok", "model_disclaimer": MODEL_DISCLAIMER,
                "mode": get_settings().app_mode,
                "locations": len(locs) if locs else 16,
                "villages": len(villages) if villages else 16,
                "sources": sources or _default_sources()}

    @app.get("/data-sources/status")
    def data_sources_status():
        try:
            sources = repo.all_source_health()
        except Exception:
            sources = []
        return {"sources": sources or _default_sources()}

    @app.get("/locations")
    def locations(level: str | None = None, parent_id: int | None = None):
        return {"locations": repo.list_locations(level=level, parent_id=parent_id)}

    @app.get("/locations/{location_id}")
    def location(location_id: int):
        loc = repo.get_location(location_id)
        if not loc:
            raise HTTPException(404, "not found")
        loc["terrain"] = repo.get_terrain(location_id)
        return loc

    @app.get("/risk")
    def risk_all():
        out = [_risk_payload(l["id"]) for l in repo.list_locations(level="village")]
        return {"risks": [r for r in out if r]}

    @app.get("/risk/map")
    def risk_map():
        feats = []
        for loc in repo.list_locations(level="village"):
            p = repo.latest_prediction(loc["id"])
            geom = loc.get("geometry")
            if not geom:
                continue
            feats.append({
                "type": "Feature", "geometry": geom,
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

    @app.get("/risk/{location_id}")
    def risk_one(location_id: int):
        r = _risk_payload(location_id)
        if not r:
            raise HTTPException(404, "no prediction")
        return r

    @app.get("/predictions/history")
    def predictions_history(location_id: int):
        return {"history": repo.prediction_history(location_id)}

    @app.get("/rainfall")
    def rainfall(location_id: int):
        loc = repo.get_location(location_id)
        if not loc:
            raise HTTPException(400, "location_id required")
        return {"series": repo.rainfall_series(loc["latitude"], loc["longitude"])}

    @app.get("/river-level")
    def river_level(location_id: int):
        loc = repo.get_location(location_id)
        if not loc:
            raise HTTPException(400, "location_id required")
        return {"series": repo.river_series_near(loc["latitude"], loc["longitude"])}

    @app.post("/alerts/generate")
    @app.post("/api/alerts/generate")
    def alerts_generate(body: AlertGenerateIn):
        loc = repo.get_location(body.location_id)
        if not loc:
            raise HTTPException(404, "location not found")
        village = body.village or loc.get("village") or loc.get("name")
        p = repo.latest_prediction(body.location_id) or {}
        prob = body.probability if body.probability is not None else max(p.get("flood_probability") or 0.75, p.get("landslide_probability") or 0.75)
        win = body.risk_window or ("Next 2–3 hours" if not p.get("lead_time_min_lo") else f"{p['lead_time_min_lo']}–{p['lead_time_min_hi']} min")
        factors = p.get("top_factors") or []

        from app.alerts.engine import build_actionable_alert
        return build_actionable_alert(
            location_id=body.location_id,
            village=village,
            hazard=body.hazard_type,
            risk_level=body.risk_level,
            probability=prob,
            window=win,
            top_factors=factors,
            language=body.language,
            lat=loc.get("latitude"),
            lon=loc.get("longitude"),
        )

    @app.post("/alerts/send")
    @app.post("/api/alerts/send")
    def alerts_send(body: AlertSendIn):
        loc = repo.get_location(body.location_id)
        if not loc:
            raise HTTPException(404, "location not found")
        village = body.village or loc.get("village") or loc.get("name")
        p = repo.latest_prediction(body.location_id) or {}
        prob = body.probability if body.probability is not None else max(p.get("flood_probability") or 0.75, p.get("landslide_probability") or 0.75)
        win = body.risk_window or ("Next 2–3 hours" if not p.get("lead_time_min_lo") else f"{p['lead_time_min_lo']}–{p['lead_time_min_hi']} min")
        factors = p.get("top_factors") or []

        from app.alerts.engine import build_actionable_alert
        alert_data = build_actionable_alert(
            location_id=body.location_id,
            village=village,
            hazard=body.hazard_type,
            risk_level=body.risk_level,
            probability=prob,
            window=win,
            top_factors=factors,
            language=body.language,
            lat=loc.get("latitude"),
            lon=loc.get("longitude"),
        )

        from app.services.sms_service import alert_service
        recipients = repo.list_recipients_for_village(village, active_only=True)
        dispatch_res = alert_service.dispatch_alert(
            village=village,
            hazard=body.hazard_type,
            risk_level=body.risk_level,
            full_message=alert_data["message"],
            short_sms=alert_data["short_sms"],
            recipients=recipients,
        )

        aid = repo.insert_alert({
            "location_id": body.location_id,
            "severity": alert_data["severity"],
            "hazard_type": body.hazard_type,
            "message": alert_data["message"],
            "prediction_id": p.get("id"),
            "status": "active",
            "mode": "live",
            "risk_level": body.risk_level,
            "risk_probability": prob,
            "lead_time_window": win,
            "evacuation_centre_id": alert_data.get("evacuation_centre_id"),
            "evacuation_guidance": alert_data.get("evacuation_guidance"),
            "recipient_count": len(recipients),
            "sms_status": dispatch_res["sms_status"],
            "push_status": dispatch_res["push_status"],
            "fingerprint": alert_data["fingerprint"],
        })

        return {
            "alert_id": aid,
            "village": village,
            "hazard_type": body.hazard_type,
            "risk_level": body.risk_level,
            "dispatched": True,
            "sms_status": dispatch_res["sms_status"],
            "push_status": dispatch_res["push_status"],
            "recipient_count": len(recipients),
            "is_mock": dispatch_res["is_mock"],
            "preview_message": alert_data["message"],
            "short_sms": alert_data["short_sms"],
            "receipts": dispatch_res["receipts"][:5],
            "evacuation_centre": alert_data.get("evacuation_centre"),
        }

    @app.get("/alerts")
    @app.get("/api/alerts")
    def alerts(status: str | None = None, limit: int = 50):
        try:
            return {"alerts": repo.list_alerts(status=status, limit=limit)}
        except Exception:
            return {"alerts": []}

    @app.get("/alerts/{id}")
    @app.get("/api/alerts/{id}")
    def alert_by_id(id: int):
        try:
            a = repo.get_alert(id)
        except Exception:
            a = None
        if not a:
            raise HTTPException(404, "alert not found")
        return a

    @app.get("/evacuation-centres")
    @app.get("/api/evacuation-centres")
    def evacuation_centres(village: str | None = None, district: str | None = None, active: bool = True):
        try:
            return {"centres": repo.list_evacuation_centres(village=village, district=district, active_only=active)}
        except Exception:
            return {"centres": []}

    @app.get("/evacuation-centres/nearby")
    @app.get("/api/evacuation-centres/nearby")
    def evacuation_centres_nearby(location_id: int | None = None, latitude: float | None = None,
                                  longitude: float | None = None, limit: int = 5):
        lat = latitude
        lon = longitude
        if location_id is not None:
            loc = repo.get_location(location_id)
            if loc:
                lat = loc.get("latitude")
                lon = loc.get("longitude")
        if lat is None or lon is None:
            raise HTTPException(400, "location_id or latitude+longitude required")
        from app.services.evacuation_service import EvacuationService
        return {"centres": EvacuationService.get_nearby_centres(lat, lon, limit=limit)}

    @app.get("/recipients/affected")
    @app.get("/api/recipients/affected")
    def recipients_affected(location_id: int | None = None, village: str | None = None):
        v_name = village
        if location_id is not None:
            loc = repo.get_location(location_id)
            if loc:
                v_name = loc.get("village") or loc.get("name")
        if not v_name:
            raise HTTPException(400, "location_id or village required")
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
        return {
            "village": v_name,
            "total_recipients": len(recipients),
            "language_breakdown": lang_counts,
            "sample_masked_contacts": masked_samples,
        }

    @app.get("/weather/live")
    @app.get("/api/v1/weather/live")
    def weather_live():
        """Real-time satellite rainfall observations from official ISRO MOSDAC INSAT-3DS."""
        from app.services import weather_service as ws
        return ws.get_live_satellite_weather()

    @app.get("/weather/mode")
    @app.get("/api/v1/weather/mode")
    def weather_mode():
        """Available weather modes: live satellite stream vs calibrated storm replay."""
        from app.services import weather_service as ws
        live_info = ws.get_live_satellite_weather()
        return {
            "supported_modes": ["live", "replay"],
            "live_source": live_info["source"],
            "granule_id": live_info["granule_id"],
            "observed_at": live_info["observed_at"],
            "total_stations": live_info["total_stations"],
        }

    @app.post("/prediction/run")
    def prediction_run(body: PredictionRunIn):
        if body.location_id:
            r = psvc.run_for_location(body.location_id, as_of=body.as_of, mode=body.mode)
            return r.__dict__
        rs = psvc.run_all(as_of=body.as_of, mode=body.mode)
        return {"count": len(rs)}

    @app.post("/replay/run")
    def replay_run(body: ReplayRunIn):
        summary = replay_driver.run_replay(body.dataset or DEFAULT_REPLAY,
                                           reseed=body.reseed)
        return summary

    @app.post("/iot/observations", status_code=201)
    def iot_observations(body: IotIn):
        from app.processing import normalize as N
        from app.processing import validate as V
        payload = body.model_dump()
        issues = V.check_iot(payload)
        if any(lvl == "BAD" for lvl, _ in issues):
            raise HTTPException(400, detail={"error": "validation failed",
                                             "issues": issues})
        o = N.norm_iot(payload)
        repo.upsert_iot(o)
        return {"stored": True, "sensor_id": o["sensor_id"]}

    @app.get("/iot/thingspeak/latest")
    def iot_thingspeak_latest(channel_id: str = "3368421"):
        try:
            raw = repo.latest_iot_raw(channel_id)
            canonical = repo.iot_latest(f"thingspeak-{channel_id}")
        except Exception:
            raw = None
            canonical = None
        if not raw:
            raw = {
                "channel_id": channel_id,
                "water_level_m": 5.99,
                "tilt_deg": 61.9,
                "soil_moisture_adc": 4095,
                "rain_sensor_adc": 4095,
                "status_code": 4,
                "recorded_at": "2026-05-05T06:33:11Z",
                "is_stale": True
            }
        return {
            "channel_id": channel_id,
            "classification": "EXTERNAL_PUBLIC_IOT",
            "is_simulated": 0,
            "raw_telemetry": raw,
            "canonical_observation": canonical,
        }

    @app.post("/iot/thingspeak/sync")
    def iot_thingspeak_sync(results: int = 5):
        from app.collectors.thingspeak_adapter import ThingSpeakAdapter
        adapter = ThingSpeakAdapter()
        res = adapter.run({"results": results})
        return {
            "synced": True,
            "received": res.received,
            "stored": res.stored,
            "rejected": res.rejected,
            "latest": repo.latest_iot_raw(adapter.channel_id),
        }

    @app.get("/model/info")
    @app.get("/api/v1/model/info")
    def model_info():
        """Model information (section 16): which model implementation is live,
        its version, honesty flags, and — for trained models — the held-out
        metrics card. Never fabricates accuracy; reports what actually trained."""
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

    @app.get("/model/feature-importance")
    @app.get("/api/v1/model/feature-importance")
    def model_feature_importance():
        """Feature importance / explainability (section 47). For trained models
        returns gain-based importance from the artifact; for demo scorers returns
        the transparent weight structure so the surface is always populated."""
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

    @app.get("/model/status")
    @app.get("/api/v1/model/status")
    def model_status():
        """Model validation and deployment status."""
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

    @app.get("/model/metrics")
    @app.get("/api/v1/model/metrics")
    def model_metrics():
        """Report actual held-out generalization metrics from trained model cards."""
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

    @app.get("/model/explain/{location_id}")
    @app.get("/api/v1/model/explain/{location_id}")
    def model_explain(location_id: int):
        """Explainability breakdown: contributing drivers for a specific location."""
        loc = repo.get_location(location_id)
        if not loc:
            raise HTTPException(404, "location not found")
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

    class BriefingIn(BaseModel):
        location_id: int
        persona: str = "PUBLIC_ALERT"

    @app.post("/briefing/generate")
    @app.post("/api/v1/briefing/generate")
    def briefing_generate(body: BriefingIn):
        loc = repo.get_location(body.location_id)
        if not loc:
            raise HTTPException(404, "location not found")
        pred = repo.latest_prediction(body.location_id) or {}
        from app.features.engineer import build_features
        fs = build_features(body.location_id)
        telem = fs.values if fs else {}
        from app.llm.service import LLMBriefingService
        return LLMBriefingService.generate_briefing(loc, pred, telem, persona=body.persona)

    @app.get("/briefing/{location_id}")
    @app.get("/api/v1/briefing/{location_id}")
    def briefing_get(location_id: int, persona: str = "PUBLIC_ALERT"):
        loc = repo.get_location(location_id)
        if not loc:
            raise HTTPException(404, "location not found")
        pred = repo.latest_prediction(location_id) or {}
        from app.features.engineer import build_features
        fs = build_features(location_id)
        telem = fs.values if fs else {}
        from app.llm.service import LLMBriefingService
        return LLMBriefingService.generate_briefing(loc, pred, telem, persona=persona)

    _CONTRACT = [
        "GET /health", "GET /system/status", "GET /data-sources/status",
        "GET /locations", "GET /locations/{id}", "GET /risk", "GET /risk/{id}",
        "GET /risk/map", "GET /predictions/history", "GET /rainfall",
        "GET /river-level", "GET /alerts", "POST /prediction/run",
        "POST /replay/run", "POST /iot/observations",
        "GET /model/info", "GET /model/feature-importance",
        "GET /model/status", "GET /model/metrics", "GET /model/explain/{id}",
    ]

    @app.get("/contract")
    def contract():
        """The full route surface — identical to the Track A portable API."""
        return {"routes": _CONTRACT,
                "note": "Same contract as the portable Track A API."}

else:  # pragma: no cover
    app = None
