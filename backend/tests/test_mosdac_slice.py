"""MOSDAC vertical-slice tests (master prompt sections 7, 34, 40, 66).

Prove — with zero network and zero Track B deps (httpx/pydantic absent in the
portable sandbox) — that the MOSDAC bridge collector honours every constraint:

  1. A discovery run stores INSAT granule metadata into `mosdac_discovery` with
     numeric_value=NULL and stage='DISCOVERY_ONLY'.
  2. A discovery record NEVER enters rainfall_observations, so it can never
     masquerade as a numeric rainfall value in the ML feature pipeline.
  3. No endpoint (MOSDAC_API_BASE_URL) -> honest NOT_CONFIGURED health status
     (one of the unchanged 7 states), NOT an error, and NO rows written -> replay
     stays untouched. The verified package hard-codes no public endpoint, so
     "configured" means the operator supplied a base URL.
  3b. A placeholder base URL (http://example.com, changeme, ...) counts as NOT
      configured — no doomed request, no ERROR.
  3c. A genuine-looking base URL IS honoured (guards against over-filtering).
  4. Unverified source -> refuses to fetch (ERROR), no invented endpoints.
  5. Successful discovery reports NRT; there is NO raster/HDF parse stage, so no
     rainfall value is ever produced (discovery-only, honestly).
  6. The pure-Python granule->discovery mapping keeps numeric_value=None and
     pulls satellite/resolution from the VERIFIED MOSDAC_DATASETS registry (never
     invented).

The discovery adapter is injected as a tiny fake exposing `.search(config)` and
`.normalize_search_items(dataset_id, items)`, mirroring the vendored
MosdacCollector's interface, so the honesty-critical logic is provable in-sandbox
(the vendored collector imports httpx at module load).
"""
import os
import tempfile
import unittest
from _util import bootstrap
bootstrap()

try:
    import h5py
    import numpy as np
    HAVE_H5PY = True
except ImportError:
    h5py = None
    np = None
    HAVE_H5PY = False

from app.database import db, repositories as repo
from app.collectors import mosdac_mapping as M
from app.collectors import mosdac_raster as MR
from app.collectors.mosdac_collector import MosdacCollector

_BASE_URL_VAR = "MOSDAC_API_BASE_URL"


# Raw mdapi search items (the shape the documented workflow returns): gId,
# title/name, startTime, endTime, downloadUrl. No numeric rainfall value.
def _sample_items():
    return [
        {
            "gId": "3RIMG_L2B_HEM_20240801_0000",
            "title": "INSAT-3DR Hydro-Estimator 20240801 0000UTC",
            "startTime": "2024-08-01T00:00:00Z",
            "endTime": "2024-08-01T00:30:00Z",
            "downloadUrl": "https://mosdac.example/order/3RIMG_L2B_HEM_20240801_0000.h5",
        }
    ]


class _FakeDiscovery:
    """Stand-in for the vendored MosdacCollector: returns canned raw items and
    normalizes them EXACTLY like the vendored normalize_search_items (verified
    field mapping), producing plain dicts. No network, no httpx, no pydantic."""

    def __init__(self, items):
        self._items = items
        self.calls = []

    def search(self, config):
        self.calls.append(config)
        return self._items

    def normalize_search_items(self, dataset_id, items):
        out = []
        for it in items:
            gid = it.get("gId") or it.get("granuleId")
            out.append({
                "dataset_id": dataset_id,
                "granule_id": str(gid) if gid else None,
                "title": it.get("title") or it.get("name"),
                "start_time": it.get("startTime"),
                "end_time": it.get("endTime"),
                "download_url": it.get("downloadUrl") or it.get("url"),
                "metadata": it,
            })
        return out


class MosdacSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)
        os.environ.pop(_BASE_URL_VAR, None)

    def tearDown(self):
        os.environ.pop(_BASE_URL_VAR, None)

    # ---- 1 + 2: discovery stores metadata, never rainfall ----
    def test_discovery_stores_metadata_and_never_rainfall(self):
        os.environ[_BASE_URL_VAR] = "https://mosdac.example/mdapi"
        c = MosdacCollector(verified=True,
                            discovery=_FakeDiscovery(_sample_items()))
        res = c.run()
        self.assertEqual(res.stored, 1, "one discovery record expected")

        disc = repo.mosdac_discovery_recent()
        self.assertEqual(len(disc), 1)
        rec = disc[0]
        self.assertIsNone(rec["numeric_value"],
                          "discovery record must carry NO rainfall value")
        self.assertEqual(rec["stage"], "DISCOVERY_ONLY")
        self.assertEqual(rec["granule_id"], "3RIMG_L2B_HEM_20240801_0000")
        self.assertTrue(rec["download_url"].endswith(".h5"))
        # satellite/resolution come from the VERIFIED registry, not invented.
        self.assertEqual(rec["satellite"], "INSAT-3DR")

        # The feature pipeline reads rainfall_observations — it must stay empty.
        rain = db.query("SELECT COUNT(*) AS n FROM rainfall_observations "
                        "WHERE source='mosdac'")
        self.assertEqual(rain[0]["n"], 0,
                         "a discovery record must NEVER reach rainfall_observations")

    # ---- 3: no endpoint -> NOT_CONFIGURED, no rows, replay untouched ----
    def test_no_endpoint_is_not_configured_not_error(self):
        c = MosdacCollector(verified=True,
                            discovery=_FakeDiscovery(_sample_items()))
        res = c.run()
        self.assertEqual(res.stored, 0)

        health = repo.get_source_health("mosdac")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "NOT_CONFIGURED")
        self.assertIsNone(health["last_success_at"],
                          "NOT_CONFIGURED is not a success")
        self.assertEqual(len(repo.mosdac_discovery_recent()), 0)
        self.assertEqual(
            db.query("SELECT COUNT(*) AS n FROM rainfall_observations "
                     "WHERE source='mosdac'")[0]["n"], 0)

    # ---- 3b: placeholder base URL counts as NOT configured (honest, no ERROR) ----
    def test_placeholder_endpoint_is_not_configured(self):
        for placeholder in ("http://example.com", "https://example.com",
                            "changeme", "  ", "placeholder", "<url>", "TODO",
                            "null"):
            with self.subTest(placeholder=placeholder):
                db.init_db(reset=True)
                os.environ[_BASE_URL_VAR] = placeholder
                c = MosdacCollector(verified=True,
                                    discovery=_FakeDiscovery(_sample_items()))
                self.assertFalse(c.is_configured(),
                                 f"'{placeholder}' must not count as an endpoint")
                res = c.run()
                self.assertEqual(res.stored, 0)
                health = repo.get_source_health("mosdac")
                self.assertEqual(health["status"], "NOT_CONFIGURED",
                                 f"'{placeholder}' should yield NOT_CONFIGURED")
                self.assertEqual(len(repo.mosdac_discovery_recent()), 0)

    # ---- 3c: a genuine-looking base URL IS honoured (guards over-filtering) ----
    def test_real_looking_endpoint_is_honoured(self):
        os.environ[_BASE_URL_VAR] = "https://mosdac.gov.in/mdapi/v1"
        c = MosdacCollector(verified=True,
                            discovery=_FakeDiscovery(_sample_items()))
        self.assertTrue(c.is_configured(),
                        "a real-looking endpoint must be accepted")
        res = c.run()
        self.assertEqual(res.stored, 1)
        self.assertEqual(repo.get_source_health("mosdac")["status"], "NRT")

    # ---- 4: unverified source refuses to fetch (honest ERROR) ----
    def test_unverified_source_refuses_and_reports_error(self):
        os.environ[_BASE_URL_VAR] = "https://mosdac.example/mdapi"
        c = MosdacCollector(verified=False,
                            discovery=_FakeDiscovery(_sample_items()))
        with self.assertRaises(RuntimeError):
            c.run()
        health = repo.get_source_health("mosdac")
        self.assertIsNotNone(health)
        self.assertEqual(health["status"], "ERROR")

    # ---- 5: successful discovery reports NRT; no parse stage, no measurement ----
    def test_successful_discovery_reports_nrt_and_no_parse_stage(self):
        os.environ[_BASE_URL_VAR] = "https://mosdac.example/mdapi"
        c = MosdacCollector(verified=True,
                            discovery=_FakeDiscovery(_sample_items()))
        c.run()
        health = repo.get_source_health("mosdac")
        self.assertEqual(health["status"], "NRT")
        self.assertIsNotNone(health["last_success_at"])
        self.assertTrue(any("parse" in n and "discovery-only" in n
                            for n in c._stage_notes),
                        f"expected a discovery-only parse note; got {c._stage_notes}")
        self.assertEqual(
            db.query("SELECT COUNT(*) AS n FROM rainfall_observations "
                     "WHERE source='mosdac'")[0]["n"], 0)

    # ---- 6: pure-Python mapping keeps numeric_value=None, uses verified registry ----
    def test_mapping_invariant_numeric_value_is_none(self):
        granules = [{
            "dataset_id": "3RIMG_L2B_HEM",
            "granule_id": "G1",
            "title": "t",
            "start_time": "2024-08-01T00:00:00Z",
            "end_time": "2024-08-01T00:30:00Z",
            "download_url": "https://mosdac.example/a.h5",
            "metadata": {},
        }]
        recs = M.granules_to_discovery_records(
            granules, retrieved_at="2026-09-06T00:00:00Z")
        self.assertEqual(len(recs), 1)
        self.assertIsNone(recs[0]["numeric_value"])
        self.assertEqual(recs[0]["stage"], M.DISCOVERY_ONLY)
        self.assertEqual(recs[0]["quality_flag"], "UNKNOWN")
        # satellite pulled from the verified registry for a known dataset_id.
        self.assertEqual(recs[0]["satellite"], "INSAT-3DR")

    def test_mapping_unknown_dataset_leaves_registry_fields_none(self):
        granules = [{
            "dataset_id": "NOT_A_REAL_DATASET",
            "granule_id": "G2",
            "download_url": "https://mosdac.example/b.h5",
        }]
        recs = M.granules_to_discovery_records(granules)
        self.assertEqual(len(recs), 1)
        self.assertIsNone(recs[0]["satellite"],
                          "unknown dataset must NOT get an invented satellite")
        self.assertIsNone(recs[0]["resolution"])
        self.assertIsNone(recs[0]["numeric_value"])

    # ---- granule with no download URL still yields a (non-measurement) record ----
    def test_granule_without_download_still_discovered(self):
        items = _sample_items()
        items[0].pop("downloadUrl")
        os.environ[_BASE_URL_VAR] = "https://mosdac.example/mdapi"
        c = MosdacCollector(verified=True, discovery=_FakeDiscovery(items))
        res = c.run()
        self.assertEqual(res.stored, 1)
        rec = repo.mosdac_discovery_recent()[0]
        self.assertIsNone(rec["download_url"])
        self.assertIsNone(rec["numeric_value"])

    # ---- reingest is idempotent on (dataset_id, granule_id, download_url) ----
    def test_reingest_is_idempotent(self):
        os.environ[_BASE_URL_VAR] = "https://mosdac.example/mdapi"
        fake = _FakeDiscovery(_sample_items())
        MosdacCollector(verified=True, discovery=fake).run()
        MosdacCollector(verified=True, discovery=fake).run()
        self.assertEqual(len(repo.mosdac_discovery_recent()), 1,
                         "re-discovering the same granule must not duplicate rows")


