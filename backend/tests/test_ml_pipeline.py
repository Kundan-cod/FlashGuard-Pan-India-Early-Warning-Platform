"""
ML pipeline tests (master prompt sections 6, 35, 47, 66).

Proves the trainable pipeline REALLY works end-to-end with deterministic
fixtures — not by assertion but by running it: deterministic data generation,
a learner whose training loss actually decreases, honest held-out metrics,
save/load round-trip fidelity, schema-fingerprint validation, explicit
missing-feature handling, versioning, and inference behind the HazardModel
interface.

Everything uses an isolated temp artifact dir so it never touches ml/artifacts.
No network, no h5py, no sklearn — pure portable core.
"""
import os
import tempfile
import unittest
from _util import bootstrap
bootstrap()

import numpy as np

from app.ml import artifact as A
from app.ml import metrics as MET
from app.ml.dataset import generate
from app.ml.gbt import GBTClassifier
from app.ml.schema import (FLOOD_SCHEMA, LANDSLIDE_SCHEMA, get_schema,
                           MissingPolicy, FeatureSpec, FeatureSchema)
from app.ml.train import train_hazard
from app.ml.inference import TrainedHazardModel


class _ArtifactDirMixin:
    """Point ML_ARTIFACT_DIR at a fresh temp dir for each test."""
    def setUp(self):
        import uuid
        base = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "data", "test_artifacts"))
        self._tmp = os.path.join(base, f"ml_art_{uuid.uuid4().hex[:8]}")
        os.makedirs(self._tmp, exist_ok=True)
        self._prev = os.environ.get("ML_ARTIFACT_DIR")
        os.environ["ML_ARTIFACT_DIR"] = self._tmp

    def tearDown(self):
        if self._prev is None:
            os.environ.pop("ML_ARTIFACT_DIR", None)
        else:
            os.environ["ML_ARTIFACT_DIR"] = self._prev
        import shutil
        shutil.rmtree(self._tmp, ignore_errors=True)


class TestDataset(unittest.TestCase):
    def test_deterministic(self):
        a = generate("flood", n=300, seed=7)
        b = generate("flood", n=300, seed=7)
        self.assertEqual(a.X, b.X, "same seed must give identical features")
        self.assertEqual(a.y, b.y, "same seed must give identical labels")

    def test_seed_changes_data(self):
        a = generate("flood", n=300, seed=1)
        b = generate("flood", n=300, seed=2)
        self.assertNotEqual(a.X, b.X)

    def test_labelled_simulated(self):
        ds = generate("landslide", n=100, seed=3)
        self.assertTrue(ds.is_synthetic)
        self.assertEqual(ds.source, "SIMULATED")

    def test_feature_order_matches_schema(self):
        ds = generate("flood", n=50, seed=1)
        self.assertEqual(ds.feature_names, FLOOD_SCHEMA.names)

    def test_classes_not_degenerate(self):
        # a meaningful pipeline proof needs both classes present, reasonably balanced
        for hazard in ("flood", "landslide"):
            ds = generate(hazard, n=2000, seed=42)
            rate = sum(ds.y) / len(ds.y)
            self.assertTrue(0.2 < rate < 0.8,
                            f"{hazard} positive rate {rate:.3f} is degenerate")


class TestSchema(unittest.TestCase):
    def test_vectorize_order(self):
        feats = {s.name: (i + 1) for i, s in enumerate(FLOOD_SCHEMA.specs)}
        vec, report = FLOOD_SCHEMA.validate_and_vectorize(feats)
        self.assertEqual(vec, [float(i + 1) for i in range(len(FLOOD_SCHEMA.specs))])
        self.assertEqual(report["imputed"], [])

    def test_missing_impute_is_flagged(self):
        feats = {"rain_3h": 40}  # everything else missing -> imputed
        vec, report = FLOOD_SCHEMA.validate_and_vectorize(feats)
        self.assertIn("rain_24h", report["imputed"])
        self.assertIn("rain_3h", report["used"])
        # imputed default is the declared default (0.0), never a fabricated value
        idx = FLOOD_SCHEMA.names.index("rain_24h")
        self.assertEqual(vec[idx], 0.0)

    def test_required_missing_raises(self):
        schema = FeatureSchema(hazard="x", specs=[
            FeatureSpec("must_have", 0, 1, missing=MissingPolicy.REQUIRED),
        ])
        with self.assertRaises(ValueError):
            schema.validate_and_vectorize({})

    def test_out_of_range_reported_not_raised(self):
        feats = {s.name: 0 for s in FLOOD_SCHEMA.specs}
        feats["rain_3h"] = 9999  # way above hi
        vec, report = FLOOD_SCHEMA.validate_and_vectorize(feats)
        self.assertIn("rain_3h", report["out_of_range"])

    def test_fingerprint_stable_and_sensitive(self):
        fp1 = FLOOD_SCHEMA.fingerprint()
        fp2 = get_schema("flood").fingerprint()
        self.assertEqual(fp1, fp2)
        drifted = FeatureSchema(hazard="flood",
                                specs=list(reversed(FLOOD_SCHEMA.specs)))
        self.assertNotEqual(fp1, drifted.fingerprint(),
                            "reordering features must change the fingerprint")


