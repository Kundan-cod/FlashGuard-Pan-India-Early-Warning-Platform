"""CWC / NWIC bridge collector (Track B) — seventh verified external source.

Ties the vendored, ChatGPT-verified CWC/NWIC adapter
(app/data_layer/sources/cwc_nwic) into this project's collector contract
(fetch -> validate -> normalize -> store), so source-health/ingestion logging,
the DAL seam and the API treat CWC like any other collector.

WHY CWC/NWIC IS CATALOG-ONLY (NOT a numeric hydrological feed):
CWC/NWIC hydrology (river water level, telemetry rainfall, reservoir storage) is
exposed through the public National Water Data Portal (NWDP), which advertises
CSV/API as data formats. The verified note (cwc_nwic_verified.md) is explicit:
  1. "This package intentionally does not invent an undocumented API URL." The
     public NWDP dataset pages are the verified entry point; CSV/API resource
     links are DISCOVERED from those pages, not fabricated. So we NEVER invent a
     station reading or an API endpoint.
  2. The portal advertises API as a data format, but "the exact API endpoint/auth
     contract was not verified in this pass", and we must "not claim that every
     station is live or that every API is anonymous." So a clean adapter boundary
     is kept: a future authenticated/live parse stage is separate.
So the honest integration is a CATALOG: we record the verified NWDP dataset pages
+ their roles + advertised formats + cadence in the `cwc_resources` table
(stage='CATALOG_ONLY'), and that is all. No numeric river-level/rainfall value is
ever produced here. The ML feature pipeline reads river_observations /
rainfall_observations and NEVER reads cwc_resources, so a catalog row can never
masquerade as a hydrological value. Real CWC values only enter after a future
gated, verified CSV/API parse of a specific dataset resource.

CONFIGURATION GATE (same shape as Bhuvan's/GSI's catalog gate): the verified
config hard-codes the REAL public portal (https://www.nwdp.nwic.gov.in) and
cataloging the dataset pages needs no credentials, so `verified=true` alone is
enough to build the catalog — a pure, offline operation over verified static
metadata. Therefore:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

Optionally, if an operator injects a `client` exposing fetch_dataset_page() (the
vendored NwdpClient), a lightweight portal-reachability probe confirms the NWDP
dataset page responds; a failed probe is reported honestly (STALE) while the
verified catalog rows are still written (the dataset pages themselves are verified
static metadata, not invented). httpx is imported lazily (Track B dep, absent in
the sandbox), so importing this module never breaks the Track A suite; a fake
`client=` can be injected for tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import cwc_mapping as M
from app.database import repositories as repo


# CWC/NWIC dataset pages are static catalog context, not a real-time feed at the
# CATALOG stage. We treat a successfully built catalog over the verified live
# public portal as LIVE; there is no NRT/latency concept for the catalog itself
# (the underlying telemetry is hourly, but that is a future gated parse stage).
CWC_REALTIME_CLASS = "static_periodic"


class CwcCollector(BaseCollector):
    """Bridge collector for CWC/NWIC NWDP dataset-page cataloging.

    Parameters come from the data_sources.yml `cwc` entry. `verified` gates the
    catalog exactly like the other catalog collectors: it refuses to catalog
    unless the registry marks the source verified. No credentials are required —
    the verified NWDP portal is public and hard-coded, and cataloging is an
    offline operation over that verified static metadata.
    """

    source_key = "cwc"
    realtime_class = CWC_REALTIME_CLASS

    def __init__(self, *, verified: bool, client: Any = None,
                 registry: dict | None = None,
                 base_url: str | None = None):
        self.verified = verified
        # Optional client exposing fetch_dataset_page(path) -> str (the vendored
        # NwdpClient). In production this stays None (pure catalog) unless an
        # operator wires a portal probe. Injecting a fake here lets the probe path
        # be unit-tested with zero network. The vendored client imports httpx at
        # module load, so it cannot be imported in the portable sandbox.
        self._client = client
        # Optional explicit registry override (used by tests). In production this
        # stays None and fetch() reads the VENDORED, verified CWC_NWIC_DATASETS.
        self._registry = registry
        # Optional NWDP base_url override. None -> the verified vendored default.
        self._base_url = base_url
        self._stage_notes: list[str] = []

    # ---- lifecycle ----
    def _load_registry(self) -> dict:
        """Return the verified CWC_NWIC_DATASETS registry. Reads the vendored,
        ChatGPT-verified registry module; never invents datasets or endpoints."""
        if self._registry is not None:
            return self._registry
        from app.data_layer.sources.cwc_nwic.sih_cwc.registry import (
            CWC_NWIC_DATASETS)
        return CWC_NWIC_DATASETS

    def _resolve_base_url(self) -> str:
        """Return the NWDP base URL to catalog against. Prefers an explicit
        override, else the vendored verified NwicConfig default; falls back to the
        mapping module constant if the config import is unavailable (sandbox)."""
        if self._base_url:
            return self._base_url
        try:
            from app.data_layer.sources.cwc_nwic.sih_cwc.config import NwicConfig
            return NwicConfig().base_url
        except Exception:  # noqa: BLE001 — sandbox has no vendored deps loaded
            return M.DEFAULT_NWDP_BASE_URL

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'cwc' is NOT verified in config/data_sources.yml — "
                "refusing to catalog (no invented endpoints/datasets).")

        registry = self._load_registry()
        base_url = self._resolve_base_url()
        records = M.registry_to_catalog_records(registry, base_url=base_url,
                                                retrieved_at=utcnow_iso())
        self._stage_notes.append(
            f"catalog: {len(records)} verified NWDP dataset page(s) from "
            f"{len(registry)} registry entr(ies) at {base_url}")

        # Optional, honest liveness probe (never fabricated). Only if an operator
        # injected a client exposing fetch_dataset_page(); a failure is noted, not
        # invented away, and does not delete the verified catalog rows. We probe
        # the FIRST cataloged dataset page as a representative reachability check.
        self._probe_ok: bool | None = None
        if self._client is not None and hasattr(self._client,
                                                 "fetch_dataset_page"):
            first_path = next((e.get("path") for e in registry.values()
                               if e.get("path")), None)
            self._probe_ok = self._probe_page(first_path)

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "cwc_catalog"})

    def _probe_page(self, path: str | None) -> bool:
        """Attempt to fetch a verified NWDP dataset page. Returns True only if the
        page responded with some content; records the outcome in stage notes. Any
        exception is caught and reported as unreachable — never suppressed into a
        false success. This reads only the public dataset-page HTML; it does NOT
        parse any CSV/API resource into a numeric value."""
        if not path:
            self._stage_notes.append("probe: no dataset path to probe — skipped")
            return False
        try:
            html = self._client.fetch_dataset_page(path)
        except Exception as exc:  # noqa: BLE001 — honest: portal unreachable
            self._stage_notes.append(f"probe: NWDP dataset page unreachable ({exc})")
            return False
        ok = bool(html)
        self._stage_notes.append(
            "probe: NWDP dataset page reachable" if ok
            else "probe: NWDP dataset page returned empty response")
        return ok

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Catalog records are dataset-page metadata, not measurements, so
        hydrological sanity checks do not apply. We only require the honesty-
        critical shape: a dataset_key and (for a usable catalog entry) a
        dataset_url. A record carrying anything that looks like a numeric water
        level or rainfall would be a bug — there is no such field in the catalog
        schema, so none can appear."""
        issues: list[Issue] = []
        for i, r in enumerate(raw.records):
            if not isinstance(r, dict):
                issues.append(Issue("BAD", "cwc catalog record is not an object", i))
                continue
            if not r.get("dataset_key"):
                issues.append(Issue("BAD", "catalog record missing dataset_key", i))
                continue
            if not r.get("dataset_url"):
                issues.append(Issue("WARNING",
                                    "catalog record has no dataset_url", i))
            if r.get("stage") != M.CATALOG_ONLY:
                issues.append(Issue("BAD",
                                    f"catalog record stage must be CATALOG_ONLY "
                                    f"(got {r.get('stage')!r})", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Catalog records are already in internal shape (produced by cwc_mapping
        from the verified registry). No numeric value exists to normalize; pass
        through unchanged."""
        return list(raw.records)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Catalog only: persist verified NWDP dataset pages -> cwc_resources.
        # There is deliberately NO write to river_observations/rainfall_observations
        # here: the verified package does not parse a CSV/API resource into numeric
        # values, so we do not fabricate a water-level/rainfall reading.
        for d in records:
            try:
                repo.upsert_cwc_resource(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "parse: skipped (no verified CSV/API resource parser — catalog-only)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run. Cataloging the verified registry is an offline
        operation that succeeds whenever the source is verified, so on success we
        report LIVE (verified public portal). If an optional portal probe was
        attempted and the dataset page was unreachable, we downgrade the health to
        STALE (the verified catalog rows are still written — the dataset pages are
        verified static metadata, not invented). A genuine failure flows through
        base.run() and lands as ERROR. Mirrors BhuvanCollector / GsiCollector."""
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
        # probe_ok False means the verified dataset page was unreachable.
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
        within-run success during store(), but this call runs afterwards and must
        be able to DOWNGRADE that to STALE (portal unreachable) by clearing
        last_success_at. On a genuine LIVE success it rewrites the same
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
            self._log_quality(note, table="cwc_resources", flag="INFO")
