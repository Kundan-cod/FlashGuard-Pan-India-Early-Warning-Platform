"""GPM production vertical-slice tests.

Covers all 10 required test specifications:
  1. CMR response parsing
  2. GET DATA URL extraction
  3. HDF5 signature validation
  4. precipitation dataset selection
  5. fill-value rejection
  6. non-finite rejection
  7. unit validation
  8. spatial coordinate mapping (using actual Grid/lat, Grid/lon & rate-to-accumulation)
  9. idempotent ingestion (no duplicate observations)
  10. failure fallback to replay
"""
import json
import os
import tempfile
import unittest
from _util import bootstrap
bootstrap()

import numpy as np

# h5py (and the HDF5 C library) only ships in the ML/data image
# (requirements-ml.txt), not the minimal default image that runs the base
# Track A suite. Import it optionally so the raster-parsing tests skip cleanly
# instead of erroring out the WHOLE suite when h5py is absent (section 66:
# a missing optional dep must not masquerade as a real test failure).
try:
    import h5py  # noqa: F401
    HAVE_H5PY = True
except ImportError:  # pragma: no cover - depends on which image runs the suite
    h5py = None
    HAVE_H5PY = False

_NEEDS_H5PY = "requires h5py (ML/data image only, see requirements-ml.txt)"

from app.database import db, repositories as repo
from app.collectors import gpm_mapping as M
from app.collectors import gpm_raster as R
from app.collectors.gpm_collector import GpmCollector
from app.features.engineer import build_features


def _sample_cmr_payload():
    """Realistic NASA CMR UMM-JSON search response with RelatedUrls."""
    return {
        "items": [
            {
                "meta": {
                    "concept-id": "G1234567890-GES_DISC",
                    "native-id": "3B-HHR-L.MS.MRG.3IMERG.20260905-S173000-E175959.1050.V07C.HDF5",
                },
                "umm": {
                    "GranuleUR": "GPM_3IMERGHHL.07:3B-HHR-L.MS.MRG.3IMERG.20260905-S173000-E175959.1050.V07C.HDF5",
                    "CollectionReference": {
                        "ShortName": "GPM_3IMERGHHL",
                        "Version": "07",
                        "EntryTitle": "GPM IMERG Late Precipitation L3 Half Hourly 0.1 degree x 0.1 degree V07",
                    },
                    "TemporalExtent": {
                        "RangeDateTime": {
                            "BeginningDateTime": "2026-09-05T17:30:00.000Z",
                            "EndingDateTime": "2026-09-05T17:59:59.000Z",
                        }
                    },
                    "RelatedUrls": [
                        {
                            "URL": "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGHHL.07/2026/248/3B-HHR-L.MS.MRG.3IMERG.20260905-S173000-E175959.1050.V07C.HDF5",
                            "Type": "GET DATA",
                            "MimeType": "application/x-hdf5",
                            "Description": "Download granule HDF5",
                        },
                        {
                            "URL": "https://gpm1.gesdisc.eosdis.nasa.gov/opendap/GPM_3IMERGHHL.07/sample.html",
                            "Type": "USE SERVICE API",
                            "Description": "OPeNDAP access",
                        },
                        {
                            "URL": "https://gpm.nasa.gov/browse.png",
                            "Type": "GET RELATED VISUALIZATION",
                            "MimeType": "image/png",
                            "Description": "Browse image",
                        },
                    ],
                },
            }
        ]
    }


def _create_mock_hdf5(
    file_path: str,
    *,
    dataset_name: str = "Grid/precipitation",
    units: str = "mm/hr",
    fill_value: float = -9999.9,
    include_coords: bool = True,
    sample_rate: float = 14.0,
    has_fill: bool = False,
    has_nan: bool = False,
) -> None:
    """Create a synthetic HDF5 file matching GPM 3IMERGHHL structure."""
    with h5py.File(file_path, "w") as f:
        grid = f.create_group("Grid")
        if include_coords:
            # Grid lat: 30.0 to 30.2, lon: 78.0 to 78.2 (step 0.1)
            lats = np.array([30.0, 30.1, 30.2], dtype="float32")
            lons = np.array([78.0, 78.1, 78.2], dtype="float32")
            grid.create_dataset("lat", data=lats)
            grid.create_dataset("lon", data=lons)

        if dataset_name:
            # Shape (1, 3, 3) -> (time, lon, lat)
            data = np.full((1, 3, 3), sample_rate, dtype="float32")
            if has_fill:
                data[0, 1, 1] = fill_value
            if has_nan:
                data[0, 1, 1] = np.nan

            ds = f.create_dataset(dataset_name, data=data)
            if units is not None:
                ds.attrs["units"] = units
            if fill_value is not None:
                ds.attrs["_FillValue"] = fill_value


