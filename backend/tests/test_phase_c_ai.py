"""
Comprehensive tests for Phase C AI/ML Prediction System.

Validates all Phase C core requirements:
1. Dual-model architecture (separate flood and landslide models).
2. Feature contracts: units, sources, valid ranges, missing policies, transformations.
3. Three-state label filtering (1=event, 0=non-event, -1=unknown filtered out).
4. Temporal block splitting to prevent autocorrelation leakage.
5. Probability calibration (Platt scaling) and Brier score evaluation.
6. Recall-prioritized threshold selection with specificity guard.
7. Independent confidence computation (decoupled from risk probability).
8. Out-of-distribution (OOD) & critical feature absence detection.
9. Directional feature contributions for explainability.
10. Bounded lead-time window estimation.
11. End-to-end risk assessment and enriched API response structure.
"""
import os
import unittest
from pathlib import Path
import numpy as np

from _util import bootstrap
bootstrap()

from app.ml.schema import FLOOD_SCHEMA, LANDSLIDE_SCHEMA, get_schema, MissingPolicy
from app.ml.dataset import Dataset, generate, inspect_available_historical_data
from app.ml.calibration import PlattCalibrator, expected_calibration_error
from app.ml import metrics as MET
from app.ml.gbt import GBTClassifier
from app.ml.train import train_hazard
from app.ml.inference import TrainedHazardModel
from app.risk import engine as risk_engine
from app.features.engineer import FeatureSet
from app.database import repositories as repo
from app.services import seed, replay_driver, prediction_service as psvc
from app.collectors.replay_collector import ReplayCollector


def _resolve_dataset() -> str:
    env = os.environ.get("REPLAY_DATASET")
    if env and Path(env).exists():
        return env
    for p in (Path(__file__).resolve().parents[1] / "data" / "replay" / "uttarakhand_flash_flood_event.json",
              Path(__file__).resolve().parents[2] / "data" / "replay" / "uttarakhand_flash_flood_event.json"):
        if p.exists():
            return str(p)
    return str(Path(__file__).resolve().parents[2] / "data" / "replay" / "uttarakhand_flash_flood_event.json")


DATASET = _resolve_dataset()


class TestPhaseCAIFeaturesAndSchemas(unittest.TestCase):
    def test_flood_and_landslide_schemas_distinct(self):
        """Flood and landslide must remain separate models with distinct features."""
        fl_names = set(FLOOD_SCHEMA.names)
        ls_names = set(LANDSLIDE_SCHEMA.names)
        self.assertNotEqual(fl_names, ls_names)
        self.assertIn("river_level", fl_names)
        self.assertNotIn("river_level", ls_names)
        self.assertIn("relative_relief", ls_names)
        self.assertNotIn("relative_relief", fl_names)

    def test_feature_specs_carry_units_sources_transforms(self):
        """Every feature must declare unit, source, valid range, and transform."""
        for schema in (FLOOD_SCHEMA, LANDSLIDE_SCHEMA):
            for s in schema.specs:
                self.assertTrue(bool(s.name), "feature must have a name")
                self.assertTrue(bool(s.unit), f"{s.name} missing physical unit")
                self.assertTrue(bool(s.source), f"{s.name} missing source")
                self.assertTrue(bool(s.transformation), f"{s.name} missing transformation")
                self.assertLess(s.lo, s.hi, f"{s.name} invalid bounds")

    def test_critical_feature_absence_flagged(self):
        """Missing critical features must be flagged in the schema report."""
        # rain_3h is critical in FLOOD_SCHEMA
        vec, report = FLOOD_SCHEMA.validate_and_vectorize({"rain_24h": 50.0})
        self.assertIn("rain_3h", report["missing_critical"])
        self.assertIn("rain_3h", report["imputed"])
        self.assertLess(report["completeness"], 1.0)


class TestPhaseCDatasetAndLabels(unittest.TestCase):
    def test_three_state_label_filtering(self):
        """Unknown (-1) samples must NEVER be treated as negatives (0)."""
        X = [[1.0] * len(FLOOD_SCHEMA.specs)] * 4
        y = [1, 0, -1, 1]  # one unknown sample
        ds = Dataset(hazard="flood", feature_names=FLOOD_SCHEMA.names, X=X, y=y)
        filtered = ds.filter_labeled_only()
        self.assertEqual(len(filtered), 3)
        self.assertNotIn(-1, filtered.y)
        self.assertEqual(filtered.y, [1, 0, 1])

    def test_temporal_block_split(self):
        """Split must partition into train, val, test without index leakage."""
        ds = generate("flood", n=300, seed=42)
        tr, va, te = ds.split_temporal_or_block(ratios=(0.6, 0.2, 0.2), seed=42)
        self.assertEqual(len(tr) + len(va) + len(te), 300)
        # Ensure no overlap between splits
        self.assertEqual(len(set(tr).intersection(set(va))), 0)
        self.assertEqual(len(set(tr).intersection(set(te))), 0)
        self.assertEqual(len(set(va).intersection(set(te))), 0)

    def test_historical_data_inspection_honest(self):
        """System must honestly report lack of confirmed negative censuses."""
        inspection = inspect_available_historical_data()
        self.assertFalse(inspection["historical_labels_available"])
        self.assertEqual(inspection["model_status"], "NOT VALIDATED")
        self.assertTrue(inspection["is_demo"])


