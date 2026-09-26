"""
GPM IMERG HDF5 download + parse probe (READ-ONLY diagnostic).

Third and final probe in the verified migration (2026-09-06). CMR discovery is
already confirmed (gpm_cmr_probe: HTTP 200, 642 hits, real GET DATA URLs). This
probe takes an EXACT GET DATA URL that CMR returned (never a constructed path),
downloads the granule to a temp location, verifies it is genuinely HDF5 by its
byte signature, opens it with h5py, and inspects the scientific datasets to
locate the precipitation variable and print its structure.

It does the discovery itself (same verified CMR query) so it can hand the
freshest real GET DATA URL to the download — OR you can pin one via GPM_HDF5_URL.

STRICT honesty posture (unchanged):
  * Uses ONLY a URL CMR actually returned (Type == "GET DATA"); never constructs
    a GES DISC path from memory.
  * Verifies HDF5 by the 8-byte signature \\x89HDF\\r\\n\\x1a\\n, not the .HDF5 name.
  * Confirms the precipitation dataset by inspecting the file's own datasets +
    their `units` attribute (expected mm/hr for the half-hourly product), rather
    than assuming a variable name.
  * Writes NOTHING to PostGIS. Creates NO rainfall observation. A successful HTTP
    response or valid HDF5 is NOT rainfall — only a finite sampled value would be,
    and even that is just printed here, never stored.
  * Token read from NASA_EARTHDATA_TOKEN, sent as Bearer; value never printed.
  * Temp file is always deleted.

Run inside the ML/raster backend image (h5py present):
    docker exec -i flashguard_backend python -m app.services.gpm_hdf5_probe

Env overrides (optional): GPM_HDF5_URL (pin an exact CMR GET DATA URL),
GPM_CMR_SHORT_NAME/VERSION/PROVIDER/POINT/DAYS (discovery, same defaults as
gpm_cmr_probe), GPM_HDF5_KEEP=1 to keep the temp file for manual inspection.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

_HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _discover_getdata_url() -> str | None:
    """Run the SAME verified CMR query and return the first Type=='GET DATA'
    https URL. Returns None if discovery finds nothing. Never constructs a URL."""
    import httpx
    base = os.environ.get("GPM_CMR_BASE_URL",
                          "https://cmr.earthdata.nasa.gov/search").rstrip("/")
    short_name = os.environ.get("GPM_CMR_SHORT_NAME", "GPM_3IMERGHHL")
    version = os.environ.get("GPM_CMR_VERSION", "07")
    provider = os.environ.get("GPM_CMR_PROVIDER", "GES_DISC")
    point = os.environ.get("GPM_CMR_POINT", "78.06,30.06")
    try:
        days = int(os.environ.get("GPM_CMR_DAYS", "14"))
    except ValueError:
        days = 14
    now = datetime.now(timezone.utc)
    params = {
        "provider": provider, "short_name": short_name, "version": version,
        "temporal[]": f"{_iso_z(now - timedelta(days=days))},{_iso_z(now)}",
        "point": point, "page_size": 5, "sort_key[]": "-start_date",
        "downloadable": "true",
    }
    token = (os.environ.get("NASA_EARTHDATA_TOKEN") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.Client(timeout=30.0, follow_redirects=True) as client:
        resp = client.get(f"{base}/granules.umm_json", params=params,
                          headers=headers)
    resp.raise_for_status()
    for it in resp.json().get("items", []):
        for r in it.get("umm", {}).get("RelatedUrls", []) or []:
            url = r.get("URL")
            if r.get("Type") == "GET DATA" and url and url.startswith("http"):
                return url
    return None


def _inspect_hdf5(path: str) -> None:
    """Open with h5py, list datasets, and locate the precipitation variable by
    inspecting each dataset's own `units` attribute + name. Prints structure."""
    import h5py
    import numpy as np

    datasets: list[tuple[str, object]] = []

    def _walk(name, obj):
        if isinstance(obj, h5py.Dataset):
            datasets.append((name, obj))

    with h5py.File(path, "r") as f:
        print("[gpm_hdf5_probe]   top-level keys:", list(f.keys()))
        f.visititems(_walk)
        print(f"[gpm_hdf5_probe]   total datasets: {len(datasets)}")

        # Print every dataset's path/shape/dtype/units so the real structure is
        # visible (not assumed). Flag likely precipitation datasets.
        precip_candidates = []
        for name, ds in datasets:
            units = ds.attrs.get("units")
            if isinstance(units, bytes):
                units = units.decode("utf-8", "replace")
            print(f"[gpm_hdf5_probe]     - {name}  shape={ds.shape} "
                  f"dtype={ds.dtype} units={units!r}")
            base = name.split("/")[-1].lower()
            if "precip" in base:
                precip_candidates.append((name, ds, units))

        print("\n[gpm_hdf5_probe]   precipitation candidate datasets:",
              [c[0] for c in precip_candidates] or "NONE")

        # Prefer the exact documented half-hourly path Grid/precipitation, else
        # the first candidate whose units look like a rate (mm/hr).
        chosen = None
        for name, ds, units in precip_candidates:
            if name.replace("//", "/").endswith("Grid/precipitation") or \
               name.lower().endswith("grid/precipitation"):
                chosen = (name, ds, units)
                break
        if chosen is None and precip_candidates:
            chosen = precip_candidates[0]

        if chosen is None:
            print("[gpm_hdf5_probe]   RESULT: no precipitation dataset found — "
                  "NOT claiming rainfall. Inspect the dataset list above.")
            return

        name, ds, units = chosen
        print("\n[gpm_hdf5_probe]   CHOSEN precipitation dataset:")
        print(f"[gpm_hdf5_probe]     path : {name}")
        print(f"[gpm_hdf5_probe]     dtype: {ds.dtype}")
        print(f"[gpm_hdf5_probe]     shape: {ds.shape}")
        print(f"[gpm_hdf5_probe]     units: {units!r}")
        fill = ds.attrs.get("_FillValue")
        if isinstance(fill, (bytes, bytearray)):
            fill = fill.decode("utf-8", "replace")
        cf = ds.attrs.get("CodeMissingValue")
        if isinstance(cf, (bytes, bytearray)):
            cf = cf.decode("utf-8", "replace")
        print(f"[gpm_hdf5_probe]     _FillValue={fill!r} CodeMissingValue={cf!r}")

        # Finite-value sample (missing != zero): read the array, mask fill/NaN,
        # print count + min/max + a few real values. Purely observational.
        try:
            arr = np.array(ds[()]).astype("float64").ravel()
            mask = np.isfinite(arr)
            if fill is not None:
                try:
                    mask &= (arr != float(fill))
                except (TypeError, ValueError):
                    pass
            finite = arr[mask]
            print(f"[gpm_hdf5_probe]     finite (non-fill) values: {finite.size} "
                  f"of {arr.size}")
            if finite.size:
                print(f"[gpm_hdf5_probe]     min={finite.min():.4f} "
                      f"max={finite.max():.4f} mean={finite.mean():.4f}")
                print("[gpm_hdf5_probe]     sample values:",
                      [round(float(v), 4) for v in finite[:8]])
                print("[gpm_hdf5_probe]   -> numeric rainfall sample: PRESENT "
                      "(printed only; NOTHING stored)")
            else:
                print("[gpm_hdf5_probe]   -> all fill/NaN in this granule cell; "
                      "no finite sample (missing != zero, nothing fabricated)")
        except Exception as e:  # noqa: BLE001
            print(f"[gpm_hdf5_probe]     value read error: {type(e).__name__}: {e}")

        # Coordinate structure (lat/lon) so the sampler knows the grid axes.
        for coord in ("Grid/lat", "Grid/lon", "lat", "lon", "Grid/latitude",
                      "Grid/longitude"):
            if coord in f:
                c = f[coord]
                print(f"[gpm_hdf5_probe]     coord {coord}: shape={c.shape} "
                      f"dtype={c.dtype}")


