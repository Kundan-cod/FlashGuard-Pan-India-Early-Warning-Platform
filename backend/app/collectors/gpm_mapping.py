"""
GPM CMR discovery -> internal mapping helpers (pure Python, no heavy deps).

These functions convert a NASA CMR UMM-JSON response item into internal
`gpm_discovery` record shapes. They are deliberately dependency-free so they can
be unit-tested in any environment without network or Track B dependencies.

KEY INVARIANTS:
1. Discovery record ALWAYS has numeric_value=None and stage='DISCOVERY_ONLY'.
2. Extract only CMR RelatedUrls with Type == 'GET DATA' (never construct URLs).
3. Full provenance is stored in raw_reference (concept ID, granule UR, collection,
   version, source URL, temporal range, variable path, units).
"""
from __future__ import annotations

import json
from typing import Any

DISCOVERY_ONLY = "DISCOVERY_ONLY"
RASTER_SAMPLED = "RASTER_SAMPLED"


def _polygon_centroid(coords: list) -> tuple[float | None, float | None]:
    """Average vertices of a GeoJSON Polygon's outer ring. Provenance only."""
    if not coords:
        return None, None
    ring = coords[0]
    if not ring:
        return None, None
    lon = sum(p[0] for p in ring) / len(ring)
    lat = sum(p[1] for p in ring) / len(ring)
    return lat, lon


def extract_downloads(item: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract ONLY verified GET DATA URLs returned by CMR RelatedUrls.
    Never constructs a GES DISC file URL manually.
    """
    downloads = []
    umm = item.get("umm", {}) if isinstance(item, dict) else {}
    meta = item.get("meta", {}) if isinstance(item, dict) else {}
    cid = meta.get("concept-id") or item.get("@id")

    # CMR UMM-JSON RelatedUrls
    for r in umm.get("RelatedUrls", []) or []:
        url = r.get("URL")
        if r.get("Type") == "GET DATA" and url and url.startswith("http"):
            downloads.append({
                "id": cid,
                "url": url,
                "media_type": r.get("MimeType"),
                "type": "GET DATA",
                "description": r.get("Description"),
            })

    # Legacy PMM support for backwards compatibility with earlier fixtures
    if not downloads and "action" in item:
        for action in item.get("action", []):
            if action.get("@type") != "ojo:download":
                continue
            for request in action.get("using", []):
                u = request.get("url")
                if u and u.startswith("http"):
                    downloads.append({
                        "id": request.get("@id") or cid,
                        "url": u,
                        "media_type": request.get("mediaType"),
                        "type": "GET DATA",
                        "display_name": request.get("displayName"),
                    })

    return downloads


def item_to_discovery_records(item: dict[str, Any],
                              retrieved_at: str | None = None) -> list[dict]:
    """Map one CMR granule item to one or more internal discovery records
    (one per GET DATA download URL). numeric_value is ALWAYS None here by design.
    """
    umm = item.get("umm", {}) if isinstance(item, dict) else {}
    meta = item.get("meta", {}) if isinstance(item, dict) else {}
    props = item.get("properties", {}) or {}
    geometry = item.get("geometry", {}) or {}

    concept_id = meta.get("concept-id") or item.get("@id") or "unknown_concept"
    granule_ur = umm.get("GranuleUR") or item.get("@id") or "unknown_granule"
    coll = umm.get("CollectionReference", {})
    short_name = coll.get("ShortName") or item.get("displayName") or "GPM_3IMERGHHL"
    version = coll.get("Version") or "07"
    product = f"{short_name}.{version}" if version else short_name

    temporal = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
    obs_start = (temporal.get("BeginningDateTime") or
                 (props.get("date", {}) or {}).get("@value", ""))
    obs_end = temporal.get("EndingDateTime") or ""

    lat = lon = None
    if geometry.get("type") == "Polygon":
        lat, lon = _polygon_centroid(geometry.get("coordinates", []))

    downloads = extract_downloads(item)

    records = []
    if not downloads:
        raw_ref = json.dumps({
            "concept_id": concept_id,
            "granule_id": granule_ur,
            "collection": short_name,
            "version": version,
            "source_url": None,
            "observation_start": obs_start,
            "observation_end": obs_end,
            "variable_path": "Grid/precipitation",
            "units": "mm/hr",
            "quality_status": "NO_DOWNLOAD_URL",
        }, sort_keys=True)
        return [{
            "source": "gpm",
            "product": product,
            "observed_date": obs_start,
            "latitude": lat,
            "longitude": lon,
            "resolution": "0.1 degree",
            "item_id": concept_id,
            "download_url": None,
            "media_type": None,
            "numeric_value": None,
            "stage": DISCOVERY_ONLY,
            "raw_reference": raw_ref,
            "retrieved_at": retrieved_at,
        }]

    for d in downloads:
        raw_ref = json.dumps({
            "concept_id": concept_id,
            "granule_id": granule_ur,
            "collection": short_name,
            "version": version,
            "source_url": d["url"],
            "observation_start": obs_start,
            "observation_end": obs_end,
            "variable_path": "Grid/precipitation",
            "units": "mm/hr",
            "quality_status": "DISCOVERED",
        }, sort_keys=True)

        records.append({
            "source": "gpm",
            "product": product,
            "observed_date": obs_start,
            "latitude": lat,
            "longitude": lon,
            "resolution": "0.1 degree",
            "item_id": concept_id,
            "download_url": d["url"],
            "media_type": d.get("media_type") or "application/x-hdf5",
            "numeric_value": None,
            "stage": DISCOVERY_ONLY,
            "raw_reference": raw_ref,
            "retrieved_at": retrieved_at,
        })

    return records


def payload_to_discovery_records(payload: dict[str, Any],
                                 retrieved_at: str | None = None) -> list[dict]:
    """Map a full CMR response payload ({'items': [...]}) to discovery records."""
    out: list[dict] = []
    for item in payload.get("items", []) or []:
        out.extend(item_to_discovery_records(item, retrieved_at=retrieved_at))
    return out
