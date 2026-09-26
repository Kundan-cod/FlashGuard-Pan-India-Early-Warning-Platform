"""
Model artifact: save / load / version (master prompt section 6).

An artifact is a single self-describing JSON file (no pickle — safe to inspect,
diff, and load across Python versions) containing:
  * the trained GBT (plain-dict form),
  * the exact feature schema + its fingerprint (re-validated on load),
  * a MODEL CARD with the ACTUAL held-out metrics, data source (SIMULATED),
    training config, and honesty flags (validated=False, is_demo=True).

Versioning: version string is  "<hazard>-gbt-<schema_fp>-<YYYYMMDDHHMMSS>".
The registry keeps a `latest.json` pointer per hazard so inference can load the
current model without hard-coding a filename, and every trained version is kept
on disk so results are reproducible/auditable.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

ARTIFACT_ENV = "ML_ARTIFACT_DIR"


def artifact_dir() -> str:
    """Where model artifacts live. Overridable via env for tests / Track B."""
    d = os.environ.get(ARTIFACT_ENV)
    if not d:
        here = os.path.dirname(os.path.abspath(__file__))
        # backend/app/ml -> repo/ml/artifacts
        d = os.path.abspath(os.path.join(here, "..", "..", "..", "ml", "artifacts"))
    os.makedirs(d, exist_ok=True)
    return d


def make_version(hazard: str, schema_fp: str, when: datetime | None = None) -> str:
    ts = (when or datetime.now(timezone.utc)).strftime("%Y%m%d%H%M%S")
    return f"{hazard}-gbt-{schema_fp}-{ts}"


def save(artifact: dict) -> str:
    """Write an artifact dict; update the per-hazard latest pointer. Returns path."""
    hazard = artifact["hazard"]
    version = artifact["version"]
    d = artifact_dir()
    path = os.path.join(d, f"{version}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(artifact, f, indent=2, sort_keys=True)
    # latest pointer
    with open(os.path.join(d, f"latest-{hazard}.json"), "w", encoding="utf-8") as f:
        json.dump({"hazard": hazard, "version": version,
                   "path": os.path.basename(path)}, f, indent=2)
    return path


def load(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def latest_path(hazard: str) -> str | None:
    d = artifact_dir()
    ptr = os.path.join(d, f"latest-{hazard}.json")
    if not os.path.exists(ptr):
        return None
    with open(ptr, "r", encoding="utf-8") as f:
        meta = json.load(f)
    p = os.path.join(d, meta["path"])
    return p if os.path.exists(p) else None


def list_versions(hazard: str | None = None) -> list:
    d = artifact_dir()
    out = []
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".json") or fn.startswith("latest-"):
            continue
        if hazard and not fn.startswith(f"{hazard}-"):
            continue
        out.append(fn[:-5])
    return out
