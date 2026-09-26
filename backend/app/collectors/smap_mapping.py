"""
SMAP CMR granule discovery -> internal mapping helpers (pure Python, no heavy deps).

These functions convert a NASA SMAP CMR granule (as discovered by the vendored,
ChatGPT-verified SmapCollector in app/data_layer/sources/smap) into the internal
`smap_discovery` record shape. They are deliberately dependency-free (no httpx,
no pydantic) so they can be unit-tested in any environment and so the honesty-
critical logic — "a granule footprint/filename is NOT a soil-moisture number" —
is provable.

KEY INVARIANT (master prompt: never invent measurements; verified spec
smap_verified.md "Do not treat CMR metadata, footprint polygons, or filenames as
numeric soil-moisture measurements"): a discovery record ALWAYS has
surface_sm=None and rootzone_sm=None and stage='DISCOVERY_ONLY'. Real m3/m3
values are produced only by a separate, gated HDF5/NetCDF parse stage, never here.

The bridge collector converts each vendored `SmapGranule` (pydantic) into a plain
dict of the shape below before calling these functions, so this module never
imports the vendored package or its deps.
"""
from __future__ import annotations

import json
from typing import Any

DISCOVERY_ONLY = "DISCOVERY_ONLY"
RASTER_SAMPLED = "RASTER_SAMPLED"


def granule_to_discovery_records(
    granule: dict[str, Any],
    *,
    version: str | None = None,
    grid: str | None = None,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map one CMR granule (plain dict) to zero-or-more internal discovery
    records (one per documented GET DATA URL). surface_sm/rootzone_sm are ALWAYS
    None here by design.

    Expected granule dict keys (mirrors the vendored SmapGranule contract):
        concept_id, producer_granule_id, title, start_time, end_time,
        downloadable_urls (list[str]), metadata (dict)

    A granule with no download URL still yields one record (url=None) so the
    discovery is not silently lost, but it can never be mistaken for a
    measurement (surface_sm/rootzone_sm stay None; never touches
    soil_moisture_observations)."""
    concept_id = granule.get("concept_id")
    urls = granule.get("downloadable_urls") or []

    raw_ref = json.dumps({
        "concept_id": concept_id,
        "producer_granule_id": granule.get("producer_granule_id"),
        "title": granule.get("title"),
    }, sort_keys=True, default=str)

    base = {
        "source": "smap",
        "product": _short_name_from(granule, default="SPL4SMAU"),
        "version": version,
        "observed_date": _as_str(granule.get("start_time")),
        "end_time": _as_str(granule.get("end_time")),
        # SMAP L4 is a global gridded product; CMR granule metadata does not give
        # a single meaningful point, so footprint centroid is left None unless a
        # caller supplies one. No fabricated coordinates.
        "latitude": granule.get("latitude"),
        "longitude": granule.get("longitude"),
        "grid": grid,
        "concept_id": concept_id,
        "producer_granule_id": granule.get("producer_granule_id"),
        # INVARIANT: discovery carries no soil-moisture value.
        "surface_sm": None,
        "rootzone_sm": None,
        "quality_flag": "UNKNOWN",
        "stage": DISCOVERY_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }

    if not urls:
        return [{**base, "download_url": None}]
    return [{**base, "download_url": u} for u in urls]


def granules_to_discovery_records(
    granules: list[dict[str, Any]],
    *,
    version: str | None = None,
    grid: str | None = None,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map a list of CMR granule dicts to discovery records."""
    out: list[dict] = []
    for g in granules or []:
        out.extend(granule_to_discovery_records(
            g, version=version, grid=grid, retrieved_at=retrieved_at))
    return out


def _short_name_from(granule: dict[str, Any], default: str) -> str:
    """Best-effort product short_name from the granule title/metadata without
    inventing anything; falls back to the configured collection default."""
    title = granule.get("title") or ""
    for sn in ("SPL4SMAU", "SPL4SMGP", "SPL4SMLM"):
        if sn in title:
            return sn
    return default


def _as_str(v: Any) -> str | None:
    if v is None:
        return None
    return v if isinstance(v, str) else str(v)