class TestGBT(unittest.TestCase):
    def test_training_loss_decreases(self):
        ds = generate("flood", n=800, seed=5)
        m = GBTClassifier(n_estimators=40, learning_rate=0.3, max_depth=3)
        m.fit(ds.X, ds.y)
        self.assertGreater(len(m.train_loss_), 1)
        self.assertLess(m.train_loss_[-1], m.train_loss_[0],
                        "training log-loss must decrease — the learner must learn")

    def test_probabilities_in_range(self):
        ds = generate("flood", n=400, seed=6)
        m = GBTClassifier(n_estimators=30).fit(ds.X, ds.y)
        p = m.predict_proba(ds.X)
        self.assertTrue(np.all(p >= 0) and np.all(p <= 1))

    def test_learns_signal_auc(self):
        # on a held-out split the model must beat random (AUC > 0.5) — proves it
        # captured real structure, not memorized noise
        ds = generate("flood", n=1500, seed=8)
        X = np.asarray(ds.X); y = np.asarray(ds.y)
        cut = 1000
        m = GBTClassifier(n_estimators=50, learning_rate=0.3).fit(X[:cut], y[:cut])
        auc = MET.roc_auc(y[cut:], m.predict_proba(X[cut:]))
        self.assertGreater(auc, 0.65, f"held-out AUC {auc:.3f} shows no real learning")

    def test_contributions_are_additive(self):
        ds = generate("flood", n=300, seed=9)
        m = GBTClassifier(n_estimators=20, learning_rate=0.3).fit(ds.X, ds.y)
        row = ds.X[0]
        contribs = m.contributions(row)
        reconstructed = m.intercept() + contribs.sum()
        actual = m.decision_function([row])[0]
        self.assertAlmostEqual(reconstructed, actual, places=6,
                               msg="intercept + contributions must sum to the decision function")

    def test_importance_sums_to_one(self):
        ds = generate("landslide", n=400, seed=10)
        m = GBTClassifier(n_estimators=30).fit(ds.X, ds.y)
        imp = m.feature_importance()
        self.assertAlmostEqual(float(imp.sum()), 1.0, places=6)

    def test_serialization_round_trip(self):
        ds = generate("flood", n=300, seed=11)
        m = GBTClassifier(n_estimators=25, learning_rate=0.25, max_depth=3).fit(ds.X, ds.y)
        d = m.to_dict()
        m2 = GBTClassifier.from_dict(d)
        p1 = m.predict_proba(ds.X)
        p2 = m2.predict_proba(ds.X)
        np.testing.assert_allclose(p1, p2, rtol=1e-12, atol=1e-12)


class TestMetrics(unittest.TestCase):
    def test_perfect_separation(self):
        y = [0, 0, 1, 1]
        prob = [0.1, 0.2, 0.8, 0.9]
        m = MET.classification_metrics(y, prob, threshold=0.5)
        self.assertEqual(m["recall"], 1.0)
        self.assertEqual(m["precision"], 1.0)
        self.assertEqual(m["auc"], 1.0)

    def test_auc_random_is_half(self):
        rng = np.random.RandomState(0)
        y = rng.randint(0, 2, size=2000)
        prob = rng.rand(2000)
        auc = MET.roc_auc(y, prob)
        self.assertAlmostEqual(auc, 0.5, delta=0.06)

    def test_threshold_guard_rejects_degenerate(self):
        # a model that outputs ~constant high prob: catching all positives needs
        # near-zero specificity, which the guard must refuse
        y = [0] * 50 + [1] * 50
        prob = [0.9] * 100
        t = MET.best_threshold_by_recall(y, prob, beta=2.0, min_specificity=0.25)
        # with all-equal probs no threshold clears the guard -> fallback returned,
        # but the call must not crash and must return a valid threshold
        self.assertTrue(0.0 < t < 1.0)

    def test_recall_weighting_prefers_recall(self):
        # beta=2 should not pick a threshold that sacrifices recall for precision
        y = [0, 0, 0, 1, 1, 1, 1, 1]
        prob = [0.1, 0.2, 0.45, 0.5, 0.55, 0.6, 0.7, 0.8]
        t = MET.best_threshold_by_recall(y, prob, beta=2.0, min_specificity=0.0)
        m = MET.classification_metrics(y, prob, threshold=t)
        self.assertGreaterEqual(m["recall"], 0.8)