def _create_mock_mosdac_hdf5(
    path: str,
    sample_rate: float = 6.0,
    units: str = "mm/hr",
    fill_value: float = -999.0,
    has_fill: bool = False,
    dataset_name: str = "IMR",
):
    """Generate minimal valid INSAT-3DS HDF5 structure for testing."""
    if not HAVE_H5PY:
        return
    with h5py.File(path, "w") as f:
        f.attrs["Satellite_Name"] = "INSAT-3DS"
        f.attrs["Sensor_Name"] = "IMAGER"
        f.attrs["Product_Name"] = "IMR"

        lats = np.array([30.2, 30.1, 30.0], dtype="float64")
        lons = np.array([78.0, 78.1, 78.2], dtype="float64")
        f.create_dataset("latitude", data=lats)
        f.create_dataset("longitude", data=lons)
        f.create_dataset("time", data=np.array([14035200.0], dtype="float64"))

        # Shape (1, 3, 3) -> (time, lat, lon)
        data = np.full((1, 3, 3), sample_rate, dtype="float32")
        if has_fill:
            data[0, 1, 1] = fill_value

        ds = f.create_dataset(dataset_name, data=data)
        if units is not None:
            ds.attrs["units"] = units
        if fill_value is not None:
            ds.attrs["_FillValue"] = fill_value


