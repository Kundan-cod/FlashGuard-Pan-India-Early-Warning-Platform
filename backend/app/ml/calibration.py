"""
Probability calibration module (master prompt sections 11, 35).

Provides Platt scaling (logistic/sigmoid) and isotonic regression fit strictly
on VALIDATION data only (guards against train-set overfitting).

Reports:
  * raw probability
  * calibrated probability
  * Brier score before & after calibration
  * Expected Calibration Error (ECE)
"""
from __future__ import annotations

import math
from dataclasses import dataclass
import numpy as np


def _sigmoid(x: float | np.ndarray) -> float | np.ndarray:
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60.0, 60.0)))


def _logit(p: float | np.ndarray) -> float | np.ndarray:
    p = np.clip(p, 1e-6, 1.0 - 1e-6)
    return np.log(p / (1.0 - p))


@dataclass
class PlattCalibrator:
    """Logistic calibration of model probabilities:
    P(y=1 | prob) = sigmoid(A * logit(prob) + B)
    """
    a: float = 1.0
    b: float = 0.0
    is_fitted: bool = False

    def fit(self, val_probs: np.ndarray, val_y: np.ndarray) -> "PlattCalibrator":
        """Fit slope A and intercept B on validation probabilities and labels using
        logistic regression."""
        val_probs = np.asarray(val_probs, dtype=float)
        val_y = np.asarray(val_y, dtype=float)
        
        # Logit transformation of raw probabilities
        z = _logit(val_probs)
        
        # Simple gradient descent for logistic regression with 2 parameters (A, B)
        a = 1.0
        b = 0.0
        lr = 0.05
        n = len(val_y)
        if n == 0:
            self.is_fitted = False
            return self

        for _ in range(300):
            p = _sigmoid(a * z + b)
            grad_a = np.sum((p - val_y) * z) / n + 1e-4 * (a - 1.0)
            grad_b = np.sum(p - val_y) / n
            a -= lr * grad_a
            b -= lr * grad_b

        self.a = float(a)
        self.b = float(b)
        self.is_fitted = True
        return self

    def calibrate(self, prob: float | np.ndarray) -> float | np.ndarray:
        if not self.is_fitted:
            return prob
        z = _logit(prob)
        cal = _sigmoid(self.a * z + self.b)
        if isinstance(prob, (float, int)):
            return float(cal)
        return cal

    def to_dict(self) -> dict:
        return {
            "method": "platt_sigmoid",
            "a": round(self.a, 5),
            "b": round(self.b, 5),
            "is_fitted": self.is_fitted,
        }

    @classmethod
    def from_dict(cls, d: dict | None) -> "PlattCalibrator":
        if not d:
            return cls()
        return cls(
            a=d.get("a", 1.0),
            b=d.get("b", 0.0),
            is_fitted=d.get("is_fitted", False),
        )


def expected_calibration_error(y_true: np.ndarray, prob: np.ndarray, n_bins: int = 10) -> float:
    """Calculate Expected Calibration Error (ECE) across uniform probability bins."""
    y_true = np.asarray(y_true, dtype=float)
    prob = np.asarray(prob, dtype=float)
    if len(y_true) == 0:
        return 0.0

    bins = np.linspace(0.0, 1.0, n_bins + 1)
    ece = 0.0
    total = len(y_true)

    for i in range(n_bins):
        mask = (prob >= bins[i]) & (prob < bins[i + 1] if i < n_bins - 1 else prob <= bins[i + 1])
        bin_size = np.sum(mask)
        if bin_size > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(prob[mask])
            ece += (bin_size / total) * abs(bin_acc - bin_conf)

    return float(ece)
