"""
Trainable ML pipeline (master prompt section 6).

A REAL train -> validate -> test -> save/load -> version -> inference pipeline,
implemented from scratch in NumPy so it RUNS and is PROVEN in the portable core
(no sklearn/xgboost needed). It sits behind the SAME `HazardModel` interface as
the transparent demo scorers (app.models), so Track B can later swap in
XGBoost/LightGBM trained on VERIFIED historical labels without touching the risk
engine, prediction service, or API.

Honesty posture (sections 6, 35, 66, 67):
  * The shipped trained models are trained on CLEARLY-LABELLED, DETERMINISTIC,
    SIMULATED fixtures (app.ml.dataset). They exist to prove the pipeline works
    end-to-end, NOT to claim scientific accuracy.
  * `validated` stays False and `trained_on` is "SIMULATED" until real labels
    are connected. No accuracy is fabricated: train.py computes metrics on a
    held-out test split and stores the ACTUAL numbers in a model card.
  * Missing features are handled explicitly (schema-driven), never silently
    faked to a neutral value that could mask a data gap.
"""
