"""
From-scratch gradient-boosted decision trees for binary classification
(master prompt section 6). Pure NumPy — runs in the portable core with no
sklearn/xgboost. This is a REAL learner (it fits data, generalizes, and its
metrics are computed on held-out data), not a hand-weighted scorer.

Track B can replace this class with XGBoost/LightGBM behind the identical
HazardModel interface; the algorithm here is deliberately the same family
(gradient boosting on regression trees with logistic loss) so behaviour is
comparable.

Explainability (section 47): every tree records which feature each split uses,
so we expose exact gain-based feature importance and per-prediction feature
contributions (sum of leaf deltas attributed to the splitting feature along the
decision path).
"""
from __future__ import annotations

import numpy as np


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-np.clip(x, -60, 60)))


class _Node:
    __slots__ = ("feature", "threshold", "left", "right", "value", "gain")

    def __init__(self):
        self.feature = None      # int index, or None for a leaf
        self.threshold = None
        self.left = None
        self.right = None
        self.value = 0.0         # leaf output (in log-odds space)
        self.gain = 0.0          # split gain (for importance)


class _RegressionTree:
    """A single regression tree fit to gradients/hessians (logistic loss)."""

    def __init__(self, max_depth=3, min_samples_leaf=20, lambda_=1.0, gamma=0.0):
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.lambda_ = lambda_
        self.gamma = gamma
        self.root = None
        self.n_features = 0

    def _leaf_value(self, g, h):
        return -g.sum() / (h.sum() + self.lambda_)

    def _best_split(self, X, g, h):
        n, m = X.shape
        G, H = g.sum(), h.sum()
        base = (G * G) / (H + self.lambda_)
        best = None
        for j in range(m):
            col = X[:, j]
            order = np.argsort(col, kind="mergesort")
            col_s, g_s, h_s = col[order], g[order], h[order]
            gl = hl = 0.0
            # candidate thresholds between distinct consecutive values
            for i in range(1, n):
                gl += g_s[i - 1]
                hl += h_s[i - 1]
                if col_s[i] == col_s[i - 1]:
                    continue
                if i < self.min_samples_leaf or (n - i) < self.min_samples_leaf:
                    continue
                gr = G - gl
                hr = H - hl
                gain = 0.5 * ((gl * gl) / (hl + self.lambda_)
                              + (gr * gr) / (hr + self.lambda_)
                              - base) - self.gamma
                if gain > 0 and (best is None or gain > best[0]):
                    thr = 0.5 * (col_s[i] + col_s[i - 1])
                    best = (gain, j, thr)
        return best

    def _build(self, X, g, h, depth):
        node = _Node()
        node.value = self._leaf_value(g, h)
        if depth >= self.max_depth or X.shape[0] < 2 * self.min_samples_leaf:
            return node
        split = self._best_split(X, g, h)
        if split is None:
            return node
        gain, j, thr = split
        mask = X[:, j] <= thr
        if mask.all() or (~mask).all():
            return node
        node.feature, node.threshold, node.gain = j, thr, gain
        node.left = self._build(X[mask], g[mask], h[mask], depth + 1)
        node.right = self._build(X[~mask], g[~mask], h[~mask], depth + 1)
        return node

    def fit(self, X, g, h):
        self.n_features = X.shape[1]
        self.root = self._build(X, g, h, 0)
        return self

    def _predict_row(self, row):
        node = self.root
        while node.feature is not None:
            node = node.left if row[node.feature] <= node.threshold else node.right
        return node.value

    def predict(self, X):
        return np.array([self._predict_row(r) for r in X], dtype=float)

    def gain_importance(self, out):
        """Accumulate split gain per feature index into `out` (length n_features)."""
        def walk(node):
            if node is None or node.feature is None:
                return
            out[node.feature] += node.gain
            walk(node.left)
            walk(node.right)
        walk(self.root)

    def path_contributions(self, row, out):
        """Attribute each step's value delta to the splitting feature (exact,
        additive, sums to tree output minus root value)."""
        node = self.root
        prev = node.value
        while node.feature is not None:
            nxt = node.left if row[node.feature] <= node.threshold else node.right
            out[node.feature] += (nxt.value - prev)
            prev = nxt.value
            node = nxt


