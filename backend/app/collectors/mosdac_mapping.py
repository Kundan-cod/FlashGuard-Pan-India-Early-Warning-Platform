"""ISRO MOSDAC INSAT granule discovery -> internal mapping helpers (pure Python,
no heavy deps).

These functions convert a MOSDAC mdapi granule (as discovered by the vendored,
ChatGPT-verified MosdacCollector in app/data_layer/sources/mosdac) into the
internal `mosdac_discovery` record shape. They are deliberately dependency-free
(no httpx, no pydantic) so they can be unit-tested in any environment and so the
honesty-critical logic — "a granule filename/download URL is NOT a rainfall
number" — is provable.

KEY INVARIANT (master prompt: never invent measurements; verified spec
mosdac_verified.md: "raw satellite files parsed by separate product parser; ML
must consume normalized values from the internal database, never call MOSDAC
directly"): a discovery record ALWAYS has numeric_value=None and
stage='DISCOVERY_ONLY'. A real mm value is produced only by a separate, gated
raster/HDF-parse stage, never here.

satellite / resolution are read from the vendored MOSDAC_DATASETS registry keyed
by dataset_id — NOT invented. If a dataset_id is not in the registry those fields
are left None rather than guessed.

The bridge collector converts each vendored `MosdacGranule` (pydantic) into a
plain dict of the shape below before calling these functions, so this module
never imports the vendored package or its deps.
"""
from __future__ import annotations

import json
from typing import Any

DISCOVERY_ONLY = "DISCOVERY_ONLY"
RASTER_SAMPLED = "RASTER_SAMPLED"


def _registry_lookup(dataset_id: str | None) -> dict[str, Any]:
    """Best-effort satellite/resolution/product lookup from the vendored
    MOSDAC_DATASETS registry (verified metadata), keyed by the mdapi dataset_id
    (e.g. '3RIMG_L2B_HEM'). Returns {} if the registry is unavailable or the id
    is unknown — nothing is fabricated."""
    if not dataset_id:
        return {}
    try:
        from app.data_layer.sources.mosdac.sih_mosdac.registry import (
            MOSDAC_DATASETS)
    except Exception:  # noqa: BLE001 — registry absent -> degrade to no metadata
        return {}
    for entry in MOSDAC_DATASETS.values():
        if entry.get("dataset_id") == dataset_id:
            return entry
    return {}


def granule_to_discovery_record(
    granule: dict[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict:
    """Map one MOSDAC granule (plain dict) to a single internal discovery record.
    numeric_value is ALWAYS None here by design.

    Expected granule dict keys (mirrors the vendored MosdacGranule contract):
        dataset_id, granule_id, title, start_time, end_time, download_url,
        metadata (dict)

    satellite / resolution / product come from the verified MOSDAC_DATASETS
    registry (never invented). A granule with no download URL still yields a
    record (download_url=None) so the discovery is not silently lost, but it can
    never be mistaken for a measurement (numeric_value stays None; never touches
    rainfall_observations)."""
    dataset_id = granule.get("dataset_id")
    reg = _registry_lookup(dataset_id)

    raw_ref = json.dumps({
        "dataset_id": dataset_id,
        "granule_id": granule.get("granule_id"),
        "title": granule.get("title"),
        "metadata": granule.get("metadata"),
    }, sort_keys=True, default=str)

    return {
        "source": "mosdac",
        "dataset_id": dataset_id,
        "satellite": reg.get("satellite"),
        # MOSDAC description is the product label (e.g. "Hydro-Estimator
        # precipitation"); preserved verbatim, not an ML value.
        "product": reg.get("description"),
        "observed_date": _as_str(granule.get("start_time")),
        "end_time": _as_str(granule.get("end_time")),
        # MOSDAC granule metadata does not give a single meaningful point, so
        # footprint centroid is left None unless a caller supplies one. No
        # fabricated coordinates.
        "latitude": granule.get("latitude"),
        "longitude": granule.get("longitude"),
        # Registry "grid" string if documented (e.g. "0.25 degree x 0.25 degree").
        "resolution": reg.get("grid"),
        "download_url": granule.get("download_url"),
        "granule_id": _as_str(granule.get("granule_id")),
        # INVARIANT: discovery carries no rainfall value.
        "numeric_value": None,
        "quality_flag": "UNKNOWN",
        "stage": DISCOVERY_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def granules_to_discovery_records(
    granules: list[dict[str, Any]],
    *,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map a list of MOSDAC granule dicts to discovery records."""
    return [granule_to_discovery_record(g, retrieved_at=retrieved_at)
            for g in (granules or [])]


def _as_str(v: Any) -> str | None:
    if v is None:
        return None
    return v if isinstance(v, str) else str(v)
