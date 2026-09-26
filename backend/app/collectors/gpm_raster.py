"""
GPM IMERG scientific HDF5 download, signature verification, parsing, and spatial sampling.

This module implements the production vertical slice:
1. Downloads the exact CMR-returned GET DATA URL with Bearer authentication.
2. Validates the HDF5 8-byte signature (\\x89HDF\\r\\n\\x1a\\n).
3. Parses Grid/precipitation with strict guards:
   - Rejects missing or malformed datasets
   - Validates units attribute (expected mm/hr)
   - Rejects _FillValue (-9999.9) and non-finite values (missing != zero)
4. Coordinates & Spatial Sampling:
   - Reads actual Grid/lat and Grid/lon coordinate arrays from the HDF5 file
   - Maps coordinates to target points using nearest-neighbor lookup
   - Converts half-hourly mm/hr precipitation rate into 30-minute accumulation:
     rainfall_30m = rate * 0.5 mm
"""
from __future__ import annotations

import os
import tempfile
from dataclasses import dataclass, field
from typing import Any

_HDF5_SIGNATURE = b"\x89HDF\r\n\x1a\n"

_SCIENTIFIC_EXTENSIONS = (
    ".hdf5", ".h5", ".he5", ".nc", ".nc4", ".tif", ".tiff", ".geotiff"
)
_BROWSE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp", ".svg")


def h5py_available() -> bool:
    """True if h5py and numpy are importable."""
    try:
        import h5py  # noqa: F401
        import numpy  # noqa: F401
        return True
    except Exception:  # noqa: BLE001
        return False


def rasterio_available() -> bool:
    """Compatibility alias for existing collector checks."""
    return h5py_available()


def is_scientific_format(url: str | None, media_type: str | None = None) -> bool:
    """Reject browse imagery (PNG/JPEG), accept scientific formats (HDF5/NetCDF/GeoTIFF)."""
    if not url:
        return False
    path = url.split("?", 1)[0].split("#", 1)[0].lower()
    mt = (media_type or "").split(";")[0].strip().lower()

    if path.endswith(_BROWSE_EXTENSIONS) or mt.startswith("image/png") or mt.startswith("image/jpeg"):
        return False
    if path.endswith(_SCIENTIFIC_EXTENSIONS):
        return True
    if any(k in mt for k in ("hdf", "netcdf", "tiff", "octet-stream")):
        return True
    # Default for CMR GET DATA URLs from GES DISC (often contain 3IMERG...HDF5)
    if "3imerg" in path or "gesdisc" in path:
        return True
    return False


is_scientific_raster = is_scientific_format


