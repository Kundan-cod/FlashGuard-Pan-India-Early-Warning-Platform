"""
GPM IMERG bridge collector (Track B) — production vertical slice.

Integrates the verified NASA CMR UMM-JSON discovery API and GES DISC HDF5 download
and parsing into this project's collector contract (fetch -> validate -> normalize -> store).

Production two-stage architecture:
  Stage 1 — CMR DISCOVERY:
    NASA CMR API -> granule metadata + exact GET DATA download URL -> gpm_discovery table.
    numeric_value stays NULL. This NEVER enters rainfall_observations.

  Stage 2 — SCIENTIFIC HDF5 DOWNLOAD, PARSE & SPATIAL SAMPLING:
    Downloads the exact CMR GET DATA URL with NASA_EARTHDATA_TOKEN Bearer auth.
    Validates HDF5 8-byte signature before parsing.
    Parses Grid/precipitation with strict unit ('mm/hr') and _FillValue (-9999.9) checks.
    Reads actual Grid/lat and Grid/lon coordinate arrays from the HDF5 file.
    Samples at real administrative units or the designated technical integration test location.
    Converts 30-minute rate (mm/hr) to accumulation (rainfall_30m = rate * 0.5 mm).
    Writes real GPM observations to rainfall_observations (PostGIS / SQLite).

Honest 7-state source status:
  - successful CMR + download + parse + numeric data -> NRT
  - discovery-only (no numeric data sampled) -> DISCOVERY_ONLY / not NRT
  - failed download/parse -> ERROR
  - missing credential -> NOT_CONFIGURED
  - Replay fallback remains active when GPM is not configured or errors out.
"""
from __future__ import annotations

import json
import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import gpm_mapping as M
from app.collectors import gpm_raster as R
from app.database import repositories as repo

# GPM IMERG is a near-real-time satellite product
GPM_REALTIME_CLASS = "near_real_time"
# ~0.1 degree native grid -> metres (provenance only; ~11.1 km at equator).
GPM_RESOLUTION_M = 11132.0


