"""Historical-source registry -> internal catalog mapping (pure Python, no deps).

These functions convert an entry of the vendored, ChatGPT-verified
HISTORICAL_SOURCES registry (app/data_layer/sources/historical/sih_history/
registry.py) into the internal `historical_sources` catalog-record shape. They are
dependency-free (no httpx, no pydantic) so they can be unit-tested anywhere and so
the honesty-critical invariants are provable.

KEY INVARIANTS (verified spec historical_labels_verified.md / README.md):
  1. These are AUTHORITATIVE historical-EVENT inventory SOURCES (NRSC/ISRO Landslide
     Atlas, NRSC flood-hazard zonation, Bhuvan historical flood inundation, NDEM
     historical disasters), NOT complete presence/absence censuses. "Do not
     interpret the inventory as a complete nationwide absence/presence census" and
     "Do not convert missing observations into negatives." So a catalog record is a
     pointer to a verified SOURCE — it carries NO event geometry, NO event time and
     NO training label.
  2. The labeling rule is deliberately THREE-STATE (1=confirmed/observed event,
     0=confirmed non-event ONLY where observation coverage is demonstrably adequate,
     -1=unobserved/unknown). This prevents the model from learning the false rule
     "no record = no disaster." The vendored package ships the source registry + the
     labeling RULE only — NO event rows and NO parser — so cataloging the verified
     sources is the honest boundary. Real events and their 1/0/-1 labels would only
     enter a separate events/labels table after a gated, verified inventory parse.
  3. A catalog record ALWAYS has stage='CATALOG_ONLY' and carries no measured value.
     Flood and landslide labels are kept separate; the source's own hazard is copied
     verbatim (FLOOD | LANDSLIDE | FLOOD_OR_LANDSLIDE) and never collapsed.

Nothing is fabricated: source_key, hazard, role, url (source_url), period and any
access note come verbatim from the verified registry. Unlike LGD/GSI (one shared
portal URL), the historical registry gives each source its OWN url — like CWC, the
source_url differs per row, and the natural key is (source, source_key, source_url).
"""
from __future__ import annotations

import json
from typing import Any

CATALOG_ONLY = "CATALOG_ONLY"
PARSED = "PARSED"


def registry_entry_to_catalog_record(
    source_key: str,
    entry: dict[str, Any],
    *,
    retrieved_at: str | None = None,
) -> dict:
    """Map one HISTORICAL_SOURCES registry entry to exactly one catalog record.

    hazard, role, source_url (registry `url`), period and access_note (registry
    `access` when present) are copied VERBATIM from the verified registry. Every
    record has stage='CATALOG_ONLY' and carries no event geometry, no event time
    and no training label by design."""
    hazard = entry.get("hazard")
    role = entry.get("role")
    source_url = entry.get("url")
    period = entry.get("period")
    # `access` is only present on portal/auth-dependent sources (e.g. NDEM).
    access_note = entry.get("access")

    raw_ref = json.dumps({
        "source_key": source_key,
        "hazard": hazard,
        "role": role,
        "url": source_url,
        "period": period,
        "access": access_note,
    }, sort_keys=True, default=str)

    return {
        "source": "historical",
        "source_key": source_key,
        # Verified hazard, kept verbatim; flood and landslide labels stay separate
        # and this is never collapsed to an ML probability.
        "hazard": hazard,
        "role": role,
        # Verified official source URL (never fabricated). Each source has its own.
        "source_url": source_url,
        "period": period,
        "access_note": access_note,
        # INVARIANT: a catalog entry is a verified SOURCE pointer, never a confirmed
        # event and never a 1/0/-1 label. No geometry / no value is produced here.
        "stage": CATALOG_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def registry_to_catalog_records(
    registry: dict[str, dict[str, Any]],
    *,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map the whole HISTORICAL_SOURCES registry to a flat list of catalog records
    (one per registry entry)."""
    return [registry_entry_to_catalog_record(source_key, entry,
                                             retrieved_at=retrieved_at)
            for source_key, entry in (registry or {}).items()]