def validate_hdf5_signature(path_or_bytes: str | bytes) -> bool:
    """Verify exact 8-byte HDF5 header: \\x89HDF\\r\\n\\x1a\\n."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes[:8]) == _HDF5_SIGNATURE
    if not os.path.exists(path_or_bytes):
        return False
    with open(path_or_bytes, "rb") as fh:
        head = fh.read(8)
    return head == _HDF5_SIGNATURE


def download_granule(url: str, dest_path: str, token: str | None = None,
                     timeout: float = 120.0) -> None:
    """Download an exact CMR-returned GET DATA URL with NASA Earthdata Bearer auth."""
    import httpx

    headers = {"Authorization": f"Bearer {token}"} if token else {}
    with httpx.stream("GET", url, headers=headers, timeout=timeout,
                      follow_redirects=True) as resp:
        if resp.status_code != 200:
            err_body = b""
            for chunk in resp.iter_bytes():
                err_body += chunk
                if len(err_body) > 500:
                    break
            raise RuntimeError(
                f"Download failed with HTTP {resp.status_code}: "
                f"{err_body.decode('utf-8', 'replace')[:200]}"
            )
        with open(dest_path, "wb") as fh:
            for chunk in resp.iter_bytes():
                fh.write(chunk)


@dataclass
class RasterStageResult:
    """Per-stage outcome so callers can log exactly which stage succeeded."""
    download_ok: bool = False
    signature_ok: bool = False
    parse_ok: bool = False
    sampled: int = 0
    skipped_reason: str | None = None
    samples: list[dict] = field(default_factory=list)
    error: str | None = None
    provenance: dict = field(default_factory=dict)


def sample_hdf5_at_points(
    hdf5_path: str,
    points: list[dict],
    dataset_name: str = "Grid/precipitation",
    max_dist_deg: float = 0.25,
) -> list[dict]:
    """Open HDF5, inspect Grid/precipitation, validate units, reject fill values,
    and sample at points using Grid/lat and Grid/lon arrays.
    """
    import h5py
    import numpy as np

    if not validate_hdf5_signature(hdf5_path):
        raise ValueError("File is not a valid HDF5 payload (signature mismatch)")

    with h5py.File(hdf5_path, "r") as f:
        # 1. Dataset selection
        if dataset_name not in f:
            # Check lowercase or alternative Grid group
            candidates = [k for k in ("precipitation", "Grid/precipitation", "grid/precipitation") if k in f]
            if not candidates:
                raise KeyError(f"Dataset '{dataset_name}' not found in HDF5 file")
            dataset_name = candidates[0]

        ds = f[dataset_name]

        # 2. Unit validation
        units = ds.attrs.get("units")
        if isinstance(units, (bytes, bytearray)):
            units = units.decode("utf-8", "replace")
        units_str = (units or "").strip()
        if not units_str or units_str.lower() not in ("mm/hr", "mm/h"):
            raise ValueError(
                f"Invalid precipitation units '{units_str}'; expected 'mm/hr'"
            )

        # 3. FillValue
        fill = ds.attrs.get("_FillValue")
        fill_val = float(fill) if fill is not None else -9999.9

        # 4. Actual spatial coordinates from file
        lat_key = next((k for k in ("Grid/lat", "Grid/latitude", "lat", "latitude") if k in f), None)
        lon_key = next((k for k in ("Grid/lon", "Grid/longitude", "lon", "longitude") if k in f), None)
        if not lat_key or not lon_key:
            raise KeyError("Spatial coordinates (Grid/lat, Grid/lon) missing from HDF5 file")

        lats = np.array(f[lat_key]).astype("float64")
        lons = np.array(f[lon_key]).astype("float64")

        arr = np.array(ds[()]).astype("float64")

        # Map dimensions: e.g. arr is (1, 3600, 1800) -> (time, lon, lat)
        if arr.ndim == 3:
            if arr.shape[1] == len(lons) and arr.shape[2] == len(lats):
                axis_lon, axis_lat = 1, 2
            elif arr.shape[1] == len(lats) and arr.shape[2] == len(lons):
                axis_lon, axis_lat = 2, 1
            else:
                raise ValueError(f"Cannot align 3D dataset shape {arr.shape} with coords")
        elif arr.ndim == 2:
            if arr.shape[0] == len(lons) and arr.shape[1] == len(lats):
                axis_lon, axis_lat = 0, 1
            elif arr.shape[0] == len(lats) and arr.shape[1] == len(lons):
                axis_lon, axis_lat = 1, 0
            else:
                raise ValueError(f"Cannot align 2D dataset shape {arr.shape} with coords")
        else:
            raise ValueError(f"Unexpected dataset dimensionality: {arr.ndim}")

        out = []
        for p in points:
            target_lat = float(p["latitude"])
            target_lon = float(p["longitude"])

            lat_idx = int(np.argmin(np.abs(lats - target_lat)))
            lon_idx = int(np.argmin(np.abs(lons - target_lon)))

            grid_lat = float(lats[lat_idx])
            grid_lon = float(lons[lon_idx])

            # Distance check
            dist = max(abs(grid_lat - target_lat), abs(grid_lon - target_lon))
            if dist > max_dist_deg:
                # Point is outside raster bounds or too far
                val = None
                accum_30m = None
            else:
                if arr.ndim == 3:
                    raw_num = arr[0, lon_idx, lat_idx] if axis_lon == 1 else arr[0, lat_idx, lon_idx]
                else:
                    raw_num = arr[lon_idx, lat_idx] if axis_lon == 0 else arr[lat_idx, lon_idx]

                # Check finite and fill value
                is_fill = (fill is not None and abs(raw_num - fill_val) < 1e-2)
                if not np.isfinite(raw_num) or is_fill or raw_num < 0:
                    val = None
                    accum_30m = None
                else:
                    val = float(raw_num)
                    # Convert half-hourly mm/hr rate to 30-minute accumulated rainfall:
                    # accumulation (mm) = rate (mm/hr) * 0.5 hr
                    accum_30m = round(val * 0.5, 4)

            out.append({
                "location_id": p.get("location_id"),
                "location_name": p.get("name") or p.get("location_name") or "target_point",
                "is_test_location": bool(p.get("is_test_location", False)),
                "target_latitude": target_lat,
                "target_longitude": target_lon,
                "latitude": target_lat,
                "longitude": target_lon,
                "grid_latitude": grid_lat,
                "grid_longitude": grid_lon,
                "rate_mm_hr": val,
                "rainfall_30m": accum_30m,
                "value": accum_30m,  # mm accumulation for rainfall_observations
                "units": units_str,
                "variable_path": dataset_name,
            })

        return out


def run_raster_stage(
    download_url: str,
    points: list[dict],
    token: str | None = None,
    workdir: str | None = None,
    media_type: str | None = None,
) -> RasterStageResult:
    """Full production stage:
    download exact CMR URL -> verify HDF5 signature -> parse Grid/precipitation ->
    sample coordinates -> return valid numeric rainfall.
    """
    res = RasterStageResult()
    if not h5py_available():
        res.skipped_reason = "h5py/numpy not installed — HDF5 sampling disabled"
        return res
    if not download_url:
        res.skipped_reason = "no download_url on discovery record"
        return res
    if not is_scientific_format(download_url, media_type):
        res.skipped_reason = "download_url is not a scientific raster/HDF5 format"
        return res

    workdir = workdir or tempfile.gettempdir()
    fd, dest = tempfile.mkstemp(prefix="gpm_", suffix=".HDF5", dir=workdir)
    os.close(fd)
    try:
        try:
            download_granule(download_url, dest, token=token)
            res.download_ok = True
        except Exception as e:  # noqa: BLE001
            res.error = f"download failed: {type(e).__name__}: {e}"
            return res

        # Validate HDF5 signature
        if not validate_hdf5_signature(dest):
            res.error = "signature validation failed: payload is not valid HDF5"
            return res
        res.signature_ok = True

        # Parse & sample
        try:
            samples = sample_hdf5_at_points(dest, points)
            res.samples = samples
            res.parse_ok = True
            res.sampled = sum(1 for s in samples if s.get("value") is not None)
        except Exception as e:  # noqa: BLE001
            res.error = f"HDF5 parse/sample failed: {type(e).__name__}: {e}"
            return res

        return res
    finally:
        try:
            os.unlink(dest)
        except OSError:
            pass