class _FakeDiscovery:
    def __init__(self, payload):
        self._payload = payload
        self.calls = []

    def search(self, **kwargs):
        self.calls.append(kwargs)
        return self._payload


class _GpmSliceBase(unittest.TestCase):
    """Shared fixture: isolated DB, clean token env, temp-file bookkeeping."""

    def setUp(self):
        db.init_db(reset=True)
        os.environ.pop("NASA_EARTHDATA_TOKEN", None)
        self.tmp_files = []

    def tearDown(self):
        os.environ.pop("NASA_EARTHDATA_TOKEN", None)
        for p in self.tmp_files:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def _temp_hdf5(self, **kwargs) -> str:
        fd, path = tempfile.mkstemp(prefix="test_gpm_", suffix=".HDF5")
        os.close(fd)
        self.tmp_files.append(path)
        _create_mock_hdf5(path, **kwargs)
        return path


class GpmMappingSliceTest(_GpmSliceBase):
    """Pure-Python slice (CMR parsing, URL extraction, replay fallback, token
    gating) — no HDF5 parsing, so runs in EVERY image including the minimal
    default one that has no h5py."""

    # ---- 1. CMR response parsing ----
    def test_1_cmr_response_parsing(self):
        payload = _sample_cmr_payload()
        records = M.payload_to_discovery_records(payload, retrieved_at="2026-09-06T12:00:00Z")
        self.assertEqual(len(records), 1)
        rec = records[0]
        self.assertEqual(rec["item_id"], "G1234567890-GES_DISC")
        self.assertEqual(rec["product"], "GPM_3IMERGHHL.07")
        self.assertEqual(rec["observed_date"], "2026-09-05T17:30:00.000Z")
        self.assertIsNone(rec["numeric_value"])
        self.assertEqual(rec["stage"], "DISCOVERY_ONLY")

        # Provenance in raw_reference
        raw_ref = json.loads(rec["raw_reference"])
        self.assertEqual(raw_ref["concept_id"], "G1234567890-GES_DISC")
        self.assertEqual(raw_ref["collection"], "GPM_3IMERGHHL")
        self.assertEqual(raw_ref["version"], "07")
        self.assertEqual(raw_ref["variable_path"], "Grid/precipitation")
        self.assertEqual(raw_ref["units"], "mm/hr")

    # ---- 2. GET DATA URL extraction ----
    def test_2_get_data_url_extraction(self):
        payload = _sample_cmr_payload()
        item = payload["items"][0]
        downloads = M.extract_downloads(item)
        self.assertEqual(len(downloads), 1, "Only GET DATA URL should be extracted")
        dl = downloads[0]
        self.assertEqual(dl["type"], "GET DATA")
        self.assertTrue(dl["url"].startswith("https://gpm1.gesdisc.eosdis.nasa.gov/data/"))
        self.assertFalse(any("browse.png" in d["url"] for d in downloads),
                         "Browse image must never be extracted as GET DATA")

    # ---- 10. Failure fallback to replay (pure-Python, no HDF5) ----
    def test_10_failure_fallback_to_replay(self):
        # 1. Without token -> NOT_CONFIGURED, replay untouched
        c = GpmCollector(verified=True, discovery=_FakeDiscovery(_sample_cmr_payload()))
        res = c.run()
        self.assertEqual(res.stored, 0)
        health = repo.get_source_health("gpm")
        self.assertEqual(health["status"], "NOT_CONFIGURED")

        # 2. Seed replay location Devgaon
        from app.services import seed
        seed.run(reset=True)
        devgaon = repo.list_locations(level="village")[0]
        self.assertIsNotNone(devgaon)

        # Insert replay baseline rainfall
        repo.upsert_rainfall({
            "source": "replay",
            "ts": "2026-09-05T12:00:00Z",
            "latitude": devgaon["latitude"],
            "longitude": devgaon["longitude"],
            "rainfall_30m": 15.0,
            "rainfall_3h": 35.0,
            "rainfall_24h": 70.0,
            "quality_flag": "GOOD",
            "realtime_class": "replay",
        })

        # Feature pipeline cleanly uses replay rainfall
        fs = build_features(devgaon["id"])
        self.assertTrue(fs.available["rainfall"])
        self.assertEqual(fs.provenance["rainfall"]["source"], "replay")
        self.assertEqual(fs.values["rain_30m"], 15.0)

        # 3. Collector error reports ERROR
        os.environ["NASA_EARTHDATA_TOKEN"] = "token"
        c_unverified = GpmCollector(verified=False, discovery=_FakeDiscovery(_sample_cmr_payload()))
        with self.assertRaises(RuntimeError):
            c_unverified.run()
        health_err = repo.get_source_health("gpm")
        self.assertEqual(health_err["status"], "ERROR")

    # ---- Credential placeholder tests (pure-Python, no HDF5) ----
    def test_placeholder_token_is_not_configured(self):
        for placeholder in ("your_token_here", "changeme", "CHANGEME", "  ", "<token>"):
            with self.subTest(placeholder=placeholder):
                db.init_db(reset=True)
                os.environ["NASA_EARTHDATA_TOKEN"] = placeholder
                c = GpmCollector(verified=True, discovery=_FakeDiscovery(_sample_cmr_payload()))
                self.assertFalse(c.has_token())
                res = c.run()
                self.assertEqual(res.stored, 0)
                self.assertEqual(repo.get_source_health("gpm")["status"], "NOT_CONFIGURED")


