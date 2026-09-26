"""GSI / Bhusanket portal layer registry -> internal catalog mapping (pure
Python, no heavy deps).

These functions convert an entry of the vendored, ChatGPT-verified GSI_LAYERS
registry (app/data_layer/sources/gsi_bhusanket/sih_gsi/registry.py) into the
internal `gsi_layers` catalog-record shape. They are dependency-free (no httpx,
no pydantic) so they can be unit-tested anywhere and so the honesty-critical
invariant — "a GSI portal layer / bulletin link is NOT a numeric landslide
susceptibility or probability" — is provable.

KEY INVARIANT (verified spec gsi_verified.md: "This adapter intentionally does
not hard-code an undocumented JSON API"; GSI forecasting is REGIONAL, "must NOT
claim that GSI provides a nationwide real-time landslide forecast API"): a
catalog record ALWAYS has stage='CATALOG_ONLY' and carries no measured value.
Each record preserves the verified geographic_scope COVERAGE note so downstream
code can honestly mark GSI as unavailable outside its coverage rather than
fabricate a forecast. Real GSI inventory/bulletin values only enter after a
separate, gated, verified parse of a specific documented public resource — never
here. The ML landslide model reads landslide_data and NEVER reads gsi_layers, so
a catalog row can never masquerade as a landslide value.

Nothing is fabricated: layer_key, role, url (service_url) and geographic_scope
come verbatim from the verified registry.
"""
from __future__ import annotations

import json
from typing import Any

CATALOG_ONLY = "CATALOG_ONLY"
PARSED = "PARSED"


def registry_entry_to_catalog_record(
    layer_key: str,
    entry: dict[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict:
    """Map one GSI_LAYERS registry entry to exactly one catalog record.

    role, service_url and geographic_scope are copied VERBATIM from the verified
    registry; no endpoint or coverage claim is invented. Every record has
    stage='CATALOG_ONLY' and carries no numeric landslide value by design."""
    role = entry.get("role")
    service_url = entry.get("url")
    scope = entry.get("geographic_scope")
    public = entry.get("public", True)

    raw_ref = json.dumps({
        "layer_key": layer_key,
        "role": role,
        "url": service_url,
        "geographic_scope": scope,
    }, sort_keys=True, default=str)

    return {
        "source": "gsi",
        "layer_key": layer_key,
        "role": role,
        "service_url": service_url,
        # Verified COVERAGE note (regional, NOT nationwide). Preserved so the app
        # can honestly mark GSI unavailable outside coverage, never fabricate.
        "geographic_scope": scope,
        "public": bool(public),
        # INVARIANT: a catalog entry is a portal layer, never a landslide
        # susceptibility/probability. No numeric value is produced here.
        "stage": CATALOG_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def registry_to_catalog_records(
    registry: dict[str, dict[str, Any]],
    *,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map the whole GSI_LAYERS registry to a flat list of catalog records
    (one per registry entry)."""
    return [registry_entry_to_catalog_record(layer_key, entry,
                                             retrieved_at=retrieved_at)
            for layer_key, entry in (registry or {}).items()]
