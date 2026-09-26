"""CWC / NWIC NWDP dataset registry -> internal catalog mapping (pure Python, no
heavy deps).

These functions convert an entry of the vendored, ChatGPT-verified
CWC_NWIC_DATASETS registry (app/data_layer/sources/cwc_nwic/sih_cwc/registry.py)
into the internal `cwc_resources` catalog-record shape. They are dependency-free
(no httpx, no pydantic) so they can be unit-tested anywhere and so the honesty-
critical invariant — "a CWC/NWIC NWDP dataset page is NOT a numeric river-level or
rainfall value" — is provable.

KEY INVARIANT (verified spec cwc_nwic_verified.md: "This package intentionally
does not invent an undocumented API URL"; the portal advertises API as a format
but "the exact API endpoint/auth contract was not verified in this pass"; "Do not
claim that every station is live or that every API is anonymous"): a catalog
record ALWAYS has stage='CATALOG_ONLY' and carries no measured value. Each record
records the verified dataset-page URL (base_url + registry path), the advertised
resource format and the verified cadence VERBATIM. Real CWC river-level/rainfall
values only enter river_observations / rainfall_observations after a separate,
gated, verified CSV/API parse of a specific dataset resource — never here. The ML
feature pipeline reads those observation tables and NEVER reads cwc_resources, so
a catalog row can never masquerade as a hydrological value.

Nothing is fabricated: dataset_key, role, path, format and frequency come verbatim
from the verified registry; the dataset_url is the verified public NWDP base_url
joined with the verified registry path (never an invented endpoint).
"""
from __future__ import annotations

import json
from typing import Any

CATALOG_ONLY = "CATALOG_ONLY"
PARSED = "PARSED"

# The verified public National Water Data Portal base URL, from the vendored
# NwicConfig default (sih_cwc/config.py: NWDP_BASE_URL). Kept here as a module
# constant so the pure mapping is testable without importing the httpx-bearing
# client/config; the collector passes the live configured base_url through.
DEFAULT_NWDP_BASE_URL = "https://www.nwdp.nwic.gov.in"


def registry_entry_to_catalog_record(
    dataset_key: str,
    entry: dict[str, Any],
    *,
    base_url: str = DEFAULT_NWDP_BASE_URL,
    retrieved_at: str | None = None,
) -> dict:
    """Map one CWC_NWIC_DATASETS registry entry to exactly one catalog record.

    role, resource format and frequency are copied VERBATIM from the verified
    registry; the dataset_url is the verified public NWDP base_url joined with the
    verified registry path — no endpoint is invented. Every record has
    stage='CATALOG_ONLY' and carries no numeric hydrological value by design."""
    role = entry.get("role")
    path = entry.get("path")
    resource_format = entry.get("format")
    frequency = entry.get("frequency")

    dataset_url = None
    if path:
        dataset_url = base_url.rstrip("/") + path

    raw_ref = json.dumps({
        "dataset_key": dataset_key,
        "role": role,
        "path": path,
        "format": resource_format,
        "frequency": frequency,
    }, sort_keys=True, default=str)

    return {
        "source": "cwc",
        "dataset_key": dataset_key,
        "role": role,
        # Verified NWDP dataset-page URL (base_url + verified path). NOT an API
        # endpoint: the verified note forbids inventing an undocumented API URL.
        "dataset_url": dataset_url,
        # Advertised resource format(s), verbatim (e.g. "CSV/API"). This is what
        # the portal ADVERTISES; it is not a promise that the API is anonymous.
        "resource_format": resource_format,
        "frequency": frequency,
        # INVARIANT: a catalog entry is a dataset page, never a numeric river-
        # level/rainfall value. No numeric value is produced here.
        "stage": CATALOG_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def registry_to_catalog_records(
    registry: dict[str, dict[str, Any]],
    *,
    base_url: str = DEFAULT_NWDP_BASE_URL,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map the whole CWC_NWIC_DATASETS registry to a flat list of catalog records
    (one per registry entry)."""
    return [registry_entry_to_catalog_record(dataset_key, entry,
                                             base_url=base_url,
                                             retrieved_at=retrieved_at)
            for dataset_key, entry in (registry or {}).items()]