class GpmCollector(BaseCollector):
    """Bridge collector for NASA GPM IMERG via NASA CMR and GES DISC."""

    source_key = "gpm"
    realtime_class = GPM_REALTIME_CLASS

    def __init__(self, *, verified: bool, api_base_url: str | None = None,
                 auth_env_var: str | None = "NASA_EARTHDATA_TOKEN",
                 product: str = "GPM_3IMERGHHL", limit: int = 10,
                 enable_raster: bool = True,
                 villages: list[dict] | None = None,
                 client: Any = None,
                 discovery: Any = None):
        self.verified = verified
        self.api_base_url = api_base_url
        self.auth_env_var = auth_env_var
        self.product = product
        self.limit = limit
        self.enable_raster = enable_raster
        self._villages = villages
        self._client = client
        self._discovery = discovery
        self._stage_notes: list[str] = []
        self._sampled_count: int = 0

    _PLACEHOLDER_TOKENS = frozenset({
        "", "changeme", "change_me", "your_token_here", "your-token-here",
        "yourtoken", "token", "todo", "tbd", "xxx", "xxxx", "placeholder",
        "none", "null", "na", "n/a", "replace_me", "replace-me",
        "nasa_earthdata_token", "earthdata_token", "<token>", "<your_token>",
        "example", "dummy", "test", "fixme",
    })

    def _token(self) -> str | None:
        """Return Earthdata token only if it looks genuinely usable."""
        import os
        if not self.auth_env_var:
            return None
        raw = os.environ.get(self.auth_env_var)
        if raw is None:
            return None
        val = raw.strip()
        if not val or val.lower() in self._PLACEHOLDER_TOKENS:
            return None
        return val

    def has_token(self) -> bool:
        return bool(self._token())

    # ---- lifecycle ----
    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'gpm' is NOT verified in config/data_sources.yml — "
                "refusing to fetch (no invented endpoints/credentials).")
        if not self.has_token():
            raise _NotConfigured(
                f"{self.auth_env_var} not set — GPM not configured; "
                "staying on replay/discovery-only.")

        collector = self._discovery
        if collector is None:
            from app.data_layer.sources.gpm.collectors.gpm import GPMCollector
            from app.data_layer.sources.gpm.config import Settings
            settings = Settings()
            collector = GPMCollector(settings=settings, client=self._client)

        w = window or {}
        payload = collector.search(
            product=w.get("product", self.product),
            latitude=w.get("latitude"),
            longitude=w.get("longitude"),
            start_date=w.get("start_date"),
            end_date=w.get("end_date"),
            limit=w.get("limit", self.limit),
        )
        items = payload.get("items", []) if isinstance(payload, dict) else []
        self._stage_notes.append(f"discovery: {len(items)} item(s)")
        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=list(items),
                        meta={"payload_kind": "cmr_discovery"})

    def validate(self, raw: RawBatch) -> list[Issue]:
        issues: list[Issue] = []
        for i, item in enumerate(raw.records):
            if not isinstance(item, dict):
                issues.append(Issue("BAD", "CMR item is not an object", i))
                continue
            meta = item.get("meta", {})
            umm = item.get("umm", {})
            if not meta.get("concept-id") and not item.get("@id") and not umm.get("GranuleUR"):
                issues.append(Issue("WARNING", "Granule has no identifier", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        records: list[dict] = []
        retrieved = raw.fetched_at
        for item in raw.records:
            records.extend(M.item_to_discovery_records(item, retrieved_at=retrieved))
        return records

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Stage 1: persist discovery records (numeric_value NULL) into gpm_discovery
        for d in records:
            try:
                repo.upsert_gpm_discovery(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1

        # Stage 2: HDF5 download, parse, and spatial sampling
        self._maybe_run_raster_stage(records, res)
        return res

    def _maybe_run_raster_stage(self, records: list[dict], res: StoreResult) -> None:
        if not self.enable_raster:
            self._stage_notes.append("raster: disabled by config")
            return
        if not R.h5py_available():
            self._stage_notes.append("raster: skipped (h5py not installed; discovery-only)")
            return

        points = self._sampling_points()
        if not points:
            self._stage_notes.append("raster: skipped (no sampling coordinates)")
            return

        token = self._token()
        sampled_total = 0
        used = 0
        # Process the latest granule for raster sampling
        for d in records[:1]:
            url = d.get("download_url")
            if not url:
                continue
            used += 1
            stage = R.run_raster_stage(url, points, token=token,
                                       media_type=d.get("media_type"))
            if stage.skipped_reason:
                self._stage_notes.append(f"raster: {stage.skipped_reason}")
                continue
            if stage.error:
                self._stage_notes.append(f"raster: {stage.error}")
                self._log_quality(f"raster stage error: {stage.error}",
                                  table="gpm_discovery", flag="WARNING")
                raise RuntimeError(f"GPM raster stage failed: {stage.error}")

            # Persist real sampled values to rainfall_observations
            for s in stage.samples:
                if s.get("rainfall_30m") is None:
                    continue  # missing != zero — never fabricate
                self._store_sampled_rainfall(d, s)
                sampled_total += 1

                # Update discovery record with real numeric sample and stage
                rate_val = s.get("rate_mm_hr")
                raw_ref_dict = {}
                try:
                    raw_ref_dict = json.loads(d.get("raw_reference") or "{}")
                except Exception:
                    pass
                raw_ref_dict.update({
                    "download_timestamp": utcnow_iso(),
                    "variable_path": s.get("variable_path", "Grid/precipitation"),
                    "units": s.get("units", "mm/hr"),
                    "quality_status": "PARSED_AND_SAMPLED",
                    "rate_mm_hr": rate_val,
                    "rainfall_30m": s.get("rainfall_30m"),
                    "grid_latitude": s.get("grid_latitude"),
                    "grid_longitude": s.get("grid_longitude"),
                    "is_test_location": s.get("is_test_location", False),
                })
                d_updated = {
                    **d,
                    "numeric_value": rate_val,
                    "stage": M.RASTER_SAMPLED,
                    "raw_reference": json.dumps(raw_ref_dict, sort_keys=True),
                }
                try:
                    repo.upsert_gpm_discovery(d_updated)
                except Exception:  # noqa: BLE001
                    pass

        self._sampled_count = sampled_total
        self._stage_notes.append(
            f"raster: {used} url(s) processed, {sampled_total} real value(s) stored"
        )
        res.stored += sampled_total

    def _store_sampled_rainfall(self, disc: dict, sample: dict) -> None:
        """Insert a REAL sampled mm accumulation as a rainfall observation."""
        accum_30m = sample.get("rainfall_30m")
        if accum_30m is None:
            return  # missing != zero — never fabricate

        r = {
            "source": "gpm",
            "ts": _observed_date_to_iso(disc.get("observed_date")) or utcnow_iso(),
            "latitude": sample["latitude"],
            "longitude": sample["longitude"],
            "rainfall_30m": accum_30m,
            "rainfall_3h": None,
            "rainfall_24h": None,
            "quality_flag": "GOOD",
            "resolution_m": GPM_RESOLUTION_M,
            "realtime_class": GPM_REALTIME_CLASS,
            "units": "mm",
            "granule_id": disc.get("item_id"),
        }
        repo.upsert_rainfall(r)

    def _sampling_points(self) -> list[dict]:
        """Returns points for spatial sampling.
        Prioritizes real administrative units.
        For technical integration test slice, includes target point clearly marked
        as a test location (never presented as a real village).
        """
        if self._villages is not None:
            return self._villages

        out = []
        # Filter real administrative units (not synthetic)
        for loc in repo.list_locations(level="village"):
            if not loc.get("is_synthetic") and loc.get("latitude") is not None and loc.get("longitude") is not None:
                out.append({
                    "location_id": loc["id"],
                    "location_name": loc["name"],
                    "latitude": loc["latitude"],
                    "longitude": loc["longitude"],
                    "is_test_location": False,
                })

        # For the first production slice / technical integration test, sample the target point
        # clearly marked as a test location (do not present it as a real village):
        if not out:
            out.append({
                "location_id": None,
                "location_name": "TEST_LOCATION_GPM_TARGET",
                "latitude": 30.06,
                "longitude": 78.06,
                "is_test_location": True,
            })
        return out

    def run(self, window: dict | None = None) -> StoreResult:
        """Execute run with honest status reporting:
        - successful CMR + download + parse + numeric data -> NRT
        - discovery-only (no numeric data sampled) -> DISCOVERY_ONLY / not NRT
        - failed download/parse -> ERROR
        - missing credential -> NOT_CONFIGURED
        """
        self._stage_notes = []
        self._sampled_count = 0
        t0 = time.time()
        started = utcnow_iso()

        if self.verified and not self.has_token():
            msg = (f"{self.auth_env_var} not set — GPM not configured; "
                   "staying on replay/discovery-only.")
            self._report_status_ext("NOT_CONFIGURED",
                                    int((time.time() - t0) * 1000),
                                    records=0, error=msg)
            self._log_ingestion(started, "not_configured", 0, 0, 0,
                                int((time.time() - t0) * 1000), msg)
            self._stage_notes.append("fetch: skipped (NOT_CONFIGURED — no token)")
            self._log_stage_notes()
            return StoreResult()

        try:
            res = super().run(window)
        except Exception as e:  # noqa: BLE001
            self._report_status_ext("ERROR", int((time.time() - t0) * 1000),
                                    records=0,
                                    error="; ".join(self._stage_notes) or str(e))
            self._log_stage_notes()
            raise

        # Status semantics:
        # successful CMR + download + parse + numeric data -> NRT
        # discovery-only -> not NRT
        latency_ms = int((time.time() - t0) * 1000)
        if self._sampled_count > 0:
            status = "NRT"
            success = True
        else:
            status = "DISCOVERY_ONLY"
            success = False

        self._report_status_ext(status, latency_ms, records=res.stored,
                                error=None if success else "discovery only; no numeric rainfall sampled",
                                success=success)
        self._log_stage_notes()
        return res

    def _report_status_ext(self, status: str, latency_ms: int, records: int,
                           error: str | None, success: bool = False) -> None:
        now = utcnow_iso()
        repo.record_source_health({
            "source": self.source_key, "status": status,
            "last_attempt_at": now,
            "last_success_at": now if success else None,
            "last_latency_ms": latency_ms, "last_error": error,
            "records_last_run": records, "updated_at": now,
        })

    def _log_stage_notes(self) -> None:
        for note in self._stage_notes:
            self._log_quality(note, table="gpm_discovery", flag="INFO")


class _NotConfigured(RuntimeError):
    """Raised when GPM is verified+enabled but no credential is configured."""


def _observed_date_to_iso(observed_date: str | None) -> str | None:
    if not observed_date:
        return None
    s = str(observed_date).strip()
    try:
        if len(s) == 8 and s.isdigit():
            return f"{s[0:4]}-{s[4:6]}-{s[6:8]}T00:00:00Z"
        from datetime import datetime, timezone
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:  # noqa: BLE001
        return None
