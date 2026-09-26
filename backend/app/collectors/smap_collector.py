"""
NASA SMAP bridge collector (Track B) — second verified external source.

Ties the vendored, ChatGPT-verified SMAP CMR discovery adapter
(app/data_layer/sources/smap) into this project's collector contract
(fetch -> validate -> normalize -> store), so everything downstream
(source-health/ingestion logging, the DAL seam, the API) treats SMAP like any
other collector — exactly as GpmCollector does for GPM.

Design (mirrors the approved GPM two-stage model, honesty rules unchanged):

  Stage 1 — DISCOVERY (always):
    NASA CMR granule search -> granule metadata + documented GET DATA URLs ->
    smap_discovery table. surface_sm / rootzone_sm stay NULL. This NEVER enters
    soil_moisture_observations, so a discovery record can never masquerade as a
    numeric soil-moisture value in the ML feature pipeline.

  Stage 2 — RAW PARSE (NOT IMPLEMENTED YET, honestly):
    The verified SMAP package implements discovery/normalization ONLY. Turning a
    granule into real m3/m3 values requires downloading the HDF5/NetCDF product
    and parsing documented variables/quality flags — that parser is not part of
    the verified package, so we DO NOT fake it. Until such a verified parser
    exists, SMAP is discovery-only and writes zero soil-moisture measurements.
    (smap_verified.md: "Do not treat CMR metadata, footprint polygons, or
    filenames as numeric soil-moisture measurements.")

Honest source status (unchanged 7-state model — LIVE/NRT/STALE/ERROR/
NOT_CONFIGURED/REPLAY/SIMULATED): decided by what actually happened at runtime,
never asserted. No usable token -> NOT_CONFIGURED. Fetch failed -> ERROR.
Successful discovery -> NRT (SMAP L4 is a near-real-time product with hours of
latency; there is no zero-latency "LIVE" SMAP). "DISCOVERY_ONLY" is an
OBSERVATION-STAGE flag on the record, not a health status.

Replay remains the known-good default: this collector is only invoked when SMAP
is verified+enabled in data_sources.yml AND a usable token is present; otherwise
the app keeps running on replay untouched.

httpx/pydantic are imported lazily (Track B deps, absent in the portable
sandbox), so importing this module never breaks the Track A test suite. A fake
discovery object can be injected via `discovery=` for zero-network unit tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import smap_mapping as M
from app.database import repositories as repo


# SMAP L4 is a near-real-time product (3-hourly, with processing latency per
# app/data_layer/sources/smap/docs/smap_verified.md). There is no "LIVE" SMAP.
SMAP_REALTIME_CLASS = "near_real_time"


class SmapCollector(BaseCollector):
    """Bridge collector for NASA SMAP L4 soil moisture via the CMR granule API.

    Parameters come from the data_sources.yml `smap` entry. `verified` gates the
    fetch exactly like GpmCollector/HttpSourceCollector: it refuses to call out
    unless the registry marks the source verified.
    """

    source_key = "smap"
    realtime_class = SMAP_REALTIME_CLASS

    def __init__(self, *, verified: bool,
                 auth_env_var: str | None = "EARTHDATA_TOKEN",
                 short_name: str = "SPL4SMAU", version: str = "008",
                 grid: str = "9 km EASE-Grid", limit: int = 10,
                 client: Any = None, discovery: Any = None):
        self.verified = verified
        self.auth_env_var = auth_env_var
        self.short_name = short_name
        self.version = version
        self.grid = grid
        self.limit = limit
        self._client = client
        # Optional pre-built discovery object exposing `.search_granules(**kw)`
        # and returning a list of objects/dicts with the SmapGranule attributes.
        # In production this stays None and fetch() lazily builds the vendored,
        # ChatGPT-verified SmapCollector (which needs httpx). Injecting a fake
        # here lets the discovery path be unit-tested with zero network and zero
        # Track B deps — the vendored collector imports httpx at module load, so
        # it cannot even be imported in the portable sandbox.
        self._discovery = discovery
        # per-run stage bookkeeping surfaced through ingestion/quality logs
        self._stage_notes: list[str] = []

    # ---- credential handling (never hard-coded) ----
    # Note: SMAP CMR granule *discovery* is often anonymous; a token is required
    # for protected downloads. We keep the same gate as GPM so an operator can
    # decide (via the yaml auth model) that SMAP is only "configured" when a
    # usable token is present — this keeps behaviour honest and consistent, and
    # makes NOT_CONFIGURED verifiable exactly like GPM. Placeholder values are
    # treated as absent so a template .env never fakes a credential.
    _PLACEHOLDER_TOKENS = frozenset({
        "", "changeme", "change_me", "your_token_here", "your-token-here",
        "yourtoken", "token", "todo", "tbd", "xxx", "xxxx", "placeholder",
        "none", "null", "na", "n/a", "replace_me", "replace-me",
        "nasa_earthdata_token", "earthdata_token", "<token>", "<your_token>",
        "example", "dummy", "test", "fixme",
    })

    def _token(self) -> str | None:
        """Return the Earthdata token ONLY if it looks genuinely usable.
        Whitespace-only and well-known placeholder values are treated as absent
        so SMAP reports NOT_CONFIGURED rather than pretending to have a
        credential. Never hard-codes or logs the token value itself."""
        import os
        if not self.auth_env_var:
            return None
        raw = os.environ.get(self.auth_env_var)
        if raw is None:
            return None
        val = raw.strip()
        if not val:
            return None
        if val.lower() in self._PLACEHOLDER_TOKENS:
            return None
        return val

    def has_token(self) -> bool:
        return bool(self._token())

    # ---- lifecycle ----
    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'smap' is NOT verified in config/data_sources.yml — "
                "refusing to fetch (no invented endpoints/credentials).")
        if not self.has_token():
            raise _NotConfigured(
                f"{self.auth_env_var} not set — SMAP not configured; "
                "staying on replay/discovery-only.")

        collector = self._discovery
        if collector is None:
            # Lazy import: the vendored verified collector needs httpx (Track B
            # dep). Only reached in production; never in the portable sandbox.
            from app.data_layer.sources.smap.sih_smap.collector import (
                SmapCollector as VendoredSmapCollector)
            from app.data_layer.sources.smap.sih_smap.config import SmapConfig
            cfg = SmapConfig(short_name=self.short_name, version=self.version)
            collector = VendoredSmapCollector(config=cfg, client=self._client)

        w = window or {}
        granules = collector.search_granules(
            start=w.get("start"),
            end=w.get("end"),
            point=w.get("point"),
            bounding_box=w.get("bounding_box"),
            page_size=w.get("limit", self.limit),
        )
        dicts = [self._granule_to_dict(g) for g in (granules or [])]
        self._stage_notes.append(f"discovery: {len(dicts)} granule(s)")
        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=dicts, meta={"payload_kind": "cmr_granules"})

    @staticmethod
    def _granule_to_dict(g: Any) -> dict:
        """Convert a vendored SmapGranule (pydantic) OR a plain dict into the
        plain-dict shape smap_mapping expects. Keeps smap_mapping free of any
        pydantic/httpx dependency so it stays sandbox-provable."""
        if isinstance(g, dict):
            return g
        get = lambda name: getattr(g, name, None)  # noqa: E731
        return {
            "concept_id": get("concept_id"),
            "producer_granule_id": get("producer_granule_id"),
            "title": get("title"),
            "start_time": get("start_time"),
            "end_time": get("end_time"),
            "downloadable_urls": list(get("downloadable_urls") or []),
        }

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Discovery granules are metadata, not soil-moisture records, so the
        soil-moisture sanity checks do not apply. We only require a parseable
        granule shape; a malformed granule is dropped (BAD) rather than guessed
        at, and one without a concept_id or any download URL is flagged."""
        issues: list[Issue] = []
        for i, g in enumerate(raw.records):
            if not isinstance(g, dict):
                issues.append(Issue("BAD", "CMR granule is not an object", i))
                continue
            if not g.get("concept_id") and not g.get("downloadable_urls"):
                issues.append(Issue("WARNING",
                                    "granule has neither concept_id nor download URL", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Map CMR granules -> internal smap_discovery record dicts. surface_sm /
        rootzone_sm are None for every record here (discovery stage). No raw
        parse stage exists yet, so no soil-moisture value is ever produced."""
        return M.granules_to_discovery_records(
            raw.records, version=self.version, grid=self.grid,
            retrieved_at=raw.fetched_at)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Stage 1 only: persist discovery records (surface_sm/rootzone_sm NULL) —
        # never to soil_moisture_observations. There is deliberately NO stage 2
        # here: the verified package does not parse the scientific product, so we
        # do not fabricate a measurement.
        for d in records:
            try:
                repo.upsert_smap_discovery(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "parse: skipped (no verified HDF5/NetCDF parser — discovery-only)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run to translate a missing credential into an
        explicit NOT_CONFIGURED health state (not an error), and to persist the
        per-stage notes. Successful discovery reports NRT. Mirrors GpmCollector.

        The not-configured case is short-circuited BEFORE super().run() so we
        never emit a spurious error health row or a duplicate ingestion log. A
        genuine fetch failure still flows through base.run() and lands as ERROR."""
        self._stage_notes = []
        t0 = time.time()
        started = utcnow_iso()

        if self.verified and not self.has_token():
            msg = (f"{self.auth_env_var} not set — SMAP not configured; "
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
            self._log_quality(note, table="smap_discovery", flag="INFO")


class _NotConfigured(RuntimeError):
    """Raised when SMAP is verified but no usable credential is configured.
    Distinct from an error: the app simply stays on replay/discovery-only."""