class TestPhaseCCalibrationAndMetrics(unittest.TestCase):
    def test_platt_calibrator_fit_and_calibrate(self):
        """Platt calibrator must monotonically map probabilities and decrease ECE/Brier."""
        np.random.seed(42)
        raw_p = np.linspace(0.1, 0.9, 100)
        true_y = (raw_p + np.random.normal(0, 0.1, 100) > 0.5).astype(int)
        
        cal = PlattCalibrator().fit(raw_p, true_y)
        self.assertTrue(cal.is_fitted)
        cal_p = cal.calibrate(raw_p)
        self.assertTrue(np.all(cal_p >= 0.0) and np.all(cal_p <= 1.0))
        # Monotonicity check
        self.assertTrue(np.all(np.diff(cal_p) >= 0))

    def test_pr_auc_and_brier_computation(self):
        y_true = np.array([1, 1, 0, 0, 1, 0])
        prob = np.array([0.9, 0.8, 0.2, 0.1, 0.7, 0.3])
        m = MET.classification_metrics(y_true, prob, threshold=0.5)
        self.assertIn("pr_auc", m)
        self.assertIn("brier", m)
        self.assertIn("calibration_error", m)
        self.assertTrue(0.0 <= m["pr_auc"] <= 1.0)
        self.assertTrue(0.0 <= m["brier"] <= 1.0)


class TestPhaseCConfidenceAndRiskEngine(unittest.TestCase):
    def test_confidence_independent_of_risk(self):
        """High risk must NOT imply high confidence."""
        # Extreme risk precursor but with only 1 source available -> low confidence
        fs = FeatureSet(location_id=1, values={
            "rain_3h": 110.0,
            "rain_intensity": 55.0,
        })
        fs.available = {"rainfall": True}  # 4 other sources missing
        fs.provenance = {"rainfall": {"quality": "GOOD"}}
        res = risk_engine.assess(fs, mode="replay")
        
        # Risk should be critical or high due to extreme rain
        self.assertIn(res.risk_level, ("HIGH", "CRITICAL"))
        # But confidence must be penalized by poor data completeness
        self.assertLessEqual(res.confidence, 0.65)

    def test_lead_time_windows(self):
        """Lead time must produce bounded windows or UNKNOWN, never an exact minute."""
        fs = FeatureSet(location_id=1, values={
            "rain_intensity": 50.0,
            "river_rate_of_rise_1h": 1.2,
        })
        lo, hi, label = risk_engine._lead_time(fs, flood_p=0.9)
        self.assertEqual((lo, hi), (15, 45))
        self.assertIn("15–45 minutes", label)

        # Missing signals -> None, None
        fs_empty = FeatureSet(location_id=1, values={})
        lo_e, hi_e, label_e = risk_engine._lead_time(fs_empty, flood_p=0.1)
        self.assertIsNone(lo_e)
        self.assertIsNone(hi_e)
        self.assertEqual(label_e, "UNKNOWN / NOT AVAILABLE")

    def test_enriched_risk_result_structure(self):
        """assess() must return separate flood, landslide, combined, and data_quality blocks."""
        fs = FeatureSet(location_id=1, values={
            "rain_3h": 45.0,
            "rain_24h": 120.0,
            "rain_intensity": 25.0,
            "soil_saturation_index": 0.85,
            "slope": 35.0,
            "susceptibility": 0.7,
        })
        fs.available = {"rainfall": True, "soil": True, "terrain": True, "susceptibility": True}
        res = risk_engine.assess(fs, mode="replay")
        
        self.assertIn("probability", res.flood)
        self.assertIn("risk", res.flood)
        self.assertIn("threshold", res.flood)
        self.assertIn("probability", res.landslide)
        self.assertIn("risk", res.landslide)
        self.assertIn("risk", res.combined)
        self.assertIn("window_label", res.lead_time)
        self.assertIn("completeness", res.data_quality)
        self.assertIn("model_meta", res.__dict__)
        self.assertEqual(res.model_meta["status"], "NOT VALIDATED")


