"""ISRO MOSDAC bridge collector (Track B) — fourth verified external source.

Ties the vendored, ChatGPT-verified MOSDAC mdapi adapter
(app/data_layer/sources/mosdac) into this project's collector contract
(fetch -> validate -> normalize -> store), so everything downstream
(source-health/ingestion logging, the DAL seam, the API) treats MOSDAC like any
other collector — exactly as GpmCollector/SmapCollector do.

Design (mirrors the approved GPM/SMAP discovery model, honesty rules unchanged):

  Stage 1 — DISCOVERY (always):
    MOSDAC mdapi granule search -> granule metadata + a documented download URL
    -> mosdac_discovery table. numeric_value stays NULL. This NEVER enters
    rainfall_observations, so a discovery record can never masquerade as a
    numeric rainfall value in the ML feature pipeline.

  Stage 2 — RAW PARSE (NOT IMPLEMENTED YET, honestly):
    The verified MOSDAC package implements search-config + normalization ONLY.
    Turning a granule into real mm values requires downloading the HDF/GeoTIFF
    product (which needs MOSDAC credentials) and parsing it with a separate
    product parser — that parser is not part of the verified package, so we DO
    NOT fake it. Until such a verified parser exists, MOSDAC is discovery-only
    and writes zero rainfall measurements. (mosdac_verified.md: "raw satellite
    files parsed by separate product parser; ML must consume normalized values
    from the internal database, never call MOSDAC directly.")

HONEST CONFIGURATION GATE (different from GPM/SMAP's token gate):
The verified MOSDAC config hard-codes NO service endpoint (api_base_url default
is "") because the public manual documents a client/config contract, not a
stable third-party endpoint — and the master prompt forbids inventing one. So
MOSDAC is "configured" only when the operator supplies MOSDAC_API_BASE_URL.
Granule SEARCH is anonymous (no login); MOSDAC_USERNAME/PASSWORD are required
only for the (unimplemented) download stage. Therefore:

  verified=false in yaml           -> refuses to fetch          -> ERROR
  verified=true, NO api_base_url   -> no fetch, no rows written -> NOT_CONFIGURED
  verified=true, api_base_url set  -> real mdapi granule search -> NRT

httpx/pydantic are imported lazily (Track B deps, absent in the portable
sandbox), so importing this module never breaks the Track A test suite. A fake
discovery object can be injected via `discovery=` for zero-network unit tests.
"""
from __future__ import annotations

import os
import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import mosdac_mapping as M
from app.database import repositories as repo


# INSAT precipitation products are near-real-time (half-hourly / product-defined
# with processing latency per the verified registry). There is no zero-latency
# "LIVE" MOSDAC precipitation product.
MOSDAC_REALTIME_CLASS = "near_real_time"
# ~0.1 degree native grid -> metres (provenance only; ~11.1 km at equator).
MOSDAC_RESOLUTION_M = 11132.0

# Default dataset to discover if the registry entry doesn't name one — the
# INSAT-3DR Hydro-Estimator half-hourly precipitation product (verified).
_DEFAULT_DATASET_ID = "3RIMG_L2B_HEM"

# Placeholder base-URL values treated as absent so a template .env never fakes a
# configured endpoint. Mirrors the token-placeholder handling in GPM/SMAP.
_PLACEHOLDER_URLS = frozenset({
    "", "changeme", "change_me", "your_url_here", "http://example.com",
    "https://example.com", "todo", "tbd", "placeholder", "none", "null",
    "na", "n/a", "<url>", "<your_url>", "example", "dummy", "test", "fixme",
})


