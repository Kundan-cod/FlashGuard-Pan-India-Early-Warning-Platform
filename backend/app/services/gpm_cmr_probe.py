"""
GPM IMERG CMR probe (READ-ONLY diagnostic; stores nothing, parses no rainfall).

Follows the ChatGPT-verified migration target (2026-09-06): the retired PMM
`/opensearch` endpoint is replaced by NASA's documented CMR granule search. This
probe hits ONLY NASA's documented CMR API:

    https://cmr.earthdata.nasa.gov/search/granules.umm_json

with the verified query (provider=GES_DISC, short_name, version=07, temporal,
point, page_size), authenticates with the existing NASA_EARTHDATA_TOKEN as a
Bearer header, and prints exactly the 7 things asked for so we SEE the contract
before wiring any collector:

    1. HTTP status
    2. collection matched (short_name / version / entry title)
    3. granule ID (producer granule id / concept id)
    4. temporal coverage (Beginning / Ending DateTime)
    5. RelatedURLs (Type + URL)
    6. selected GETDATA URL (the first Type == "GET DATA")
    7. media / type (declared MimeType if any, else URL extension)

It NEVER downloads the product, NEVER opens a raster, NEVER writes a row, and
NEVER treats any metadata as a rainfall value. The token value is never printed.

Run inside the backend container:
    docker exec -i flashguard_backend python -m app.services.gpm_cmr_probe

Env overrides (all optional):
    GPM_CMR_BASE_URL   default https://cmr.earthdata.nasa.gov/search
    GPM_CMR_SHORT_NAME default GPM_3IMERGHHL   (Late half-hourly — verified primary)
    GPM_CMR_VERSION    default 07
    GPM_CMR_PROVIDER   default GES_DISC
    GPM_CMR_POINT      default "78.06,30.06"  (lon,lat — the demo Uttarakhand cell)
    GPM_CMR_DAYS       default 14  (temporal window = now-DAYS .. now; latency-aware)
    GPM_CMR_PAGE_SIZE  default 5
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _media_of(url: str, declared: str | None) -> str:
    if declared:
        return declared
    low = url.split("?", 1)[0].lower()
    for ext in (".he5", ".h5", ".hdf5", ".hdf", ".nc4", ".nc",
                ".tif", ".tiff", ".xml", ".png", ".jpg", ".jpeg"):
        if low.endswith(ext):
            return f"(by extension {ext})"
    return "(unknown)"


def main() -> None:
    import httpx

    base = os.environ.get("GPM_CMR_BASE_URL",
                          "https://cmr.earthdata.nasa.gov/search").rstrip("/")
    short_name = os.environ.get("GPM_CMR_SHORT_NAME", "GPM_3IMERGHHL")
    version = os.environ.get("GPM_CMR_VERSION", "07")
    provider = os.environ.get("GPM_CMR_PROVIDER", "GES_DISC")
    point = os.environ.get("GPM_CMR_POINT", "78.06,30.06")  # lon,lat
    try:
        days = int(os.environ.get("GPM_CMR_DAYS", "14"))
    except ValueError:
        days = 14
    try:
        page_size = int(os.environ.get("GPM_CMR_PAGE_SIZE", "5"))
    except ValueError:
        page_size = 5
    try:
        timeout = float(os.environ.get("GPM_TIMEOUT_SECONDS", "30"))
    except ValueError:
        timeout = 30.0

    now = datetime.now(timezone.utc)
    start = now - timedelta(days=days)
    temporal = f"{_iso_z(start)},{_iso_z(now)}"

    params = {
        "provider": provider,
        "short_name": short_name,
        "version": version,
        "temporal[]": temporal,
        "point": point,
        "page_size": page_size,
        "sort_key[]": "-start_date",
        "downloadable": "true",
    }

    token = (os.environ.get("NASA_EARTHDATA_TOKEN") or "").strip()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    url = f"{base}/granules.umm_json"
    print("[gpm_cmr_probe] endpoint :", url)
    print("[gpm_cmr_probe] provider :", provider)
    print("[gpm_cmr_probe] collection:", f"{short_name} v{version}")
    print("[gpm_cmr_probe] temporal :", temporal)
    print("[gpm_cmr_probe] point    :", point, "(lon,lat)")
    print("[gpm_cmr_probe] page_size:", page_size)
    print("[gpm_cmr_probe] bearer   :", "attached" if token else "none")

    try:
        with httpx.Client(timeout=timeout, follow_redirects=True) as client:
            resp = client.get(url, params=params, headers=headers)
    except Exception as e:  # noqa: BLE001
        print(f"[gpm_cmr_probe] TRANSPORT ERROR: {type(e).__name__}: {e}")
        return

    # (1) HTTP status
    print("\n[gpm_cmr_probe] (1) HTTP status:", resp.status_code)
    print("[gpm_cmr_probe]     final URL  :", resp.url)
    print("[gpm_cmr_probe]     Content-Type:",
          resp.headers.get("content-type", "?"))
    hits = resp.headers.get("cmr-hits")
    if hits is not None:
        print("[gpm_cmr_probe]     CMR-Hits    :", hits)

    if resp.status_code != 200:
        print("[gpm_cmr_probe]     non-200 body (first 500 chars):")
        print("-" * 70)
        print((resp.text or "")[:500])
        print("-" * 70)
        return

    try:
        data = resp.json()
    except Exception as e:  # noqa: BLE001
        print(f"[gpm_cmr_probe]     JSON parse FAILED: {type(e).__name__}: {e}")
        print((resp.text or "")[:500])
        return

    items = data.get("items", []) if isinstance(data, dict) else []
    print(f"[gpm_cmr_probe]     granules returned: {len(items)}")
    if not items:
        print("[gpm_cmr_probe]     No granules in this window — try widening "
              "GPM_CMR_DAYS or check the short_name/version.")
        return

    for idx, it in enumerate(items):
        umm = it.get("umm", {}) if isinstance(it, dict) else {}
        meta = it.get("meta", {}) if isinstance(it, dict) else {}
        print("\n" + "=" * 70)
        print(f"[gpm_cmr_probe] GRANULE {idx + 1} of {len(items)}")

        # (2) collection matched
        coll = umm.get("CollectionReference", {})
        print("[gpm_cmr_probe]  (2) collection: "
              f"short_name={coll.get('ShortName')} version={coll.get('Version')} "
              f"entry_title={coll.get('EntryTitle')}")

        # (3) granule id
        print("[gpm_cmr_probe]  (3) granule id: "
              f"producer={umm.get('GranuleUR')} concept-id={meta.get('concept-id')}")

        # (4) temporal coverage
        trange = (umm.get("TemporalExtent", {})
                  .get("RangeDateTime", {}))
        print("[gpm_cmr_probe]  (4) temporal  : "
              f"{trange.get('BeginningDateTime')} .. {trange.get('EndingDateTime')}")

        # (5) RelatedUrls (verbatim Type + URL)
        rel = umm.get("RelatedUrls", []) or []
        print(f"[gpm_cmr_probe]  (5) RelatedUrls ({len(rel)}):")
        getdata = []
        for r in rel:
            rtype = r.get("Type")
            rurl = r.get("URL")
            rmime = r.get("MimeType")
            print(f"[gpm_cmr_probe]        - Type={rtype} MimeType={rmime}")
            print(f"[gpm_cmr_probe]          URL={rurl}")
            if rtype == "GET DATA" and rurl:
                getdata.append((rurl, rmime))

        # (6) selected GETDATA url
        if getdata:
            sel_url, sel_mime = getdata[0]
            print(f"[gpm_cmr_probe]  (6) selected GETDATA: {sel_url}")
            # (7) media/type
            print(f"[gpm_cmr_probe]  (7) media/type      : "
                  f"{_media_of(sel_url, sel_mime)}")
        else:
            print("[gpm_cmr_probe]  (6) selected GETDATA: NONE "
                  "(no Type=='GET DATA' RelatedUrl on this granule)")
            print("[gpm_cmr_probe]  (7) media/type      : n/a")

    print("\n[gpm_cmr_probe] done. Nothing downloaded, nothing stored, "
          "no metadata treated as rainfall.")


if __name__ == "__main__":
    main()
