"""
Model provider (master prompt sections 6, 16).

Single place that decides which model implementation the risk engine uses:

  * DEMO scorers (app.models.demo_models) — the default. Transparent, always
    available, zero dependencies. Every proven Phase-1 path keeps using these
    unless explicitly opted out of.
  * TRAINED GBT artifacts (app.ml.inference.TrainedHazardModel) — used when
    USE_TRAINED_MODELS=1 AND a saved artifact exists for the hazard. Falls back
    to the demo scorer (with a logged note) if no artifact is present, so
    enabling the flag can never break inference.

Both implement the identical HazardModel interface, so the risk engine is
agnostic. This is the seam where Track B's XGBoost/LightGBM would slot in.
"""
from __future__ import annotations

import os

def _load_env_file() -> None:
    for path in (".env", "../.env", "../../.env"):
        if os.path.exists(path):
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k, v = k.strip(), v.strip()
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass
            break

_load_env_file()

from app.models.demo_models import FloodDemoModel, LandslideDemoModel

_DEMO = {"flood": FloodDemoModel, "landslide": LandslideDemoModel}

# process-level cache so we don't reload artifacts on every prediction
_cache: dict = {}


def use_trained() -> bool:
    val = os.environ.get("USE_TRAINED_MODELS")
    if val is not None:
        return val.strip().lower() in ("1", "true", "yes", "on")
    # Auto-detect: if trained model artifacts are present on disk, use them
    try:
        from app.ml import artifact as A
        return A.latest_path("flood") is not None and A.latest_path("landslide") is not None
    except Exception:
        return False


def get_model(hazard: str):
    """Return a HazardModel for `hazard`. Trained if enabled+available, else demo."""
    key = (hazard, use_trained())
    if key in _cache:
        return _cache[key]

    model = None
    if use_trained():
        try:
            from app.ml.inference import TrainedHazardModel
            model = TrainedHazardModel.load_latest(hazard)
        except Exception as exc:  # missing artifact / bad schema -> safe fallback
            import logging
            logging.getLogger("flashguard.ml").warning(
                "trained model for %s unavailable (%s); falling back to demo scorer",
                hazard, exc)
            model = None

    if model is None:
        model = _DEMO[hazard]()

    _cache[key] = model
    return model


def reset_cache() -> None:
    """Clear the model cache (tests toggle USE_TRAINED_MODELS between cases)."""
    _cache.clear()
