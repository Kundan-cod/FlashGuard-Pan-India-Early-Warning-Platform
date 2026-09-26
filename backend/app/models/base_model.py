"""
Model interface (master prompt sections 16, 68).

Two hazards, two models, one interface. The shipped implementation is a
from-scratch gradient-boosted-tree-style / logistic model in numpy (portable
core has no sklearn/xgboost). It is a DEMO MODEL:

  *** NOT SCIENTIFICALLY VALIDATED ***
  Trained on synthetic/replay data for demonstration. Architecturally ready to
  retrain on verified historical labels (GSI inventory, India Flood Inventory)
  in Track B with XGBoost/LightGBM behind the SAME interface.

The interface is what matters for the architecture: predict_proba(features)->p,
plus feature_contributions() for explainability (section 47).
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Prediction:
    probability: float
    contributions: list  # [{"factor": name, "contribution": float}], sorted desc
    calibrated_probability: float | None = None
    operating_threshold: float | None = None
    schema_report: dict | None = None
    drivers: list[str] | None = None


class HazardModel:
    """Abstract hazard model. Subclasses define `feature_order` and predict."""
    name: str = "base"
    version: str = "demo-0.1"
    validated: bool = False   # never claim True without real labels + eval
    operating_threshold: float = 0.5

    feature_order: list[str] = []

    def predict(self, feature_values: dict) -> Prediction:
        raise NotImplementedError

    def is_demo(self) -> bool:
        return not self.validated
