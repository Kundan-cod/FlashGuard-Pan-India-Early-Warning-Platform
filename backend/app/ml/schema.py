"""
Feature schema + validation (master prompt section 6:
"feature schema validation, missing-feature handling").

A model's feature schema is an ORDERED, VERSIONED contract: exactly which
features go in, in what order, with what valid range, and what to do when one is
missing. Training and inference MUST use the identical schema, so it is stored
inside the saved model artifact and re-validated on load (guards against a
feature-order drift silently corrupting predictions).

Missing-feature policy is EXPLICIT per feature, never a silent zero:
  * IMPUTE  -> substitute a declared, documented default AND flag it, so the
               risk engine can lower confidence (absence is surfaced, not faked).
  * REQUIRED -> refuse to predict; a required feature cannot be guessed.
"""
from __future__ import annotations

from dataclasses import dataclass, field


class MissingPolicy:
    IMPUTE = "IMPUTE"
    REQUIRED = "REQUIRED"


@dataclass(frozen=True)
class FeatureSpec:
    name: str
    lo: float                 # expected physical low (for range validation / scaling)
    hi: float                 # expected physical high
    missing: str = MissingPolicy.IMPUTE
    impute_default: float = 0.0
    label: str = ""           # human-readable, for explainability output
    unit: str = ""            # physical unit (mm, mm/hr, m, m/h, degrees, index)
    source: str = ""          # expected observation source (IMD, CWC, SMAP, DEM, etc.)
    transformation: str = "identity" # normalization/scaling rule
    critical: bool = False    # True if missing this feature substantially impairs prediction

    def human(self) -> str:
        return self.label or self.name


@dataclass
class FeatureSchema:
    """Ordered feature contract shared by training and inference."""
    hazard: str
    specs: list  # list[FeatureSpec], order is significant

    @property
    def names(self) -> list:
        return [s.name for s in self.specs]

    def fingerprint(self) -> str:
        """Stable hash of the ordered contract; stored in the model artifact and
        checked on load so a schema drift can never pass silently."""
        import hashlib
        payload = "|".join(
            f"{s.name}:{s.lo}:{s.hi}:{s.missing}:{s.impute_default}"
            for s in self.specs
        )
        return hashlib.sha256(payload.encode()).hexdigest()[:16]

    # -- validation / vectorization -------------------------------------------
    def validate_and_vectorize(self, features: dict) -> tuple:
        """Turn a feature dict into an ordered numeric vector.

        Returns (vector, report) where report describes what happened:
          {"imputed": [...names], "out_of_range": [...names], "used": [...names],
           "missing_critical": [...names], "completeness": float}

        Raises ValueError if a REQUIRED feature is missing or non-finite.
        """
        import math
        vec = []
        imputed, out_of_range, used, missing_critical = [], [], [], []
        for s in self.specs:
            v = features.get(s.name)
            if v is None or (isinstance(v, float) and math.isnan(v)):
                if s.missing == MissingPolicy.REQUIRED:
                    raise ValueError(
                        f"required feature '{s.name}' missing for hazard "
                        f"'{self.hazard}' — refusing to predict on a guess")
                v = s.impute_default
                imputed.append(s.name)
                if s.critical:
                    missing_critical.append(s.name)
            else:
                v = float(v)
                used.append(s.name)
                if v < s.lo or v > s.hi:
                    out_of_range.append(s.name)
            vec.append(v)
        
        completeness = len(used) / len(self.specs) if self.specs else 0.0
        report = {
            "imputed": imputed,
            "out_of_range": out_of_range,
            "used": used,
            "missing_critical": missing_critical,
            "completeness": round(completeness, 3),
        }
        return vec, report


# ---------------------------------------------------------------------------
# Canonical schemas. Feature names MATCH app.features.engineer output exactly,
# so a FeatureSet flows straight into a trained model with no remapping.
# ---------------------------------------------------------------------------
FLOOD_SCHEMA = FeatureSchema(
    hazard="flood",
    specs=[
        FeatureSpec("rain_3h",               0, 120,  label="Rainfall last 3h",           unit="mm",      source="IMD/GPM",              transformation="identity", critical=True),
        FeatureSpec("rain_24h",              0, 300,  label="Rainfall last 24h",          unit="mm",      source="IMD/GPM",              transformation="identity", critical=False),
        FeatureSpec("rain_intensity",        0, 60,   label="Rainfall intensity (30m)",   unit="mm/hr",   source="IMD/AWS/Radar",        transformation="identity", critical=True),
        FeatureSpec("soil_saturation_index", 0, 1,    label="Soil saturation",            unit="fraction",source="SMAP/MOSDAC/In-situ",  transformation="min_max_0_1", critical=True),
        FeatureSpec("river_level",           0, 10,   label="River level",                unit="m",       source="CWC/IoT Gauge",        transformation="identity", critical=False),
        FeatureSpec("river_rate_of_rise_1h", 0, 1.5,  label="River rate of rise",         unit="m/h",     source="CWC/IoT Gauge",        transformation="identity", critical=False),
        FeatureSpec("flow_accumulation",     0, 5000, label="Upstream flow accumulation", unit="cells",   source="CartoDEM/HydroSHEDS",  transformation="identity", critical=False),
        FeatureSpec("slope",                 0, 60,   label="Slope (fast runoff)",        unit="degrees", source="Bhuvan/SRTM DEM",      transformation="identity", critical=False),
        FeatureSpec("susceptibility",        0, 1,    label="Historical susceptibility",  unit="index",   source="GSI/NRSC Atlas",       transformation="min_max_0_1", critical=False),
    ],
)

LANDSLIDE_SCHEMA = FeatureSchema(
    hazard="landslide",
    specs=[
        FeatureSpec("slope",                 0, 60,   label="Slope steepness",           unit="degrees", source="Bhuvan/SRTM DEM",      transformation="identity", critical=True),
        FeatureSpec("curvature",            -1, 1,    label="Slope curvature",           unit="index",   source="Bhuvan/SRTM DEM",      transformation="identity", critical=False),
        FeatureSpec("susceptibility",        0, 1,    label="GSI-style susceptibility",  unit="index",   source="GSI Landslide Atlas",  transformation="min_max_0_1", critical=True),
        FeatureSpec("relative_relief",       0, 1500, label="Relative relief",           unit="m",       source="Bhuvan/SRTM DEM",      transformation="identity", critical=False),
        FeatureSpec("rain_24h",              0, 300,  label="Rainfall last 24h",         unit="mm",      source="IMD/GPM",              transformation="identity", critical=True),
        FeatureSpec("rain_3h",               0, 120,  label="Rainfall last 3h",          unit="mm",      source="IMD/GPM",              transformation="identity", critical=False),
        FeatureSpec("soil_saturation_index", 0, 1,    label="Soil saturation",           unit="fraction",source="SMAP/MOSDAC/In-situ",  transformation="min_max_0_1", critical=True),
    ],
)


def get_schema(hazard: str) -> FeatureSchema:
    h = hazard.lower()
    if h == "flood":
        return FLOOD_SCHEMA
    if h == "landslide":
        return LANDSLIDE_SCHEMA
    raise ValueError(f"no schema for hazard '{hazard}'")

