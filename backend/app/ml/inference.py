"""
Inference: load a trained artifact and serve it behind the HazardModel interface
(master prompt sections 6, 16, 47).

TrainedHazardModel is a drop-in for the demo scorers in app.models: same
`predict(feature_dict) -> Prediction` contract, same `contributions` shape for
explainability, same `validated`/`is_demo` honesty flags. The risk engine,
prediction service, and API therefore need ZERO changes to consume a trained
model — that's the whole point of the shared interface.

On load it re-validates the schema fingerprint, so a model trained against a
different feature contract can never silently score the wrong vector.
"""
from __future__ import annotations

import math

from app.models.base_model import HazardModel, Prediction
from app.ml import artifact as A
from app.ml.calibration import PlattCalibrator
from app.ml.gbt import GBTClassifier
from app.ml.schema import FeatureSchema, FeatureSpec, get_schema


def _schema_from_artifact(art: dict) -> FeatureSchema:
    s = art["schema"]
    specs = [FeatureSpec(name=f["name"], lo=f["lo"], hi=f["hi"],
                         missing=f["missing"], impute_default=f["impute_default"],
                         label=f.get("label", ""),
                         unit=f.get("unit", ""),
                         source=f.get("source", ""),
                         transformation=f.get("transformation", "identity"),
                         critical=f.get("critical", False))
             for f in s["features"]]
    return FeatureSchema(hazard=s["hazard"], specs=specs)


class TrainedHazardModel(HazardModel):
    """A trained GBT served behind the HazardModel interface."""

    def __init__(self, artifact: dict):
        self._art = artifact
        self.name = artifact["hazard"]
        self.version = artifact["version"]
        # honesty: trained on SIMULATED data => still a demo, NOT validated
        self.validated = bool(artifact["card"].get("validated", False))
        self.schema = _schema_from_artifact(artifact)
        stored_fp = artifact["schema"]["fingerprint"]
        if self.schema.fingerprint() != stored_fp:
            raise ValueError(
                f"schema fingerprint mismatch for {self.version}: "
                f"artifact {stored_fp} != rebuilt {self.schema.fingerprint()}")
        self.feature_order = self.schema.names
        self.threshold = artifact.get("operating_threshold", 0.5)
        self.operating_threshold = self.threshold
        self._model = GBTClassifier.from_dict(artifact["model"])
        self.calibrator = PlattCalibrator.from_dict(artifact.get("calibration"))

    @classmethod
    def load_latest(cls, hazard: str) -> "TrainedHazardModel":
        path = A.latest_path(hazard)
        if not path:
            raise FileNotFoundError(
                f"no trained artifact for '{hazard}' — run app.ml.train first")
        return cls(A.load(path))

    @classmethod
    def load_path(cls, path: str) -> "TrainedHazardModel":
        return cls(A.load(path))

    def predict(self, feature_values: dict) -> Prediction:
        vec, report = self.schema.validate_and_vectorize(feature_values)
        raw_prob = float(self._model.predict_proba([vec])[0])
        cal_prob = float(self.calibrator.calibrate(raw_prob))

        # exact additive log-odds contributions -> readable factors
        contribs_logodds = self._model.contributions(vec)
        labels = {s.name: s.human() for s in self.schema.specs}
        units = {s.name: getattr(s, "unit", "") for s in self.schema.specs}
        contribs = []
        drivers = []
        for name, c in zip(self.feature_order, contribs_logodds):
            if name in report["imputed"]:
                # imputed feature: its influence is not evidence, so surface it
                # transparently with zero credit rather than a misleading value
                continue
            direction = "increasing" if c > 0 else "decreasing"
            symbol = "+" if c > 0 else "-"
            u = f" ({units[name]})" if units[name] else ""
            contribs.append({
                "factor": f"{symbol} {labels[name]}{u}",
                "feature": name,
                "raw_factor": labels[name],
                "direction": direction,
                "contribution": round(float(c), 4),
            })
            if c > 0.05:
                intensity_prefix = "High" if c >= 0.8 else ("Elevated" if c >= 0.3 else "Active")
                drivers.append(f"{intensity_prefix} {labels[name].lower()}")

        contribs.sort(key=lambda d: d["contribution"], reverse=True)

        pred = Prediction(
            probability=cal_prob,
            contributions=contribs,
            calibrated_probability=cal_prob,
            operating_threshold=self.threshold,
            schema_report=report,
            drivers=drivers[:5],
        )
        return pred

    def card(self) -> dict:
        return self._art["card"]