class GBTClassifier:
    """Gradient-boosted trees, logistic loss. Deterministic given inputs."""

    def __init__(self, n_estimators=60, learning_rate=0.3, max_depth=3,
                 min_samples_leaf=20, lambda_=1.0, gamma=0.0):
        self.n_estimators = n_estimators
        self.learning_rate = learning_rate
        self.max_depth = max_depth
        self.min_samples_leaf = min_samples_leaf
        self.lambda_ = lambda_
        self.gamma = gamma
        self.trees = []
        self.base_score = 0.0
        self.n_features = 0
        self.train_loss_ = []

    def fit(self, X, y, sample_weight=None, class_weight=None):
        X = np.asarray(X, dtype=float)
        y = np.asarray(y, dtype=float)
        self.n_features = X.shape[1]

        if class_weight == "balanced" and sample_weight is None:
            n_pos = max(1, int(np.sum(y == 1)))
            n_neg = max(1, int(np.sum(y == 0)))
            w_pos = n_neg / n_pos
            sample_weight = np.where(y == 1, w_pos, 1.0)

        if sample_weight is not None:
            w = np.asarray(sample_weight, dtype=float)
            p = float(np.clip(np.average(y, weights=w), 1e-6, 1 - 1e-6))
        else:
            w = None
            p = float(np.clip(y.mean(), 1e-6, 1 - 1e-6))

        self.base_score = float(np.log(p / (1 - p)))  # log-odds prior
        F = np.full(X.shape[0], self.base_score, dtype=float)
        self.trees = []
        self.train_loss_ = []
        for _ in range(self.n_estimators):
            prob = _sigmoid(F)
            g = prob - y            # gradient of logloss wrt F
            h = prob * (1 - prob)   # hessian
            if w is not None:
                g *= w
                h *= w
            h = np.maximum(h, 1e-6)
            tree = _RegressionTree(self.max_depth, self.min_samples_leaf,
                                   self.lambda_, self.gamma).fit(X, g, h)
            F += self.learning_rate * tree.predict(X)
            self.trees.append(tree)
            self.train_loss_.append(self._logloss(y, _sigmoid(F), sample_weight=w))
        return self

    @staticmethod
    def _logloss(y, p, sample_weight=None):
        p = np.clip(p, 1e-9, 1 - 1e-9)
        loss = -(y * np.log(p) + (1 - y) * np.log(1 - p))
        if sample_weight is not None:
            return float(np.average(loss, weights=sample_weight))
        return float(np.mean(loss))

    def decision_function(self, X):
        X = np.asarray(X, dtype=float)
        F = np.full(X.shape[0], self.base_score, dtype=float)
        for tree in self.trees:
            F += self.learning_rate * tree.predict(X)
        return F

    def predict_proba(self, X):
        return _sigmoid(self.decision_function(X))

    def feature_importance(self):
        out = np.zeros(self.n_features, dtype=float)
        for tree in self.trees:
            tree.gain_importance(out)
        total = out.sum()
        return (out / total) if total > 0 else out

    def intercept(self):
        """The non-attributable offset: prior log-odds plus each tree's root
        value (a tree's root leaf value belongs to no splitting feature). Exposed
        so contributions are exactly additive:
            intercept() + sum(contributions(row)) == decision_function(row)."""
        roots = sum(t.root.value for t in self.trees)
        return self.base_score + self.learning_rate * roots

    def contributions(self, row):
        """Per-feature additive contribution (log-odds) for a single sample.
        intercept() + sum(contributions) == decision_function(row). Each tree's
        contribution is the sum of value deltas along the decision path,
        attributed to the feature that governs each split (exact, additive)."""
        row = np.asarray(row, dtype=float)
        out = np.zeros(self.n_features, dtype=float)
        for tree in self.trees:
            per = np.zeros(self.n_features, dtype=float)
            tree.path_contributions(row, per)
            out += self.learning_rate * per
        return out

    # -- plain-dict serialization (no pickle => safe, portable, inspectable) --
    def to_dict(self) -> dict:
        def node_to_dict(node):
            if node is None:
                return None
            if node.feature is None:
                return {"leaf": node.value}
            return {"f": node.feature, "t": node.threshold, "g": node.gain,
                    "l": node_to_dict(node.left), "r": node_to_dict(node.right)}
        return {
            "n_estimators": self.n_estimators,
            "learning_rate": self.learning_rate,
            "max_depth": self.max_depth,
            "min_samples_leaf": self.min_samples_leaf,
            "lambda_": self.lambda_,
            "gamma": self.gamma,
            "base_score": self.base_score,
            "n_features": self.n_features,
            "train_loss": self.train_loss_,
            "trees": [node_to_dict(t.root) for t in self.trees],
        }

    @classmethod
    def from_dict(cls, d: dict) -> "GBTClassifier":
        m = cls(n_estimators=d["n_estimators"], learning_rate=d["learning_rate"],
                max_depth=d["max_depth"], min_samples_leaf=d["min_samples_leaf"],
                lambda_=d["lambda_"], gamma=d["gamma"])
        m.base_score = d["base_score"]
        m.n_features = d["n_features"]
        m.train_loss_ = d.get("train_loss", [])

        def dict_to_node(nd):
            node = _Node()
            if nd is None:
                return node
            if "leaf" in nd:
                node.value = nd["leaf"]
                return node
            node.feature = nd["f"]
            node.threshold = nd["t"]
            node.gain = nd.get("g", 0.0)
            node.left = dict_to_node(nd["l"])
            node.right = dict_to_node(nd["r"])
            return node

        m.trees = []
        for root_d in d["trees"]:
            t = _RegressionTree(m.max_depth, m.min_samples_leaf, m.lambda_, m.gamma)
            t.n_features = m.n_features
            t.root = dict_to_node(root_d)
            m.trees.append(t)
        return m