@unittest.skipUnless(HAVE_H5PY, _NEEDS_H5PY)
class GpmRasterSliceTest(_GpmSliceBase):
    """Raster-parsing slice (tests 3-9): build + sample real HDF5 granules.
    Requires h5py, which ships only in the ML/data image (requirements-ml.txt);
    skipped cleanly in the minimal default image."""

    # ---- 3. HDF5 signature validation ----
    def test_3_hdf5_signature_validation(self):
        valid_path = self._temp_hdf5()
        self.assertTrue(R.validate_hdf5_signature(valid_path))

        # Invalid: HTML page or text error
        fd, invalid_path = tempfile.mkstemp(prefix="test_bad_", suffix=".HDF5")
        os.close(fd)
        self.tmp_files.append(invalid_path)
        with open(invalid_path, "wb") as fh:
            fh.write(b"<!DOCTYPE html><html><head><title>Earthdata Login</title></head></html>")

        self.assertFalse(R.validate_hdf5_signature(invalid_path))
        with self.assertRaises(ValueError):
            R.sample_hdf5_at_points(invalid_path, [{"latitude": 30.06, "longitude": 78.06}])

    # ---- 4. Precipitation dataset selection ----
    def test_4_precipitation_dataset_selection(self):
        # Good dataset
        good_path = self._temp_hdf5(dataset_name="Grid/precipitation")
        samples = R.sample_hdf5_at_points(good_path, [{"latitude": 30.06, "longitude": 78.06}])
        self.assertEqual(len(samples), 1)
        self.assertIsNotNone(samples[0]["value"])

        # Missing dataset
        missing_path = self._temp_hdf5(dataset_name="Grid/random_var")
        with self.assertRaises(KeyError):
            R.sample_hdf5_at_points(missing_path, [{"latitude": 30.06, "longitude": 78.06}])

    # ---- 5. Fill-value rejection ----
    def test_5_fill_value_rejection(self):
        fill_path = self._temp_hdf5(sample_rate=-9999.9, has_fill=True)
        samples = R.sample_hdf5_at_points(fill_path, [{"latitude": 30.1, "longitude": 78.1}])
        self.assertEqual(len(samples), 1)
        self.assertIsNone(samples[0]["rate_mm_hr"], "FillValue must be rejected")
        self.assertIsNone(samples[0]["rainfall_30m"], "FillValue must not yield accumulation")

    # ---- 6. Non-finite rejection ----
    def test_6_non_finite_rejection(self):
        nan_path = self._temp_hdf5(has_nan=True)
        samples = R.sample_hdf5_at_points(nan_path, [{"latitude": 30.1, "longitude": 78.1}])
        self.assertEqual(len(samples), 1)
        self.assertIsNone(samples[0]["rate_mm_hr"], "NaN must be rejected")
        self.assertIsNone(samples[0]["rainfall_30m"], "NaN must not yield accumulation")

    # ---- 7. Unit validation ----
    def test_7_unit_validation(self):
        # Invalid units
        bad_units_path = self._temp_hdf5(units="degC")
        with self.assertRaises(ValueError):
            R.sample_hdf5_at_points(bad_units_path, [{"latitude": 30.06, "longitude": 78.06}])

        # Missing units
        no_units_path = self._temp_hdf5(units=None)
        with self.assertRaises(ValueError):
            R.sample_hdf5_at_points(no_units_path, [{"latitude": 30.06, "longitude": 78.06}])

    # ---- 8. Spatial coordinate mapping & Rate-to-accumulation ----
    def test_8_spatial_coordinate_mapping(self):
        # Rate = 10.0 mm/hr. Half-hour accumulation = 10.0 * 0.5 = 5.0 mm
        path = self._temp_hdf5(sample_rate=10.0)
        target = [{"latitude": 30.06, "longitude": 78.06, "name": "TEST_LOCATION_GPM_TARGET", "is_test_location": True}]
        samples = R.sample_hdf5_at_points(path, target)
        self.assertEqual(len(samples), 1)
        s = samples[0]
        self.assertAlmostEqual(s["rate_mm_hr"], 10.0, places=3)
        self.assertAlmostEqual(s["rainfall_30m"], 5.0, places=3,
                               msg="mm/hr rate must be converted to 30m accumulation via * 0.5")
        self.assertTrue(s["is_test_location"])
        # Mapped to nearest grid coordinates
        self.assertAlmostEqual(s["grid_latitude"], 30.1, places=1)
        self.assertAlmostEqual(s["grid_longitude"], 78.1, places=1)

    # ---- 9. Idempotent ingestion ----
    def test_9_idempotent_ingestion(self):
        os.environ["NASA_EARTHDATA_TOKEN"] = "valid-token-1234"
        path = self._temp_hdf5(sample_rate=8.0)

        # Mock raster stage to use our verified test HDF5
        original_run_raster = R.run_raster_stage

        def mock_run_raster(url, points, token=None, media_type=None):
            samples = R.sample_hdf5_at_points(path, points)
            res = R.RasterStageResult(download_ok=True, signature_ok=True,
                                      parse_ok=True, sampled=len(samples),
                                      samples=samples)
            return res

        R.run_raster_stage = mock_run_raster
        try:
            c = GpmCollector(verified=True, enable_raster=True,
                             discovery=_FakeDiscovery(_sample_cmr_payload()))
            res1 = c.run()
            self.assertEqual(res1.stored, 2)  # 1 discovery + 1 rainfall

            rain_rows1 = db.query("SELECT * FROM rainfall_observations WHERE source='gpm'")
            disc_rows1 = db.query("SELECT * FROM gpm_discovery WHERE source='gpm'")
            self.assertEqual(len(rain_rows1), 1)
            self.assertEqual(len(disc_rows1), 1)

            # Re-run same granule: must NOT duplicate observations
            res2 = c.run()
            rain_rows2 = db.query("SELECT * FROM rainfall_observations WHERE source='gpm'")
            disc_rows2 = db.query("SELECT * FROM gpm_discovery WHERE source='gpm'")
            self.assertEqual(len(rain_rows2), 1, "Repeated ingestion must not duplicate rainfall rows")
            self.assertEqual(len(disc_rows2), 1, "Repeated ingestion must not duplicate discovery rows")
        finally:
            R.run_raster_stage = original_run_raster


if __name__ == "__main__":
    unittest.main()