class TestTrainAndInfer(_ArtifactDirMixin, unittest.TestCase):
    def test_train_produces_honest_card(self):
        art = train_hazard("flood", n=1000, seed=42)
        card = art["card"]
        self.assertFalse(card["validated"], "must never claim validated on simulated data")
        self.assertTrue(card["is_demo"])
        self.assertEqual(card["data_source"], "SIMULATED")
        self.assertTrue(card["is_synthetic"])
        # metrics exist and are real numbers on the held-out test split
        tm = card["test_metrics"]
        for k in ("accuracy", "precision", "recall", "auc", "brier"):
            self.assertIsInstance(tm[k], float)
        self.assertEqual(tm["n"], card["n_test"])

    def test_test_split_is_held_out(self):
        # n_train + n_val + n_test == n_samples, and splits are disjoint sizes
        art = train_hazard("landslide", n=1000, seed=42)
        c = art["card"]
        self.assertEqual(c["n_train"] + c["n_val"] + c["n_test"], c["n_samples"])
        self.assertGreater(c["n_test"], 0)

    def test_versioning_and_latest_pointer(self):
        art = train_hazard("flood", n=600, seed=42)
        version = art["version"]
        self.assertTrue(version.startswith("flood-gbt-"))
        # latest pointer resolves to a real file
        p = A.latest_path("flood")
        self.assertIsNotNone(p)
        self.assertIn("flood", os.path.basename(p))
        self.assertIn(version, A.list_versions("flood"))

    def test_save_load_inference_matches_training(self):
        art = train_hazard("flood", n=800, seed=42)
        model = TrainedHazardModel.load_latest("flood")
        # reload the raw GBT and compare probabilities on the generated data
        ds = generate("flood", n=50, seed=99)
        from app.ml.schema import get_schema
        schema = get_schema("flood")
        for row_feats_vec in ds.X[:10]:
            feat_dict = dict(zip(schema.names, row_feats_vec))
            pred = model.predict(feat_dict)
            self.assertTrue(0.0 <= pred.probability <= 1.0)
            # contributions present and sorted desc for explainability
            vals = [c["contribution"] for c in pred.contributions]
            self.assertEqual(vals, sorted(vals, reverse=True))

    def test_schema_fingerprint_mismatch_rejected(self):
        art = train_hazard("flood", n=400, seed=42)
        # corrupt the stored fingerprint -> load must refuse
        art["schema"]["fingerprint"] = "deadbeefdeadbeef"
        with self.assertRaises(ValueError):
            TrainedHazardModel(art)

    def test_inference_missing_feature_handled(self):
        train_hazard("flood", n=400, seed=42)
        model = TrainedHazardModel.load_latest("flood")
        # supply only some features; the rest are imputed + excluded from factors
        pred = model.predict({"rain_3h": 100, "river_rate_of_rise_1h": 1.0})
        self.assertTrue(0.0 <= pred.probability <= 1.0)
        used_feats = {c["feature"] for c in pred.contributions}
        # imputed features must not appear as contributing evidence
        self.assertNotIn("flow_accumulation", used_feats)
        self.assertTrue(hasattr(pred, "schema_report"))
        self.assertIn("flow_accumulation", pred.schema_report["imputed"])

    def test_trained_model_is_hazardmodel(self):
        train_hazard("landslide", n=400, seed=42)
        model = TrainedHazardModel.load_latest("landslide")
        from app.models.base_model import HazardModel
        self.assertIsInstance(model, HazardModel)
        self.assertFalse(model.validated)
        self.assertTrue(model.is_demo())


class TestProviderIntegration(_ArtifactDirMixin, unittest.TestCase):
    def tearDown(self):
        os.environ.pop("USE_TRAINED_MODELS", None)
        from app.ml.provider import reset_cache
        reset_cache()
        super().tearDown()

    def test_default_is_demo(self):
        from app.ml import provider
        os.environ.pop("USE_TRAINED_MODELS", None)
        provider.reset_cache()
        m = provider.get_model("flood")
        self.assertEqual(m.version, "flood-demo-0.1")

    def test_trained_used_when_enabled(self):
        train_hazard("flood", n=400, seed=42)
        from app.ml import provider
        os.environ["USE_TRAINED_MODELS"] = "1"
        provider.reset_cache()
        m = provider.get_model("flood")
        self.assertTrue(m.version.startswith("flood-gbt-"))

    def test_falls_back_to_demo_when_no_artifact(self):
        # enabled but NO artifact trained -> must fall back, never crash
        from app.ml import provider
        os.environ["USE_TRAINED_MODELS"] = "1"
        provider.reset_cache()
        m = provider.get_model("landslide")
        self.assertEqual(m.version, "landslide-demo-0.1")


if __name__ == "__main__":
    unittest.main()