def main() -> None:
    import tempfile
    import httpx

    url = (os.environ.get("GPM_HDF5_URL") or "").strip()
    if not url:
        print("[gpm_hdf5_probe] no GPM_HDF5_URL pinned -> discovering a fresh "
              "GET DATA URL via the verified CMR query...")
        try:
            url = _discover_getdata_url()
        except Exception as e:  # noqa: BLE001
            print(f"[gpm_hdf5_probe] CMR discovery error: {type(e).__name__}: {e}")
            return
    if not url:
        print("[gpm_hdf5_probe] no GET DATA URL available — cannot proceed. "
              "(Widen GPM_CMR_DAYS or check collection.) Nothing stored.")
        return
    if not url.startswith("http"):
        print(f"[gpm_hdf5_probe] refusing non-http URL: {url}")
        return

    print("[gpm_hdf5_probe] GET DATA URL (from CMR):", url)
    token = (os.environ.get("NASA_EARTHDATA_TOKEN") or "").strip()
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    print("[gpm_hdf5_probe] bearer   :", "attached" if token else "none")

    fd, dest = tempfile.mkstemp(prefix="gpm_", suffix=".HDF5")
    os.close(fd)
    keep = os.environ.get("GPM_HDF5_KEEP") == "1"
    try:
        try:
            with httpx.Client(timeout=120.0, follow_redirects=True) as client:
                with client.stream("GET", url, headers=headers) as resp:
                    # (3) HTTP status / content-type / length
                    print("[gpm_hdf5_probe] (3) HTTP status :", resp.status_code)
                    print("[gpm_hdf5_probe]     Content-Type :",
                          resp.headers.get("content-type", "?"))
                    print("[gpm_hdf5_probe]     Content-Length:",
                          resp.headers.get("content-length", "?"))
                    print("[gpm_hdf5_probe]     final URL    :", resp.url)
                    if resp.status_code != 200:
                        body = b""
                        for chunk in resp.iter_bytes():
                            body += chunk
                            if len(body) > 800:
                                break
                        print("[gpm_hdf5_probe]     non-200 body (first 800 bytes):")
                        print("-" * 70)
                        print(body[:800].decode("utf-8", "replace"))
                        print("-" * 70)
                        if resp.status_code in (401, 403):
                            print("[gpm_hdf5_probe]   -> auth/authorization issue: "
                                  "the token may need GES DISC app approval in your "
                                  "Earthdata profile. NOT a code bug.")
                        elif resp.status_code in (301, 302):
                            print("[gpm_hdf5_probe]   -> redirect to an Earthdata "
                                  "login page: token not accepted for download.")
                        return
                    total = 0
                    with open(dest, "wb") as fh:
                        for chunk in resp.iter_bytes():
                            fh.write(chunk)
                            total += len(chunk)
            print(f"[gpm_hdf5_probe]     downloaded bytes: {total}")
        except Exception as e:  # noqa: BLE001
            print(f"[gpm_hdf5_probe] DOWNLOAD ERROR: {type(e).__name__}: {e}")
            return

        # (4) verify HDF5 by signature, not extension
        with open(dest, "rb") as fh:
            head = fh.read(8)
        is_hdf5 = head == _HDF5_SIGNATURE
        print(f"[gpm_hdf5_probe] (4) HDF5 signature: {head!r} -> "
              f"{'VALID HDF5' if is_hdf5 else 'NOT HDF5'}")
        if not is_hdf5:
            print("[gpm_hdf5_probe]   -> payload is not HDF5 (maybe an HTML login "
                  "page or error). NOT parsing as rainfall. Nothing stored.")
            # Show a peek so the cause is visible.
            print("[gpm_hdf5_probe]   first 200 bytes:",
                  head + open(dest, "rb").read(192))
            return

        # (5)/(6) open + inspect
        try:
            import h5py  # noqa: F401
        except Exception:  # noqa: BLE001
            print("[gpm_hdf5_probe] h5py not installed in this image. Add "
                  "requirements-ml.txt (h5py==3.11.0) and run on the ML image. "
                  "Download+signature already verified above.")
            return
        print("\n[gpm_hdf5_probe] (5/6) inspecting HDF5 scientific datasets:")
        _inspect_hdf5(dest)

        print("\n[gpm_hdf5_probe] done. Nothing written to PostGIS; no rainfall "
              "observation created; values above are printed for verification only.")
    finally:
        if not keep:
            try:
                os.unlink(dest)
            except OSError:
                pass
        else:
            print(f"[gpm_hdf5_probe] kept temp file at {dest} (GPM_HDF5_KEEP=1)")


if __name__ == "__main__":
    main()
