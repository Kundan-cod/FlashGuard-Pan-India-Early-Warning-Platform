"""
GPM raw-response diagnostic (READ-ONLY, no storage, no parsing-as-rainfall).

Point 13 of verify_gpm_runtime showed the GPM discovery request reached NASA but
the vendored collector failed with "Expecting value: line 1 column 1 (char 0)" —
a JSON-parse failure AFTER raise_for_status() passed. That means the server
returned a non-JSON body (very likely OpenSearch XML/Atom, or an HTML notice).

This tool hits the SAME verified endpoint (app.data_layer.sources.gpm.config
.Settings.gpm_api_base_url — never an invented URL) with the SAME documented
params and prints EXACTLY what comes back so we can see it instead of guessing:
  * final URL (after redirects) and HTTP status
  * Content-Type
  * body length + the first ~800 bytes, verbatim
  * whether the body parses as JSON, and if so whether it has 'items'

It NEVER writes to any table and NEVER treats the body as rainfall. The token is
read from NASA_EARTHDATA_TOKEN and sent as a Bearer header if present; its value
is never printed (only whether it was attached).

Run inside the backend container:
    docker exec -i flashguard_backend python -m app.services.gpm_probe_raw
Optional: GPM_PROBE_PRODUCT (default precip_1d), GPM_PROBE_LIMIT (default 5).
"""
from __future__ import annotations

import os


