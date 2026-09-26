"""
Training pipeline: train -> validate -> test -> version -> save
(master prompt section 6).

Deterministic three-way split (train/validation/test) with a fixed seed so the
whole run is reproducible (section 66). The validation split is used ONLY to
select the operating threshold (recall-weighted, section 35); the test split is
touched ONCE at the end to produce the reported metrics — so the numbers in the
model card are honest held-out generalization, never training-set scores.

*** The shipped model trains on SIMULATED data (app.ml.dataset). The model card
records source="SIMULATED", validated=False. No real-world accuracy is claimed. ***
"""
from __future__ import annotations

from datetime import datetime, timezone

import numpy as np

from app.ml import artifact as A
from app.ml import metrics as MET
from app.ml.calibration import PlattCalibrator, expected_calibration_error
from app.ml.dataset import Dataset, generate, inspect_available_historical_data
from app.ml.gbt import GBTClassifier
from app.ml.schema import get_schema


def _split(n: int, seed: int, ratios=(0.6, 0.2, 0.2)):
    rng = np.random.RandomState(seed)
    idx = rng.permutation(n)
    a = int(ratios[0] * n)
    b = int((ratios[0] + ratios[1]) * n)
    return idx[:a], idx[a:b], idx[b:]


def train_hazard(hazard: str, *, dataset: Dataset | None = None,
                 n: int = 1200, seed: int = 42,
                 n_estimators: int = 60, learning_rate: float = 0.3,
                 max_depth: int = 3, recall_beta: float = 2.0,
                 use_class_weight: bool = True,
                 save_artifact: bool = True) -> dict:
    """Train one hazard model end-to-end and return its artifact dict.

    If `dataset` is provided it is filtered for valid labels and used as-is;
    otherwise a deterministic SIMULATED dataset is generated.
    """
    schema = get_schema(hazard)
    raw_ds = dataset or generate(hazard, n=n, seed=seed)
    if raw_ds.feature_names != schema.names:
        raise ValueError(
            f"dataset feature order {raw_ds.feature_names} != schema {schema.names}")

    # Honest label handling (section 6): unknown (-1) labels are NEVER assumed negative.
    ds = raw_ds.filter_labeled_only()

    X = np.asarray(ds.X, dtype=float)
    y = np.asarray(ds.y, dtype=int)
    
    # Spatial/temporal split (section 7): avoid random point leakage
    tr, va, te = ds.split_temporal_or_block(seed=seed)

    # Imbalance handling (section 9): balanced class weighting
    class_weight = "balanced" if use_class_weight else None
    model = GBTClassifier(n_estimators=n_estimators, learning_rate=learning_rate,
                          max_depth=max_depth)
    model.fit(X[tr], y[tr], class_weight=class_weight)

    # Validation: predict raw probabilities
    va_raw_prob = model.predict_proba(X[va])

    # Probability calibration (section 11): fit Platt scaling on validation data ONLY
    calibrator = PlattCalibrator().fit(va_raw_prob, y[va])
    va_cal_prob = calibrator.calibrate(va_raw_prob)

    # Validation: choose operating threshold favouring recall (section 10, 35)
    threshold = MET.best_threshold_by_recall(y[va], va_cal_prob, beta=recall_beta)
    val_metrics = MET.classification_metrics(y[va], va_cal_prob, threshold=threshold)

    # Test: touched ONCE at the chosen threshold => honest generalization (section 7, 19)
    te_raw_prob = model.predict_proba(X[te])
    te_cal_prob = calibrator.calibrate(te_raw_prob)
    test_metrics = MET.classification_metrics(y[te], te_cal_prob, threshold=threshold)

    # Feature importance (gain-based, from the trained trees) (section 14)
    importance = model.feature_importance()
    feat_importance = sorted(
        [{"feature": name, "importance": round(float(imp), 4),
          "unit": getattr(spec, "unit", ""), "source": getattr(spec, "source", "")}
         for name, imp, spec in zip(schema.names, importance, schema.specs)],
        key=lambda d: d["importance"], reverse=True)

    schema_fp = schema.fingerprint()
    version = A.make_version(hazard, schema_fp)

    # Historical data readiness inspection
    hist_status = inspect_available_historical_data()

    artifact = {
        "hazard": hazard,
        "version": version,
        "model_type": "gbt-from-scratch-numpy",
        "operating_threshold": threshold,
        "threshold_type": "ML decision threshold (not official government threshold)",
        "threshold_objective": f"F-beta (beta={recall_beta}) with min_specificity>=0.25 on validation set",
        "schema": {
            "hazard": schema.hazard,
            "fingerprint": schema_fp,
            "features": [
                {"name": s.name, "lo": s.lo, "hi": s.hi,
                 "missing": s.missing, "impute_default": s.impute_default,
                 "label": s.label, "unit": getattr(s, "unit", ""),
                 "source": getattr(s, "source", ""),
                 "transformation": getattr(s, "transformation", "identity"),
                 "critical": getattr(s, "critical", False)}
                for s in schema.specs
            ],
        },
        "model": model.to_dict(),
        "calibration": calibrator.to_dict(),
        "feature_importance": feat_importance,
        "card": {
            # ---- HONESTY BLOCK (sections 6, 17, 18, 27) ----
            "model_name": f"{hazard}_model",
            "model_version": version,
            "status": "NOT VALIDATED",
            "validated": False,
            "is_demo": True,
            "data_source": ds.source,          # "SIMULATED"
            "data_version": ds.version,
            "is_synthetic": ds.is_synthetic,    # True
            "split_strategy": "temporal_block_split (Train: 60%, Val: 20%, Test: 20%)",
            "historical_data_inspection": hist_status,
            "disclaimer": (
                "Trained on DETERMINISTIC SIMULATED data to demonstrate and prove the "
                "AI pipeline architecture. NOT scientifically validated; not trained on "
                "verified real government event/non-event censuses. Metrics are held-out "
                "on simulated data and describe pipeline generalization only."
            ),
            "trained_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "n_samples": int(len(y)),
            "n_train": int(len(tr)),
            "n_val": int(len(va)),
            "n_test": int(len(te)),
            "class_balance": round(float(y.mean()), 4),
            "imbalance_handling": "class_weight_balanced",
            "config": {
                "n_estimators": n_estimators,
                "learning_rate": learning_rate,
                "max_depth": max_depth,
                "seed": seed,
                "recall_beta": recall_beta,
                "use_class_weight": use_class_weight,
            },
            "final_train_logloss": round(float(model.train_loss_[-1]), 4) if model.train_loss_ else None,
            "validation_metrics": val_metrics,
            "test_metrics": test_metrics,
            "calibration_summary": {
                "method": "platt_sigmoid",
                "val_brier_before": round(MET.brier_score(y[va], va_raw_prob), 4),
                "val_brier_after": round(MET.brier_score(y[va], va_cal_prob), 4),
                "val_ece": round(expected_calibration_error(y[va], va_cal_prob), 4),
                "test_brier": round(MET.brier_score(y[te], te_cal_prob), 4),
                "test_ece": round(expected_calibration_error(y[te], te_cal_prob), 4),
            },
        },
    }

    if save_artifact:
        A.save(artifact)
    return artifact


def train_all(**kwargs) -> dict:
    """Train both hazard models. Returns {hazard: artifact}."""
    return {h: train_hazard(h, **kwargs) for h in ("flood", "landslide")}



if __name__ == "__main__":  # manual/CLI training entry point
    import json
    result = train_all()
    for hazard, art in result.items():
        card = art["card"]
        print(f"\n=== {hazard} :: {art['version']} ===")
        print("  test metrics:", json.dumps(card["test_metrics"], indent=2))
        print("  top features:", art["feature_importance"][:3])