@unittest.skipUnless(HAVE_H5PY, "requires h5py and numpy")
class MosdacRasterSliceTest(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)
        os.environ.pop(_BASE_URL_VAR, None)
        self.tmp_files = []

    def tearDown(self):
        os.environ.pop(_BASE_URL_VAR, None)
        for p in self.tmp_files:
            if os.path.exists(p):
                try:
                    os.unlink(p)
                except OSError:
                    pass

    def _temp_hdf5(self, **kwargs) -> str:
        fd, path = tempfile.mkstemp(prefix="test_mosdac_", suffix=".h5")
        os.close(fd)
        self.tmp_files.append(path)
        _create_mock_mosdac_hdf5(path, **kwargs)
        return path

    # ---- 1. HDF5 signature validation ----
    def test_hdf5_signature_validation(self):
        valid_path = self._temp_hdf5()
        self.assertTrue(MR.validate_hdf5_signature(valid_path))

        # Invalid: text file
        fd, bad_path = tempfile.mkstemp(prefix="test_bad_", suffix=".h5")
        os.close(fd)
        self.tmp_files.append(bad_path)
        with open(bad_path, "wb") as fh:
            fh.write(b"<html>404 Not Found</html>")
        self.assertFalse(MR.validate_hdf5_signature(bad_path))

    # ---- 2. Point sampling, units validation, and accumulation calculation ----
    def test_sample_hdf5_at_points_and_units(self):
        path = self._temp_hdf5(sample_rate=8.0, units="mm/hr")
        target = [{"latitude": 30.1, "longitude": 78.1, "location_id": 1}]
        samples = MR.sample_hdf5_at_points(path, target)
        self.assertEqual(len(samples), 1)
        s = samples[0]
        self.assertEqual(s["quality_flag"], "GOOD")
        self.assertAlmostEqual(s["value"], 8.0, places=2)
        # 30-min accumulation: rate (8.0 mm/hr) * 0.5 hr = 4.0 mm
        self.assertAlmostEqual(s["rainfall_30m"], 4.0, places=2)
        self.assertAlmostEqual(s["grid_latitude"], 30.1, places=2)
        self.assertAlmostEqual(s["grid_longitude"], 78.1, places=2)

        # Invalid units must raise ValueError
        bad_units_path = self._temp_hdf5(units="m/s")
        with self.assertRaises(ValueError):
            MR.sample_hdf5_at_points(bad_units_path, target)

    # ---- 3. Fill value rejection (missing != zero) ----
    def test_fill_value_rejection(self):
        path = self._temp_hdf5(sample_rate=5.0, has_fill=True, fill_value=-999.0)
        target = [{"latitude": 30.1, "longitude": 78.1, "location_id": 1}]
        samples = MR.sample_hdf5_at_points(path, target)
        s = samples[0]
        self.assertIsNone(s["value"], "Fill value must NOT be converted to numeric measurement")
        self.assertIsNone(s["rainfall_30m"])
        self.assertEqual(s["quality_flag"], "MISSING")

    # ---- 4. Stage 2 integration into rainfall_observations ----
    def test_stage2_integration_into_rainfall_observations(self):
        os.environ[_BASE_URL_VAR] = "https://mosdac.example/mdapi"
        path = self._temp_hdf5(sample_rate=10.0)

        granule = {
            "gId": "3SIMG_TEST_GRANULE",
            "title": "INSAT-3DS IMR Test Granule",
            "startTime": "2026-09-07T16:00:00Z",
            "endTime": "2026-09-07T16:30:00Z",
            "downloadUrl": path,
        }

        test_village = [{"latitude": 30.1, "longitude": 78.1, "location_id": 42}]
        c = MosdacCollector(
            verified=True,
            enable_raster=True,
            villages=test_village,
            discovery=_FakeDiscovery([granule]),
        )

        res = c.run()
        self.assertEqual(res.stored, 2, "1 discovery record + 1 rainfall observation expected")

        # Verify rainfall_observations
        rain_rows = db.query("SELECT * FROM rainfall_observations WHERE source='mosdac'")
        self.assertEqual(len(rain_rows), 1)
        row = rain_rows[0]
        self.assertEqual(row["source"], "mosdac")
        self.assertAlmostEqual(row["rainfall_30m"], 5.0, places=2)  # 10.0 * 0.5
        self.assertEqual(row["quality_flag"], "GOOD")
        self.assertEqual(row["realtime_class"], "near_real_time")

        # Verify mosdac_discovery stage elevated to RASTER_SAMPLED
        disc_rows = repo.mosdac_discovery_recent()
        self.assertEqual(len(disc_rows), 1)
        self.assertEqual(disc_rows[0]["stage"], M.RASTER_SAMPLED)
        self.assertAlmostEqual(disc_rows[0]["numeric_value"], 10.0, places=2)

        # Idempotency check: re-running does NOT duplicate rows
        res2 = c.run()
        rain_rows2 = db.query("SELECT * FROM rainfall_observations WHERE source='mosdac'")
        self.assertEqual(len(rain_rows2), 1, "Re-running ingestion must be idempotent")


if __name__ == "__main__":
    unittest.main()