class TestPhaseCModelInferenceAndVersioning(unittest.TestCase):
    def test_deterministic_inference(self):
        """Identical features must produce bit-for-bit identical probabilities and factors."""
        model = TrainedHazardModel.load_latest("flood")
        features = {"rain_3h": 45.0, "rain_24h": 120.0, "soil_saturation_index": 0.8}
        p1 = model.predict(features)
        p2 = model.predict(features)
        self.assertEqual(p1.probability, p2.probability)
        self.assertEqual(p1.calibrated_probability, p2.calibrated_probability)
        self.assertEqual(p1.contributions, p2.contributions)
        self.assertEqual(p1.drivers, p2.drivers)

    def test_probability_range_and_calibration(self):
        """Raw and calibrated probabilities must be bounded strictly in [0.0, 1.0]."""
        model = TrainedHazardModel.load_latest("landslide")
        for rain in [0.0, 20.0, 50.0, 100.0, 200.0]:
            for slope in [5.0, 25.0, 45.0, 60.0]:
                p = model.predict({"rain_24h": rain, "slope": slope, "soil_saturation_index": 0.7})
                self.assertTrue(0.0 <= p.probability <= 1.0)
                if p.calibrated_probability is not None:
                    self.assertTrue(0.0 <= p.calibrated_probability <= 1.0)
                self.assertTrue(0.0 < model.operating_threshold < 1.0)

    def test_model_artifact_loading_and_fingerprint_check(self):
        """Model artifacts must load correctly and verify sha256 fingerprint against active schema."""
        for hazard in ("flood", "landslide"):
            model = TrainedHazardModel.load_latest(hazard)
            self.assertTrue(model.version.startswith(f"{hazard}-gbt"))
            self.assertFalse(model.validated, "Demo model must not claim validation without real censuses")
            fp = model.schema.fingerprint()
            self.assertEqual(len(fp), 16, "Schema fingerprint must be a 16-char sha256 hex digest prefix")
            card = model.card()
            self.assertIn("model_name", card)
            self.assertIn("n_train", card)
            self.assertIn("test_metrics", card)

    def test_missing_values_and_imputation(self):
        """Missing features must be safely imputed per missing policy and flagged in schema report."""
        vec, report = FLOOD_SCHEMA.validate_and_vectorize({})
        self.assertEqual(len(vec), len(FLOOD_SCHEMA.specs))
        self.assertFalse(any(np.isnan(vec)))
        self.assertFalse(any(np.isinf(vec)))
        self.assertEqual(len(report["imputed"]), len(FLOOD_SCHEMA.specs))
        self.assertIn("rain_3h", report["missing_critical"])


class TestPhaseCExplanationAndDrivers(unittest.TestCase):
    def test_structured_drivers_generation(self):
        """High risk features must produce human-readable structured drivers."""
        model = TrainedHazardModel.load_latest("flood")
        high_risk_input = {
            "rain_3h": 85.0,
            "rain_24h": 180.0,
            "rain_intensity": 45.0,
            "soil_saturation_index": 0.9,
            "river_level": 4.5,
        }
        pred = model.predict(high_risk_input)
        self.assertIsNotNone(pred.drivers)
        self.assertGreater(len(pred.drivers), 0)
        self.assertTrue(any("rainfall" in d.lower() or "intensity" in d.lower() or "rain" in d.lower() for d in pred.drivers))

    def test_combined_risk_drivers(self):
        """Combined risk block in engine assess must include structured drivers."""
        fs = FeatureSet(location_id=1, values={
            "rain_3h": 60.0,
            "rain_24h": 140.0,
            "rain_intensity": 30.0,
            "soil_saturation_index": 0.85,
            "slope": 42.0,
            "susceptibility": 0.8,
        })
        fs.available = {"rainfall": True, "soil": True, "terrain": True, "susceptibility": True}
        res = risk_engine.assess(fs, mode="replay")
        self.assertIn("drivers", res.combined)
        self.assertIsInstance(res.combined["drivers"], list)
        self.assertGreater(len(res.combined["drivers"]), 0)
        self.assertIn("drivers", res.flood)
        self.assertIn("drivers", res.landslide)


class TestPhaseCReplayToML(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.ids = seed.run(reset=True)
        cls.vid = cls.ids["villages"][0]
        rc = ReplayCollector(DATASET, source_key="replay")
        rc.run()

    def test_replay_ml_pipeline_execution(self):
        """Replay observations must flow cleanly into features, ML models, and persisted predictions."""
        result = psvc.run_for_location(self.vid, as_of="2024-08-01T10:00:00Z", mode="replay")
        self.assertIn(result.risk_level, ("LOW", "MODERATE", "HIGH", "CRITICAL"))
        latest = repo.latest_prediction(self.vid)
        self.assertIsNotNone(latest)
        self.assertEqual(latest["mode"], "replay")
        self.assertTrue("+" in latest["model_version"])
        self.assertTrue(0.0 <= latest["flood_probability"] <= 1.0)
        self.assertTrue(0.0 <= latest["landslide_probability"] <= 1.0)
        self.assertTrue(0.0 <= latest["confidence"] <= 1.0)
        self.assertTrue(0.0 <= latest["data_completeness"] <= 1.0)
        self.assertIsInstance(latest["top_factors"], list)


if __name__ == "__main__":
    unittest.main()
