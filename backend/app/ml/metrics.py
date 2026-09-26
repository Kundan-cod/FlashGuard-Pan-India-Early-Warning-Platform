"""
Evaluation metrics computed from scratch (master prompt sections 6, 35, 66).

All metrics are computed on ACTUAL held-out predictions. Nothing here fabricates
a number. Section 35 (false negatives are worse than false positives for a
disaster system) is why we report recall and the full confusion matrix, and why
train.py selects the operating threshold by recall-weighted F-beta, not accuracy.
"""
from __future__ import annotations

import numpy as np


def confusion(y_true, y_pred) -> dict:
    y_true = np.asarray(y_true).astype(int)
    y_pred = np.asarray(y_pred).astype(int)
    tp = int(np.sum((y_true == 1) & (y_pred == 1)))
    tn = int(np.sum((y_true == 0) & (y_pred == 0)))
    fp = int(np.sum((y_true == 0) & (y_pred == 1)))
    fn = int(np.sum((y_true == 1) & (y_pred == 0)))
    return {"tp": tp, "tn": tn, "fp": fp, "fn": fn}


def _safe_div(a, b):
    return a / b if b else 0.0


def precision_recall_auc(y_true, prob) -> float:
    """Compute Area Under Precision-Recall Curve (PR-AUC / Average Precision)."""
    y_true = np.asarray(y_true).astype(int)
    prob = np.asarray(prob, dtype=float)
    n_pos = int(y_true.sum())
    if n_pos == 0:
        return 0.0
    if n_pos == len(y_true):
        return 1.0

    order = np.argsort(-prob)
    y_sorted = y_true[order]
    tp_cumsum = np.cumsum(y_sorted == 1)
    fp_cumsum = np.cumsum(y_sorted == 0)
    
    recalls = tp_cumsum / n_pos
    precisions = tp_cumsum / (tp_cumsum + fp_cumsum)
    
    # Prepend (recall=0, precision=1)
    recalls = np.concatenate(([0.0], recalls))
    precisions = np.concatenate(([1.0], precisions))
    
    # Trapezoidal integration for PR curve
    pr_auc = float(np.sum((recalls[1:] - recalls[:-1]) * precisions[1:]))
    return max(0.0, min(1.0, pr_auc))


def classification_metrics(y_true, prob, threshold: float = 0.5) -> dict:
    from app.ml.calibration import expected_calibration_error
    y_true = np.asarray(y_true).astype(int)
    prob = np.asarray(prob, dtype=float)
    y_pred = (prob >= threshold).astype(int)
    c = confusion(y_true, y_pred)
    tp, tn, fp, fn = c["tp"], c["tn"], c["fp"], c["fn"]
    precision = _safe_div(tp, tp + fp)
    recall = _safe_div(tp, tp + fn)
    specificity = _safe_div(tn, tn + fp)
    f1 = _safe_div(2 * precision * recall, precision + recall)
    accuracy = _safe_div(tp + tn, tp + tn + fp + fn)
    fb = fbeta(precision, recall, beta=2.0)
    
    return {
        "threshold": round(float(threshold), 4),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "specificity": round(specificity, 4),
        "f1": round(f1, 4),
        "f2": round(fb, 4),
        "auc": round(roc_auc(y_true, prob), 4),
        "pr_auc": round(precision_recall_auc(y_true, prob), 4),
        "brier": round(brier_score(y_true, prob), 4),
        "calibration_error": round(expected_calibration_error(y_true, prob), 4),
        "confusion": c,
        "n": int(len(y_true)),
        "positives": int(y_true.sum()),
        "negatives": int(len(y_true) - y_true.sum()),
    }


def roc_auc(y_true, prob) -> float:
    """AUC via the Mann-Whitney U statistic (rank-based, handles ties)."""
    y_true = np.asarray(y_true).astype(int)
    prob = np.asarray(prob, dtype=float)
    n_pos = int(y_true.sum())
    n_neg = int(len(y_true) - n_pos)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = np.argsort(prob, kind="mergesort")
    ranks = np.empty(len(prob), dtype=float)
    sorted_p = prob[order]
    i = 0
    n = len(prob)
    while i < n:
        j = i
        while j + 1 < n and sorted_p[j + 1] == sorted_p[i]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # ranks are 1-based
        ranks[order[i:j + 1]] = avg_rank
        i = j + 1
    sum_pos = ranks[y_true == 1].sum()
    auc = (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)
    return float(auc)


def brier_score(y_true, prob) -> float:
    y_true = np.asarray(y_true, dtype=float)
    prob = np.asarray(prob, dtype=float)
    return float(np.mean((prob - y_true) ** 2))


def fbeta(precision: float, recall: float, beta: float = 2.0) -> float:
    b2 = beta * beta
    denom = b2 * precision + recall
    return _safe_div((1 + b2) * precision * recall, denom)


def best_threshold_by_recall(y_true, prob, beta: float = 2.0,
                             min_specificity: float = 0.25) -> float:
    """Pick the probability threshold that maximizes F-beta (beta>1 favours
    recall — section 35: missing a real event is the costly error), while
    refusing degenerate operating points that flag (almost) everything.

    The `min_specificity` guard rejects thresholds that catch every positive
    only by raising a false alarm on nearly every negative — an operating point
    with no discriminative value. If no threshold clears the guard (a very weak
    model), we fall back to the plain F-beta optimum so a threshold is always
    returned.
    """
    y_true = np.asarray(y_true).astype(int)
    prob = np.asarray(prob, dtype=float)
    best_t, best_score = None, -1.0
    fallback_t, fallback_score = 0.5, -1.0
    for t in np.linspace(0.05, 0.95, 19):
        m = classification_metrics(y_true, prob, threshold=float(t))
        score = fbeta(m["precision"], m["recall"], beta=beta)
        if score > fallback_score:
            fallback_score, fallback_t = score, float(t)
        if m["specificity"] >= min_specificity and score > best_score:
            best_score, best_t = score, float(t)
    return round(best_t if best_t is not None else fallback_t, 4)

