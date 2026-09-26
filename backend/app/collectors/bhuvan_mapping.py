"""Bhuvan/NRSC OGC layer registry -> internal catalog mapping (pure Python, no
heavy deps).

These functions convert an entry of the vendored, ChatGPT-verified BHUVAN_LAYERS
registry (app/data_layer/sources/bhuvan_nrsc/sih_bhuvan/registry.py) into the
internal `bhuvan_layers` catalog-record shape. They are dependency-free (no httpx,
no pydantic) so they can be unit-tested anywhere and so the honesty-critical
invariant — "a WMS/WMTS layer endpoint is NOT a numeric terrain value" — is
provable.

KEY INVARIANT (verified spec bhuvan_verified.md: "Do not scrape rendered map
pixels as a substitute for the DEM"; quantitative terrain must be derived from
downloaded DEM tiles and preprocessed once — a stage the verified package does
NOT implement): a catalog record ALWAYS has stage='CATALOG_ONLY' and carries no
measured value. Real terrain values (elevation/slope/aspect/...) only enter
terrain_features after a separate, gated DEM-tile processing stage — never here.
The ML feature pipeline reads terrain_features and NEVER reads bhuvan_layers, so
a catalog row can never masquerade as a numeric terrain feature.

Nothing is fabricated: layer_key, role and service_url come verbatim from the
verified registry; service_type is split from the registry "service" string
(e.g. "WMS/WMTS"). A layer_name is only set if the registry supplies one.
"""
from __future__ import annotations

import json
from typing import Any

CATALOG_ONLY = "CATALOG_ONLY"
DEM_PROCESSED = "DEM_PROCESSED"


def registry_entry_to_catalog_record(
    layer_key: str,
    entry: dict[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict:
    """Map one BHUVAN_LAYERS registry entry to exactly one catalog record.

    `service_type` is copied VERBATIM from the registry "service" string (e.g.
    "WMS/WMTS" or "WMS") — deliberately NOT split into separate rows: the
    verified registry stores a single `verified_service_url` per layer, so
    fabricating a distinct WMTS row that reused the WMS URL would be dishonest.
    The service_url comes verbatim from the verified registry; no endpoint is
    invented. Every record has stage='CATALOG_ONLY' and carries no numeric
    value by design."""
    service = entry.get("service") or None
    service_url = entry.get("verified_service_url")
    role = entry.get("role")
    layer_name = entry.get("layer_name")  # only if the verified registry gives one

    raw_ref = json.dumps({
        "layer_key": layer_key,
        "service": service,
        "role": role,
        "verified_service_url": service_url,
    }, sort_keys=True, default=str)

    return {
        "source": "bhuvan",
        "layer_key": layer_key,
        # e.g. "WMS/WMTS" — the verbatim list of protocols the layer is served
        # over, per the verified registry. Not a measurement.
        "service_type": service,
        "role": role,
        "service_url": service_url,
        "layer_name": layer_name,
        # INVARIANT: a catalog entry is a service endpoint, never a terrain
        # measurement. No elevation/slope/etc. is produced here.
        "stage": CATALOG_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def registry_to_catalog_records(
    registry: dict[str, dict[str, Any]],
    *,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map the whole BHUVAN_LAYERS registry to a flat list of catalog records
    (one per registry entry)."""
    return [registry_entry_to_catalog_record(layer_key, entry,
                                             retrieved_at=retrieved_at)
            for layer_key, entry in (registry or {}).items()]