def main() -> None:
    import httpx
    from app.data_layer.sources.gpm.config import Settings

    settings = Settings()
    base_url = settings.gpm_api_base_url  # verified endpoint, from config
    product = os.environ.get("GPM_PROBE_PRODUCT", "precip_1d")
    try:
        limit = int(os.environ.get("GPM_PROBE_LIMIT", "5"))
    except ValueError:
        limit = 5

    # Only the documented params (q, limit). No invented fields.
    params = {"q": product, "limit": limit}

    token = (os.environ.get("NASA_EARTHDATA_TOKEN") or "").strip()
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print("[gpm_probe_raw] endpoint :", base_url)
    print("[gpm_probe_raw] params   :", params)
    print("[gpm_probe_raw] bearer   :", "attached" if token else "none")

    # Try a couple of Accept headers so we can see whether the server has a JSON
    # representation at all, or only XML/Atom. Purely observational.
    accepts = [None, "application/json", "application/geo+json, application/json"]
    for accept in accepts:
        h = dict(headers)
        if accept:
            h["Accept"] = accept
        label = accept or "(no Accept header)"
        print("\n" + "=" * 70)
        print(f"[gpm_probe_raw] REQUEST Accept: {label}")
        try:
            with httpx.Client(timeout=settings.timeout_seconds,
                              follow_redirects=True) as client:
                resp = client.get(base_url, params=params, headers=h)
        except Exception as e:  # noqa: BLE001 - report, never crash
            print(f"[gpm_probe_raw]   TRANSPORT ERROR: {type(e).__name__}: {e}")
            continue

        ctype = resp.headers.get("content-type", "(none)")
        body = resp.text or ""
        print(f"[gpm_probe_raw]   final URL   : {resp.url}")
        print(f"[gpm_probe_raw]   HTTP status : {resp.status_code}")
        print(f"[gpm_probe_raw]   Content-Type: {ctype}")
        print(f"[gpm_probe_raw]   body length : {len(body)} chars")
        snippet = body[:800].replace("\r", "")
        print("[gpm_probe_raw]   first 800 chars ->")
        print("-" * 70)
        print(snippet)
        print("-" * 70)

        # Does it parse as JSON? (Observation only — nothing stored.)
        try:
            import json
            data = json.loads(body)
            kind = type(data).__name__
            has_items = isinstance(data, dict) and "items" in data
            n_items = len(data["items"]) if has_items and isinstance(
                data.get("items"), list) else "n/a"
            print(f"[gpm_probe_raw]   JSON parse  : OK ({kind}), "
                  f"has 'items'={has_items}, item count={n_items}")
        except Exception as e:  # noqa: BLE001
            print(f"[gpm_probe_raw]   JSON parse  : FAILED ({type(e).__name__}: {e})")
            low = body[:200].lstrip().lower()
            if low.startswith("<?xml") or low.startswith("<feed") or "<opensearch" in low:
                print("[gpm_probe_raw]   -> body looks like XML/Atom (OpenSearch default)")
            elif low.startswith("<!doctype html") or low.startswith("<html"):
                print("[gpm_probe_raw]   -> body looks like an HTML page (portal/notice)")

    # ------------------------------------------------------------------
    # OpenSearch autodiscovery: the HTML page NASA served us should itself
    # advertise the REAL query API via an OpenSearch Description Document
    # (OSDD), per the OpenSearch spec. Reading NASA's own published
    # self-description is NOT inventing an endpoint — it is the documented way
    # to discover the correct URL template. We fetch the OSDD (if advertised)
    # and print its <Url template="..."> entries verbatim. Nothing is stored.
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("[gpm_probe_raw] OpenSearch autodiscovery from the returned HTML")
    try:
        import re
        from urllib.parse import urljoin

        with httpx.Client(timeout=settings.timeout_seconds,
                          follow_redirects=True) as client:
            page = client.get(base_url, params={"q": product, "limit": limit},
                              headers=headers).text

        # 1) <link rel="search" type="application/opensearchdescription+xml" href="...">
        osdd_hrefs = re.findall(
            r'<link[^>]+opensearchdescription\+xml[^>]*>', page, re.I)
        hrefs = []
        for tag in osdd_hrefs:
            m = re.search(r'href=["\']([^"\']+)["\']', tag, re.I)
            if m:
                hrefs.append(m.group(1))
        # 2) any explicit opensearchdescription*.xml reference in the HTML/JS
        hrefs += re.findall(r'["\']([^"\']*opensearchdescription[^"\']*\.xml)["\']',
                            page, re.I)
        hrefs = list(dict.fromkeys(hrefs))  # dedupe, keep order

        if not hrefs:
            print("[gpm_probe_raw]   no OSDD <link> advertised in the page.")
            # Surface any inline hints (JSON API paths referenced by the viewer JS)
            hints = sorted(set(re.findall(
                r'["\'](/[^"\']*(?:search|opensearch|api)[^"\']*)["\']', page, re.I)))
            if hints:
                print("[gpm_probe_raw]   inline path hints found in the page JS:")
                for h in hints[:20]:
                    print(f"[gpm_probe_raw]     {h}")
            else:
                print("[gpm_probe_raw]   no inline search/api path hints either.")
        else:
            for href in hrefs:
                osdd_url = urljoin(str(base_url), href)
                print(f"[gpm_probe_raw]   OSDD advertised at: {osdd_url}")
                try:
                    with httpx.Client(timeout=settings.timeout_seconds,
                                      follow_redirects=True) as client:
                        osdd = client.get(osdd_url, headers=headers)
                    print(f"[gpm_probe_raw]     OSDD HTTP {osdd.status_code}, "
                          f"Content-Type {osdd.headers.get('content-type','?')}")
                    templates = re.findall(r'<Url\b[^>]*>', osdd.text, re.I)
                    if templates:
                        print("[gpm_probe_raw]     <Url> templates (verbatim):")
                        for t in templates:
                            print(f"[gpm_probe_raw]       {t}")
                    else:
                        print("[gpm_probe_raw]     (no <Url> templates; first 400 chars:)")
                        print(osdd.text[:400])
                except Exception as e:  # noqa: BLE001
                    print(f"[gpm_probe_raw]     OSDD fetch error: "
                          f"{type(e).__name__}: {e}")
    except Exception as e:  # noqa: BLE001
        print(f"[gpm_probe_raw]   autodiscovery error: {type(e).__name__}: {e}")

    print("\n[gpm_probe_raw] done. Nothing was stored; no body was treated as rainfall.")


if __name__ == "__main__":
    main()
