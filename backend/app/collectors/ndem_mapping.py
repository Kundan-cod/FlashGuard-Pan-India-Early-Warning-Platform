"""NDEM capability registry -> internal catalog mapping (pure Python, no heavy deps).

These functions convert an entry of the vendored, ChatGPT-verified NDEM_CAPABILITIES
registry (app/data_layer/sources/ndem/sih_ndem/registry.py) into the internal
`ndem_capabilities` catalog-record shape. They are dependency-free (no httpx, no
pydantic) so they can be unit-tested anywhere and so the honesty-critical invariants
are provable.

KEY INVARIANTS (verified spec ndem_verified.md / README.md):
  1. NDEM's non-base products are PROTECTED: "the portal is protected and requires
     username/password obtained through an authorization form"; authorized users are
     Central/State/District/NDRF/SDRF officials; only public/base layers may be
     visible without login. The vendored package "does not invent private API
     endpoints" and must "never bypass authentication." So a catalog record is a
     CAPABILITY description — a name + an access classification + a role + the
     verified public portal URL — never a measurement, an event, a geometry or a
     private endpoint.
  2. "Store access_level and source-health separately from risk score." So the
     `access` field (PUBLIC | AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC) is a
     capability-access classification copied VERBATIM from the registry; it is NOT a
     data value and never enters a risk score.
  3. A catalog record ALWAYS has stage='CATALOG_ONLY' and carries no measured value
     and no geometry. Real NDEM products would only enter observation/event tables
     after a future AUTHORIZED, gated adapter behind the same interface (a stage the
     verified package deliberately does NOT implement). The ML feature pipeline never
     reads this catalog.

Nothing is fabricated: capability_key, access and role come verbatim from the
verified registry; source_url is the verified NDEM portal URL carried by each
registry entry. Like GSI/LGD (and UNLIKE CWC/Historical which use a distinct URL per
entry), every NDEM capability is exposed through the SAME public portal URL, so
capability_key is what keeps rows distinct.
"""
from __future__ import annotations

import json
from typing import Any

CATALOG_ONLY = "CATALOG_ONLY"
PARSED = "PARSED"


def registry_entry_to_catalog_record(
    capability_key: str,
    entry: dict[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict:
    """Map one NDEM_CAPABILITIES registry entry to exactly one catalog record.

    access, role and source_url are copied VERBATIM from the verified registry
    entry (source_url is the verified NDEM public portal URL, never a private API
    endpoint). Every record has stage='CATALOG_ONLY' and carries no measurement, no
    geometry and no risk score by design. access is a capability-access
    classification stored separately from any risk score, per the verified note."""
    access = entry.get("access")
    role = entry.get("role")
    source_url = entry.get("source_url")

    raw_ref = json.dumps({
        "capability_key": capability_key,
        "access": access,
        "role": role,
        "source_url": source_url,
    }, sort_keys=True, default=str)

    return {
        "source": "ndem",
        "capability_key": capability_key,
        # Capability-access classification (PUBLIC | AUTHORIZED |
        # AUTHORIZED_OR_PRODUCT_SPECIFIC), verbatim. Stored SEPARATELY from any risk
        # score; never a data value; never used to bypass authentication.
        "access": access,
        "role": role,
        # Verified NDEM public portal URL (the single documented entry point). NDEM
        # exposes no verified private API, so this is never a fabricated endpoint.
        "source_url": source_url,
        # INVARIANT: a catalog entry is a capability description, never a
        # measurement, an event or a geometry. Nothing numeric is produced here.
        "stage": CATALOG_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def registry_to_catalog_records(
    registry: dict[str, dict[str, Any]],
    *,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map the whole NDEM_CAPABILITIES registry to a flat list of catalog records
    (one per registry entry)."""
    return [registry_entry_to_catalog_record(capability_key, entry,
                                             retrieved_at=retrieved_at)
            for capability_key, entry in (registry or {}).items()]
