"""LGD directory registry -> internal catalog mapping (pure Python, no heavy deps).

These functions convert an entry of the vendored, ChatGPT-verified LGD_DATASETS
registry (app/data_layer/sources/lgd/sih_lgd/registry.py) into the internal
`lgd_directory` catalog-record shape. They are dependency-free (no httpx, no
pydantic) so they can be unit-tested anywhere and so the honesty-critical
invariants are provable.

KEY INVARIANTS (verified spec lgd_verified.md / README.md):
  1. "Do not assume LGD directory tables are themselves polygon datasets. Boundary
     geometry must be sourced from an authoritative GIS boundary product and
     versioned separately ... joined using LGD codes." So a catalog record carries
     NO geometry and NO coordinate — it describes a directory DATASET, not a
     boundary polygon and not a point observation.
  2. "Use LGD codes as stable join keys. Names are display fields only ... Never
     use village/ward names as primary keys because names can repeat or change."
     So the natural key uses the registry dataset_key + the verified directory URL,
     never a name.
  3. A catalog record ALWAYS has stage='CATALOG_ONLY' and carries no measured
     value. The vendored adapter fetches only the directory download page and
     "does not guess file names or fabricate geometry URLs"; it implements no row
     parser. Real LGD unit rows (codes+hierarchy) would only enter a separate
     administrative table after a gated, verified directory-file parse (future
     work). The ML feature pipeline never reads this catalog.

Nothing is fabricated: dataset_key, admin_level (level) and purpose come verbatim
from the verified registry; directory_url is the verified LGD download-portal URL.
Unlike CWC (distinct path per dataset), the LGD registry exposes every directory
through the SAME download portal, so — like GSI — dataset_key is what keeps rows
distinct, and the directory URL is shared across rows.
"""
from __future__ import annotations

import json
from typing import Any

CATALOG_ONLY = "CATALOG_ONLY"
PARSED = "PARSED"

# The verified official LGD download portal (sih_lgd/config.py LgdConfig default).
# Cataloging needs no credentials; this is the single documented entry point the
# verified adapter fetches — we never guess per-dataset file names or geometry URLs.
DEFAULT_LGD_DOWNLOAD_URL = "https://lgdirectory.gov.in/demo/downloadDirectory.do"


def registry_entry_to_catalog_record(
    dataset_key: str,
    entry: dict[str, Any],
    *,
    directory_url: str = DEFAULT_LGD_DOWNLOAD_URL,
    retrieved_at: str | None = None,
) -> dict:
    """Map one LGD_DATASETS registry entry to exactly one catalog record.

    admin_level (from the registry `level`) and purpose are copied VERBATIM from
    the verified registry; directory_url is the verified LGD download-portal URL
    (never a guessed file name or geometry URL). Every record has
    stage='CATALOG_ONLY' and carries no geometry and no numeric value by design."""
    admin_level = entry.get("level")
    purpose = entry.get("purpose")

    raw_ref = json.dumps({
        "dataset_key": dataset_key,
        "level": admin_level,
        "purpose": purpose,
        "directory_url": directory_url,
    }, sort_keys=True, default=str)

    return {
        "source": "lgd",
        "dataset_key": dataset_key,
        # Verified administrative level (STATE_UT|DISTRICT|...|WARD). Codes, not
        # names, are the stable join keys — this catalog does not carry names.
        "admin_level": admin_level,
        "purpose": purpose,
        # Verified LGD download-portal URL (the single documented entry point).
        "directory_url": directory_url,
        # INVARIANT: a catalog entry is a directory dataset, never a boundary
        # polygon or a measurement. No geometry / no numeric value is produced here.
        "stage": CATALOG_ONLY,
        "raw_reference": raw_ref,
        "retrieved_at": retrieved_at,
    }


def registry_to_catalog_records(
    registry: dict[str, dict[str, Any]],
    *,
    directory_url: str = DEFAULT_LGD_DOWNLOAD_URL,
    retrieved_at: str | None = None,
) -> list[dict]:
    """Map the whole LGD_DATASETS registry to a flat list of catalog records
    (one per registry entry)."""
    return [registry_entry_to_catalog_record(dataset_key, entry,
                                             directory_url=directory_url,
                                             retrieved_at=retrieved_at)
            for dataset_key, entry in (registry or {}).items()]
