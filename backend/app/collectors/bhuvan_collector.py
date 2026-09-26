"""Bhuvan/NRSC bridge collector (Track B) — fifth verified external source.

Ties the vendored, ChatGPT-verified Bhuvan adapter
(app/data_layer/sources/bhuvan_nrsc) into this project's collector contract
(fetch -> validate -> normalize -> store), so source-health/ingestion logging,
the DAL seam and the API treat Bhuvan like any other collector.

WHY BHUVAN IS DIFFERENT (catalog-only, NOT discovery-only, NOT measurements):
Bhuvan/NRSC is a STATIC terrain/context source exposed as OGC WMS/WMTS layers
(CartoDEM, LULC, geomorphology, lineament, historical flood-hazard/annual). The
verified note (bhuvan_verified.md) is explicit on two points:
  1. "Do not scrape rendered map pixels as a substitute for the DEM." A WMS
     GetMap PNG is a picture, never a numeric elevation/slope value.
  2. Quantitative terrain must be derived from downloaded DEM tiles and
     preprocessed ONCE, then joined to villages — a stage the verified package
     does NOT implement.
So the honest integration is a CATALOG: we record the verified layer endpoints +
their roles in the `bhuvan_layers` table (stage='CATALOG_ONLY'), and that is all.
No numeric terrain value is ever produced here. The ML feature pipeline reads
terrain_features and NEVER reads bhuvan_layers, so a catalog row can never
masquerade as a numeric terrain feature. Real terrain values only enter
terrain_features after a future gated DEM-tile processing stage.

CONFIGURATION GATE (different again from GPM/SMAP token gate and MOSDAC base-URL
gate): the verified Bhuvan registry hard-codes the REAL public OGC endpoints
(bhuvan-vec2.nrsc.gov.in/bhuvan/wms etc), and cataloging needs no credentials, so
`verified=true` alone is enough to build the catalog from the vendored registry —
a pure, offline operation over verified static metadata. Therefore:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

Optionally, if an operator injects a `client` exposing get_capabilities(url), a
lightweight OGC GetCapabilities probe confirms endpoint reachability; a failed
probe is reported honestly (STALE) while the verified catalog rows are still
written (the endpoints themselves are verified static metadata, not invented).
httpx is imported lazily (Track B dep, absent in the sandbox), so importing this
module never breaks the Track A suite; a fake `client=` can be injected for tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import bhuvan_mapping as M
from app.database import repositories as repo


# Bhuvan is a STATIC public OGC service (terrain/context), not a real-time feed.
# We treat a successfully built catalog over verified live public endpoints as
# LIVE; there is no NRT/latency concept for static terrain layers.
BHUVAN_REALTIME_CLASS = "static"


class BhuvanCollector(BaseCollector):
    """Bridge collector for Bhuvan/NRSC OGC layer cataloging.

    Parameters come from the data_sources.yml `bhuvan` entry. `verified` gates
    the catalog exactly like the other collectors: it refuses to catalog unless
    the registry marks the source verified. No credentials are required — the
    verified registry endpoints are public and hard-coded, and cataloging is an
    offline operation over that verified static metadata.
    """

    source_key = "bhuvan"
    realtime_class = BHUVAN_REALTIME_CLASS

    def __init__(self, *, verified: bool, client: Any = None,
                 registry: dict | None = None):
        self.verified = verified
        # Optional client exposing get_capabilities(url) -> truthy on reach. In
        # production this stays None (pure catalog) unless an operator wires an
        # OGC probe. Injecting a fake here lets the probe path be unit-tested
        # with zero network. The vendored BhuvanWmsClient imports httpx at module
        # load, so it cannot even be imported in the portable sandbox.
        self._client = client
        # Optional explicit registry override (used by tests). In production this
        # stays None and fetch() reads the VENDORED, verified BHUVAN_LAYERS.
        self._registry = registry
        self._stage_notes: list[str] = []

    # ---- lifecycle ----
    def _load_registry(self) -> dict:
        """Return the verified BHUVAN_LAYERS registry. Reads the vendored,
        ChatGPT-verified registry module; never invents layers or endpoints."""
        if self._registry is not None:
            return self._registry
        from app.data_layer.sources.bhuvan_nrsc.sih_bhuvan.registry import (
            BHUVAN_LAYERS)
        return BHUVAN_LAYERS

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'bhuvan' is NOT verified in config/data_sources.yml — "
                "refusing to catalog (no invented endpoints/layers).")

        registry = self._load_registry()
        records = M.registry_to_catalog_records(registry,
                                                retrieved_at=utcnow_iso())
        self._stage_notes.append(
            f"catalog: {len(records)} verified layer endpoint(s) from "
            f"{len(registry)} registry entr(ies)")

        # Optional, honest liveness probe (never fabricated). Only if an operator
        # injected a client exposing get_capabilities(url); a failure is noted,
        # not invented away, and does not delete the verified catalog rows.
        self._probe_ok: bool | None = None
        if self._client is not None and hasattr(self._client, "get_capabilities"):
            self._probe_ok = self._probe_endpoints(records)

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "bhuvan_catalog"})

    def _probe_endpoints(self, records: list[dict]) -> bool:
        """Attempt an OGC GetCapabilities probe on each distinct verified
        endpoint. Returns True only if every probed endpoint responded; records
        the outcome in stage notes. Any exception is caught and reported as an
        unreachable endpoint — never suppressed into a false success."""
        urls = sorted({r.get("service_url") for r in records
                       if r.get("service_url")})
        all_ok = True
        for url in urls:
            try:
                ok = bool(self._client.get_capabilities(url))
            except Exception as exc:  # noqa: BLE001 — honest: probe failed
                ok = False
                self._stage_notes.append(f"probe: {url} unreachable ({exc})")
            if ok:
                self._stage_notes.append(f"probe: {url} reachable")
            else:
                all_ok = False
        return all_ok

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Catalog records are service-endpoint metadata, not measurements, so
        terrain sanity checks do not apply. We only require the honesty-critical
        shape: a layer_key and (for a usable catalog entry) a service_url. A
        record carrying anything that looks like a numeric measurement would be a
        bug — there is no such field in the catalog schema, so none can appear."""
        issues: list[Issue] = []
        for i, r in enumerate(raw.records):
            if not isinstance(r, dict):
                issues.append(Issue("BAD", "bhuvan catalog record is not an object", i))
                continue
            if not r.get("layer_key"):
                issues.append(Issue("BAD", "catalog record missing layer_key", i))
                continue
            if not r.get("service_url"):
                issues.append(Issue("WARNING",
                                    "catalog record has no service_url", i))
            if r.get("stage") != M.CATALOG_ONLY:
                issues.append(Issue("BAD",
                                    f"catalog record stage must be CATALOG_ONLY "
                                    f"(got {r.get('stage')!r})", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Catalog records are already in internal shape (produced by
        bhuvan_mapping from the verified registry). No numeric value exists to
        normalize; pass through unchanged."""
        return list(raw.records)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Catalog only: persist verified layer endpoints -> bhuvan_layers. There
        # is deliberately NO write to terrain_features here: the verified package
        # does not process DEM tiles, so we do not fabricate a terrain value.
        for d in records:
            try:
                repo.upsert_bhuvan_layer(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "dem-parse: skipped (no verified DEM-tile processor — catalog-only)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run. Cataloging the verified registry is an offline
        operation that succeeds whenever the source is verified, so on success we
        report LIVE (verified public OGC endpoints). If an optional endpoint probe
        was attempted and any endpoint was unreachable, we downgrade the health to
        STALE (the verified catalog rows are still written — the endpoints are
        verified static metadata, not invented). A genuine failure flows through
        base.run() and lands as ERROR."""
        self._stage_notes = []
        self._probe_ok = None
        t0 = time.time()

        try:
            res = super().run(window)
        except Exception:  # noqa: BLE001
            self._report_status_ext("ERROR", int((time.time() - t0) * 1000),
                                    records=0,
                                    error="; ".join(self._stage_notes) or None)
            self._log_stage_notes()
            raise

        # probe_ok is None when no probe was attempted (pure catalog) -> LIVE.
        # probe_ok False means at least one verified endpoint was unreachable.
        status = "STALE" if self._probe_ok is False else "LIVE"
        self._report_status_ext(status, int((time.time() - t0) * 1000),
                                 records=res.stored, error=None,
                                 success=(status == "LIVE"))
        self._log_stage_notes()
        return res

    def _report_status_ext(self, status: str, latency_ms: int, records: int,
                           error: str | None, success: bool = False) -> None:
        """Record an honest source_health row using the extended 7-state
        vocabulary, stored verbatim. last_success_at is only set on a genuine
        success (a fully reachable/verified catalog).

        force_success_ts=True is passed so this write OVERWRITES last_success_at
        rather than COALESCE-preserving it: BaseCollector.run() already recorded a
        within-run success timestamp during store(), but this call runs afterwards
        and must be able to DOWNGRADE that to STALE (probe unreachable) by clearing
        last_success_at. On a genuine LIVE success it simply rewrites the same
        timestamp."""
        now = utcnow_iso()
        repo.record_source_health({
            "source": self.source_key, "status": status,
            "last_attempt_at": now,
            "last_success_at": now if success else None,
            "last_latency_ms": latency_ms, "last_error": error,
            "records_last_run": records, "updated_at": now,
            "force_success_ts": True,
        })

    def _log_stage_notes(self) -> None:
        for note in self._stage_notes:
            self._log_quality(note, table="bhuvan_layers", flag="INFO")