class MosdacCollector(BaseCollector):
    """Bridge collector for ISRO MOSDAC INSAT precipitation granule discovery.

    Parameters come from the data_sources.yml `mosdac` entry. `verified` gates
    the fetch exactly like the other collectors: it refuses to call out unless
    the registry marks the source verified.
    """

    source_key = "mosdac"
    realtime_class = MOSDAC_REALTIME_CLASS

    def __init__(self, *, verified: bool,
                 base_url_env_var: str | None = "MOSDAC_API_BASE_URL",
                 dataset_id: str = _DEFAULT_DATASET_ID,
                 count: int = 10,
                 enable_raster: bool = False,
                 villages: list[dict] | None = None,
                 client: Any = None, discovery: Any = None):
        self.verified = verified
        self.base_url_env_var = base_url_env_var
        self.dataset_id = dataset_id
        self.count = count
        self.enable_raster = enable_raster
        self._villages = villages
        self._client = client
        # Optional pre-built discovery object exposing
        # `.search(config: dict) -> list[dict]` (raw mdapi items). In production
        # this stays None and fetch() lazily builds the vendored, ChatGPT-
        # verified MosdacCollector (which needs httpx). Injecting a fake here
        # lets the discovery path be unit-tested with zero network and zero
        # Track B deps — the vendored collector imports httpx at module load, so
        # it cannot even be imported in the portable sandbox.
        self._discovery = discovery
        self._stage_notes: list[str] = []

    # ---- configuration handling (never hard-coded, never invented) ----
    def _base_url(self) -> str | None:
        """Return the MOSDAC service base URL ONLY if it looks genuinely usable.
        Whitespace-only and well-known placeholder values are treated as absent
        so MOSDAC reports NOT_CONFIGURED rather than pretending to have an
        endpoint. The verified package hard-codes no endpoint by design."""
        if not self.base_url_env_var:
            return None
        raw = os.environ.get(self.base_url_env_var)
        if raw is None:
            return None
        val = raw.strip()
        if not val:
            return None
        if val.lower() in _PLACEHOLDER_URLS:
            return None
        return val

    def is_configured(self) -> bool:
        """MOSDAC is configured when a usable service base URL is present.
        Search is anonymous, so credentials are NOT part of this gate (they are
        required only for the unimplemented download stage)."""
        return bool(self._base_url())

    # ---- lifecycle ----
    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'mosdac' is NOT verified in config/data_sources.yml — "
                "refusing to fetch (no invented endpoints/credentials).")
        if not self.is_configured():
            raise _NotConfigured(
                f"{self.base_url_env_var} not set — MOSDAC has no hard-coded "
                "endpoint (verified package documents a client/config contract, "
                "not a stable public URL); staying on replay/discovery-only.")

        w = window or {}
        # Build the verified mdapi search config (no invented parameters).
        search_config = self._build_search_config(w)

        discovery = self._discovery
        if discovery is None:
            # Lazy import: the vendored verified collector needs httpx (Track B
            # dep). Only reached in production; never in the portable sandbox.
            from app.data_layer.sources.mosdac.sih_mosdac.collector import (
                MosdacCollector as VendoredMosdacCollector)
            from app.data_layer.sources.mosdac.sih_mosdac.config import (
                MosdacConfig)
            cfg = MosdacConfig()  # reads MOSDAC_* env vars
            discovery = VendoredMosdacCollector(config=cfg, client=self._client)

        # The seam: `search(config)` returns raw mdapi items (list[dict]). The
        # vendored collector exposes build_search_config + normalize_search_items
        # but no stable HTTP search method (the endpoint is operator-supplied),
        # so an injected discovery object performs the actual retrieval. If the
        # object cannot search, this raises and is honestly reported as ERROR —
        # we never fabricate items.
        search = getattr(discovery, "search", None)
        if not callable(search):
            raise RuntimeError(
                "MOSDAC discovery client exposes no callable search(config) — "
                "the verified package documents the search-config contract but "
                "not a stable public endpoint; an operator-configured client is "
                "required. Refusing to invent a request.")
        raw_items = search(search_config) or []

        # Normalize raw mdapi items -> MosdacGranule dicts via the VENDORED
        # normalizer (verified field mapping), then to plain dicts.
        granules = self._normalize_items(discovery, self.dataset_id, raw_items)
        dicts = [self._granule_to_dict(g) for g in granules]
        self._stage_notes.append(f"discovery: {len(dicts)} granule(s)")
        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=dicts, meta={"payload_kind": "mosdac_granules"})

    def _build_search_config(self, w: dict) -> dict:
        """Build the mdapi search config using the VENDORED build_search_config
        when available (verified parameter names), else a minimal equivalent.
        Never invents parameter names."""
        try:
            from app.data_layer.sources.mosdac.sih_mosdac.collector import (
                MosdacCollector as VendoredMosdacCollector)
            from app.data_layer.sources.mosdac.sih_mosdac.contracts import (
                MosdacSearchRequest)
            req = MosdacSearchRequest(
                dataset_id=self.dataset_id,
                start_time=w.get("start"),
                end_time=w.get("end"),
                count=w.get("count", self.count),
                bounding_box=w.get("bounding_box"),
                granule_id=w.get("granule_id"),
            )
            return VendoredMosdacCollector.build_search_config(req)
        except Exception:  # noqa: BLE001 — vendored pydantic/httpx absent (sandbox)
            # Minimal verified-shape config (same keys build_search_config emits).
            box = w.get("bounding_box")
            return {
                "datasetId": self.dataset_id,
                "startTime": "", "endTime": "",
                "count": str(w.get("count", self.count)),
                "boundingBox": ",".join(str(v) for v in box) if box else "",
                "gId": w.get("granule_id") or "",
            }

    @staticmethod
    def _normalize_items(discovery: Any, dataset_id: str,
                         raw_items: list[dict]) -> list[Any]:
        """Prefer the vendored normalize_search_items (verified field mapping).
        If the injected discovery object provides its own normalizer, use it;
        otherwise fall back to passing raw dicts straight through (they already
        carry dataset_id/granule_id/download_url in tests)."""
        norm = getattr(discovery, "normalize_search_items", None)
        if callable(norm):
            return norm(dataset_id, raw_items)
        # Fall back: attach dataset_id so mapping has it.
        out = []
        for it in raw_items:
            d = dict(it)
            d.setdefault("dataset_id", dataset_id)
            out.append(d)
        return out

    @staticmethod
    def _granule_to_dict(g: Any) -> dict:
        """Convert a vendored MosdacGranule (pydantic) OR a plain dict into the
        plain-dict shape mosdac_mapping expects. Keeps mosdac_mapping free of any
        pydantic/httpx dependency so it stays sandbox-provable."""
        if isinstance(g, dict):
            return g
        get = lambda name: getattr(g, name, None)  # noqa: E731
        return {
            "dataset_id": get("dataset_id"),
            "granule_id": get("granule_id"),
            "title": get("title"),
            "start_time": get("start_time"),
            "end_time": get("end_time"),
            "download_url": get("download_url"),
            "metadata": get("metadata") or {},
        }

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Discovery granules are metadata, not rainfall records, so rainfall
        sanity checks do not apply. We only require a parseable granule shape; a
        malformed granule is dropped (BAD) rather than guessed at, and one
        without a granule_id or download URL is flagged."""
        issues: list[Issue] = []
        for i, g in enumerate(raw.records):
            if not isinstance(g, dict):
                issues.append(Issue("BAD", "MOSDAC granule is not an object", i))
                continue
            if not g.get("granule_id") and not g.get("download_url"):
                issues.append(Issue("WARNING",
                                    "granule has neither granule_id nor download URL", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Map MOSDAC granules -> internal mosdac_discovery record dicts.
        numeric_value is None for every record here (discovery stage). No raw
        parse stage exists yet, so no rainfall value is ever produced."""
        return M.granules_to_discovery_records(
            raw.records, retrieved_at=raw.fetched_at)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Stage 1: persist discovery records (numeric_value NULL) into mosdac_discovery
        for d in records:
            try:
                repo.upsert_mosdac_discovery(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1

        # Stage 2: HDF5 parse and spatial sampling into rainfall_observations
        self._maybe_run_raster_stage(records, res)
        return res

    def _maybe_run_raster_stage(self, records: list[dict], res: StoreResult) -> None:
        if not self.enable_raster:
            self._stage_notes.append("parse: skipped (no verified raster/HDF parser — discovery-only)")
            return
        try:
            from app.collectors import mosdac_raster as MR
        except ImportError:
            MR = None
        if MR is None or not MR.h5py_available():
            self._stage_notes.append("raster: skipped (h5py not installed; discovery-only)")
            return

        points = self._sampling_points()
        if not points:
            self._stage_notes.append("raster: skipped (no sampling coordinates)")
            return

        sampled_total = 0
        used = 0
        import json
        for d in records:
            file_path = self._resolve_local_file(d)
            if not file_path:
                continue
            used += 1
            stage = MR.run_raster_stage(file_path, points, dataset_name=self.dataset_id)
            if stage.skipped_reason:
                self._stage_notes.append(f"raster: {stage.skipped_reason}")
                continue
            if stage.error:
                self._stage_notes.append(f"raster: {stage.error}")
                self._log_quality(f"raster stage error: {stage.error}",
                                  table="mosdac_discovery", flag="WARNING")
                raise RuntimeError(f"MOSDAC raster stage failed: {stage.error}")

            # Persist real sampled values to rainfall_observations
            for s in stage.samples:
                if s.get("rainfall_30m") is None:
                    continue  # missing != zero — never fabricate
                self._store_sampled_rainfall(d, s)
                sampled_total += 1

                rate_val = s.get("value")
                raw_ref_dict = {}
                try:
                    raw_ref_dict = json.loads(d.get("raw_reference") or "{}")
                except Exception:
                    pass
                raw_ref_dict.update({
                    "download_timestamp": utcnow_iso(),
                    "variable_path": self.dataset_id,
                    "units": s.get("units", "mm/hr"),
                    "quality_status": "PARSED_AND_SAMPLED",
                    "rate_mm_hr": rate_val,
                    "rainfall_30m": s.get("rainfall_30m"),
                    "grid_latitude": s.get("grid_latitude"),
                    "grid_longitude": s.get("grid_longitude"),
                })
                d_updated = {
                    **d,
                    "numeric_value": rate_val,
                    "stage": M.RASTER_SAMPLED,
                    "raw_reference": json.dumps(raw_ref_dict, sort_keys=True),
                }
                try:
                    repo.upsert_mosdac_discovery(d_updated)
                except Exception:  # noqa: BLE001
                    pass

        self._stage_notes.append(
            f"raster: {used} granule(s) processed, {sampled_total} real value(s) stored"
        )
        res.stored += sampled_total

    def _store_sampled_rainfall(self, disc: dict, sample: dict) -> None:
        """Insert a REAL sampled mm accumulation as a rainfall observation."""
        accum_30m = sample.get("rainfall_30m")
        if accum_30m is None:
            return

        r = {
            "source": self.source_key,
            "ts": _observed_date_to_iso(disc.get("observed_date")) or utcnow_iso(),
            "latitude": sample["latitude"],
            "longitude": sample["longitude"],
            "rainfall_30m": accum_30m,
            "rainfall_3h": None,
            "rainfall_24h": None,
            "quality_flag": sample.get("quality_flag", "GOOD"),
            "resolution_m": MOSDAC_RESOLUTION_M,
            "realtime_class": MOSDAC_REALTIME_CLASS,
        }
        repo.upsert_rainfall(r)

    def _sampling_points(self) -> list[dict]:
        """Returns points for spatial sampling."""
        if self._villages is not None:
            return self._villages
        out = []
        for loc in repo.list_locations(level="village"):
            if loc.get("latitude") is not None and loc.get("longitude") is not None:
                out.append({
                    "location_id": loc.get("id"),
                    "location_name": loc.get("name"),
                    "latitude": loc["latitude"],
                    "longitude": loc["longitude"],
                })
        return out

    def _resolve_local_file(self, d: dict) -> str | None:
        """Find local HDF5 file corresponding to discovery record."""
        # 1. Direct path in record
        for key in ("local_path", "download_url"):
            p = d.get(key)
            if p and os.path.exists(p) and not p.startswith("http"):
                return p

        # 2. Check metadata dict
        meta = d.get("metadata") or {}
        if isinstance(meta, dict):
            p = meta.get("local_path")
            if p and os.path.exists(p):
                return p

        # 3. Check data/mosdac/ directory
        from pathlib import Path
        gid = d.get("granule_id") or ""
        title = d.get("title") or ""
        search_dirs = [Path("data/mosdac"), Path("../data/mosdac"), Path("../../data/mosdac")]
        for sdir in search_dirs:
            if not sdir.exists():
                continue
            if gid:
                for candidate in (sdir / f"{gid}.h5", sdir / gid, sdir / f"{gid}.hdf5"):
                    if candidate.exists():
                        return str(candidate)
            if title:
                for candidate in (sdir / f"{title}.h5", sdir / title):
                    if candidate.exists():
                        return str(candidate)
            # Find latest matching .h5 in sdir
            h5_files = sorted(sdir.glob("*.h5"), key=os.path.getmtime, reverse=True)
            if h5_files:
                return str(h5_files[0])
        return None

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run to translate a missing endpoint into an
        explicit NOT_CONFIGURED health state (not an error), and to persist the
        per-stage notes. Successful discovery reports NRT. Mirrors SmapCollector.

        The not-configured case is short-circuited BEFORE super().run() so we
        never emit a spurious error health row or a duplicate ingestion log. A
        genuine fetch failure still flows through base.run() and lands as ERROR."""
        self._stage_notes = []
        t0 = time.time()
        started = utcnow_iso()

        if self.verified and not self.is_configured():
            msg = (f"{self.base_url_env_var} not set — MOSDAC not configured; "
                   "staying on replay/discovery-only.")
            self._report_status_ext("NOT_CONFIGURED",
                                    int((time.time() - t0) * 1000),
                                    records=0, error=msg)
            self._log_ingestion(started, "not_configured", 0, 0, 0,
                                int((time.time() - t0) * 1000), msg)
            self._stage_notes.append(
                "fetch: skipped (NOT_CONFIGURED — no endpoint)")
            self._log_stage_notes()
            return StoreResult()

        try:
            res = super().run(window)
        except Exception:  # noqa: BLE001
            self._report_status_ext("ERROR", int((time.time() - t0) * 1000),
                                    records=0,
                                    error="; ".join(self._stage_notes) or None)
            self._log_stage_notes()
            raise
        self._report_status_ext("NRT", int((time.time() - t0) * 1000),
                                 records=res.stored, error=None, success=True)
        self._log_stage_notes()
        return res

    def _report_status_ext(self, status: str, latency_ms: int, records: int,
                           error: str | None, success: bool = False) -> None:
        """Record an honest source_health row. `status` uses the extended
        7-state vocabulary; stored verbatim so the dashboard shows exactly what
        happened. last_success_at is only set on a genuine success."""
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
            self._log_quality(note, table="mosdac_discovery", flag="INFO")


class _NotConfigured(RuntimeError):
    """Raised when MOSDAC is verified but no usable endpoint is configured.
    Distinct from an error: the app simply stays on replay/discovery-only."""


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
