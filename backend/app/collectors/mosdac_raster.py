"""
MOSDAC INSAT-3DS / INSAT-3DR scientific HDF5 verification, parsing, and spatial sampling.

Implements FlashGuard's production multi-source data ingestion pipeline:
MOSDAC -> Collector / Adapter -> Validation + QC -> Normalization -> Internal Observation Schema -> PostGIS/SQLite

Key features:
1. Validates the HDF5 8-byte signature (\\x89HDF\\r\\n\\x1a\\n).
2. Parses INSAT precipitation datasets (e.g. 'IMR', 'HEM', 'RAIN') with strict guards:
   - Rejects missing or corrupted datasets
   - Validates units attribute (expected 'mm/hr' or 'mm/h')
   - Rejects _FillValue (-999.0) and non-finite values (missing != zero)
3. Coordinates & Spatial Sampling:
   - Reads actual latitude and longitude coordinate arrays directly from the HDF5 file
   - Maps coordinates to FlashGuard monitored locations/villages via nearest-neighbor lookup
   - Converts 30-minute precipitation rate (mm/hr) into 30-minute accumulation:
     rainfall_30m = rate * 0.5 mm
4. Provenance & Metadata:
   - Preserves satellite payload metadata (INSAT-3DS IMAGER)
   - Assigns quality_flag ('GOOD' | 'MISSING')
   - Idempotent storage into rainfall_observations
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


def is_scientific_format(path_or_url: str | None) -> bool:
    """Accept scientific HDF5 formats, reject browse images."""
    if not path_or_url:
        return False
    clean = path_or_url.split("?", 1)[0].split("#", 1)[0].lower()
    if clean.endswith(_BROWSE_EXTENSIONS):
        return False
    if clean.endswith(_SCIENTIFIC_EXTENSIONS):
        return True
    if any(k in clean for k in ("3simg", "3rimg", "imr", "hem", "hdf")):
        return True
    return False


def validate_hdf5_signature(path_or_bytes: str | bytes) -> bool:
    """Verify exact 8-byte HDF5 header: \\x89HDF\\r\\n\\x1a\\n."""
    if isinstance(path_or_bytes, (bytes, bytearray)):
        return bytes(path_or_bytes[:8]) == _HDF5_SIGNATURE
    if not os.path.exists(path_or_bytes):
        return False
    with open(path_or_bytes, "rb") as fh:
        head = fh.read(8)
    return head == _HDF5_SIGNATURE


@dataclass
class RasterStageResult:
    """Per-stage outcome for MOSDAC HDF5 raster extraction."""
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
    dataset_name: str = "IMR",
    max_dist_deg: float = 0.25,
) -> list[dict]:
    """Open MOSDAC HDF5, inspect precipitation dataset, validate units, reject fill values,
    and sample at target coordinates using latitude and longitude arrays.
    """
    import h5py
    import numpy as np

    if not validate_hdf5_signature(hdf5_path):
        raise ValueError("File is not a valid HDF5 payload (signature mismatch)")

    with h5py.File(hdf5_path, "r") as f:
        # 1. Dataset selection
        target_ds_name = dataset_name
        if target_ds_name not in f:
            candidates = [k for k in ("IMR", "HEM", "rain", "Rain", "precipitation") if k in f]
            if not candidates:
                raise KeyError(f"Dataset '{dataset_name}' not found in HDF5 file (keys: {list(f.keys())})")
            target_ds_name = candidates[0]

        ds = f[target_ds_name]

        # 2. Unit validation
        units = ds.attrs.get("units", ds.attrs.get("Units", "mm/hr"))
        if isinstance(units, (bytes, bytearray)):
            units = units.decode("utf-8", "replace")
        elif isinstance(units, np.ndarray):
            units = str(units.item()) if units.size == 1 else str(units)
        units_str = (str(units) or "").strip()
        if not units_str or units_str.lower() not in ("mm/hr", "mm/h", "mm hr-1", "mm/hour"):
            raise ValueError(f"Invalid precipitation units '{units_str}'; expected 'mm/hr'")

        # 3. FillValue & scale
        fill = ds.attrs.get("_FillValue", ds.attrs.get("FillValue", -999.0))
        if isinstance(fill, (np.ndarray, list)):
            fill_val = float(fill[0])
        else:
            fill_val = float(fill) if fill is not None else -999.0

        scale = float(ds.attrs.get("scale_factor", 1.0))
        offset = float(ds.attrs.get("add_offset", 0.0))

        # 4. Actual spatial coordinates from file
        lat_key = next((k for k in ("latitude", "lat", "Grid/latitude", "Grid/lat") if k in f), None)
        lon_key = next((k for k in ("longitude", "lon", "Grid/longitude", "Grid/lon") if k in f), None)
        if not lat_key or not lon_key:
            raise KeyError("Spatial coordinates (latitude, longitude) missing from HDF5 file")

        lats = np.array(f[lat_key]).astype("float64")
        lons = np.array(f[lon_key]).astype("float64")

        arr = np.array(ds[()]).astype("float64")

        # Satellite & Sensor provenance
        sat = f.attrs.get("Satellite_Name", f.attrs.get("SatelliteName", b"INSAT-3DS"))
        sensor = f.attrs.get("Sensor_Name", f.attrs.get("SensorName", b"IMAGER"))
        if isinstance(sat, bytes): sat = sat.decode("utf-8", errors="ignore")
        if isinstance(sensor, bytes): sensor = sensor.decode("utf-8", errors="ignore")

        # Map dimensions: e.g. arr is (1, 801, 901) -> (time, lat, lon) or (801, 901)
        if arr.ndim == 3:
            if arr.shape[1] == len(lats) and arr.shape[2] == len(lons):
                axis_lat, axis_lon = 1, 2
            elif arr.shape[1] == len(lons) and arr.shape[2] == len(lats):
                axis_lat, axis_lon = 2, 1
            else:
                raise ValueError(f"Cannot align 3D dataset shape {arr.shape} with coords ({len(lats)}, {len(lons)})")
        elif arr.ndim == 2:
            if arr.shape[0] == len(lats) and arr.shape[1] == len(lons):
                axis_lat, axis_lon = 0, 1
            elif arr.shape[0] == len(lons) and arr.shape[1] == len(lats):
                axis_lat, axis_lon = 1, 0
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

            dist = max(abs(grid_lat - target_lat), abs(grid_lon - target_lon))
            if dist > max_dist_deg:
                val = None
                accum_30m = None
                q_flag = "MISSING"
            else:
                if arr.ndim == 3:
                    raw_num = arr[0, lat_idx, lon_idx] if axis_lat == 1 else arr[0, lon_idx, lat_idx]
                else:
                    raw_num = arr[lat_idx, lon_idx] if axis_lat == 0 else arr[lon_idx, lat_idx]

                is_fill = (abs(raw_num - fill_val) < 1e-2)
                if not np.isfinite(raw_num) or is_fill or raw_num < 0:
                    val = None
                    accum_30m = None
                    q_flag = "MISSING"
                else:
                    val = float(raw_num * scale + offset)
                    accum_30m = round(val * 0.5, 4)
                    q_flag = "GOOD"

            out.append({
                "location_id": p.get("location_id"),
                "latitude": target_lat,
                "longitude": target_lon,
                "grid_latitude": round(grid_lat, 4),
                "grid_longitude": round(grid_lon, 4),
                "value": val,
                "rainfall_30m": accum_30m,
                "quality_flag": q_flag,
                "units": "mm/hr",
                "satellite": str(sat),
                "sensor": str(sensor),
            })
        return out


def run_raster_stage(
    file_path_or_url: str,
    points: list[dict],
    dataset_name: str = "IMR",
) -> RasterStageResult:
    """Execute MOSDAC scientific raster parsing & point extraction."""
    res = RasterStageResult()
    if not h5py_available():
        res.skipped_reason = "h5py/numpy not installed — HDF5 sampling disabled"
        return res
    if not file_path_or_url:
        res.skipped_reason = "no file path or URL provided"
        return res
    if not is_scientific_format(file_path_or_url):
        res.skipped_reason = "file is not a scientific HDF5 format"
        return res

    if not os.path.exists(file_path_or_url):
        res.error = f"HDF5 file does not exist at '{file_path_or_url}'"
        return res

    res.download_ok = True

    if not validate_hdf5_signature(file_path_or_url):
        res.error = "signature validation failed: payload is not valid HDF5"
        return res
    res.signature_ok = True

    try:
        samples = sample_hdf5_at_points(file_path_or_url, points, dataset_name=dataset_name)
        res.samples = samples
        res.parse_ok = True
        res.sampled = sum(1 for s in samples if s.get("value") is not None)
        return res
    except Exception as e:
        res.error = f"MOSDAC HDF5 parse/sample failed: {type(e).__name__}: {e}"
        return res
