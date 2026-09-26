"""Historical-labels bridge collector (Track B) — ninth verified external source.

Ties the vendored, ChatGPT-verified historical-labels layer
(app/data_layer/sources/historical) into this project's collector contract
(fetch -> validate -> normalize -> store), so source-health/ingestion logging, the
DAL seam and the API treat the historical-label layer like any other collector.

WHY HISTORICAL IS CATALOG-ONLY (NOT events and NOT training labels):
The historical-labels layer defines the VERIFIED official sources of historical
flood / landslide events used for model training and replay validation:
  * NRSC/ISRO Landslide Atlas (~80,000 landslides mapped 1998-2022, 17 states+2 UTs)
  * NRSC flood-hazard zonation (historical satellite-derived flood datasets)
  * Bhuvan historical flood-inundation service (1998-2019 maximum-inundation layers)
  * NDEM historical disaster data (1999-present, portal/authentication dependent)
The verified note (docs/historical_labels_verified.md / README.md) is explicit on
two honesty-critical boundaries:
  1. These are AUTHORITATIVE EVENT inventories, NOT complete presence/absence
     censuses. "Do not interpret the inventory as a complete nationwide absence/
     presence census" and "Do not convert missing observations into negatives."
  2. The labeling rule is THREE-STATE (1=confirmed event, 0=confirmed non-event only
     where observation coverage is demonstrably adequate, -1=unobserved/unknown) so
     the model never learns "no record = no disaster"; and an event must never be
     reduced to a fake point label.
The vendored package ships the source registry + the labeling RULE only — it ships
NO event rows and NO parser. So the honest integration is a CATALOG: we record the
verified historical-event SOURCES (one per registry key) + their hazard + period +
role + access note in the `historical_sources` table (stage='CATALOG_ONLY'), and
that is all. No event geometry, no event time and no 1/0/-1 label is ever produced
here. The ML training pipeline that would consume labels reads a separate (future)
events/labels table, never this catalog, so a catalog row can never masquerade as a
confirmed event or a label. Real events + labels only enter after a gated, verified
inventory parse — and negatives would then be sampled only from areas/times with
demonstrably adequate observation coverage.

CONFIGURATION GATE (same shape as Bhuvan's/GSI's/CWC's/LGD's catalog gate): the
verified registry hard-codes the REAL official source URLs and cataloging them needs
no credentials, so `verified=true` alone is enough to build the catalog — a pure,
offline operation over verified static metadata. Therefore:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

Optionally, if an operator injects a `client` exposing fetch_source_page() (a
reachability probe of a verified source URL), a failed probe is reported honestly
(STALE) while the verified catalog rows are still written (the sources themselves
are verified static metadata, not invented). No such client ships with the vendored
package (it provides the registry + labeling rule only), so in production this stays
a pure catalog; the hook exists purely for symmetry and testability.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import historical_mapping as M
from app.database import repositories as repo


# Historical-event sources are static reference context, not a real-time feed. We
# treat a successfully built catalog over the verified official sources as LIVE;
# there is no NRT/latency concept for the catalog itself.
HISTORICAL_REALTIME_CLASS = "static_periodic"


class HistoricalCollector(BaseCollector):
    """Bridge collector for historical-label SOURCE cataloging.

    Parameters come from the data_sources.yml `historical` entry. `verified` gates
    the catalog exactly like the other catalog collectors: it refuses to catalog
    unless the registry marks the source verified. No credentials are required — the
    verified official source URLs are public references and cataloging is an offline
    operation over that verified static metadata.
    """

    source_key = "historical"
    realtime_class = HISTORICAL_REALTIME_CLASS

    def __init__(self, *, verified: bool, client: Any = None,
                 registry: dict | None = None):
        self.verified = verified
        # Optional client exposing fetch_source_page() -> str for a reachability
        # probe of a verified source URL. In production this stays None (pure
        # catalog); no such client ships with the vendored package. Injecting a fake
        # here lets the probe path be unit-tested with zero network.
        self._client = client
        # Optional explicit registry override (used by tests). In production this
        # stays None and fetch() reads the VENDORED, verified HISTORICAL_SOURCES.
        self._registry = registry
        self._stage_notes: list[str] = []

    # ---- lifecycle ----
    def _load_registry(self) -> dict:
        """Return the verified HISTORICAL_SOURCES registry. Reads the vendored,
        ChatGPT-verified registry module; never invents sources or endpoints."""
        if self._registry is not None:
            return self._registry
        from app.data_layer.sources.historical.sih_history.registry import (
            HISTORICAL_SOURCES)
        return HISTORICAL_SOURCES

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'historical' is NOT verified in config/data_sources.yml — "
                "refusing to catalog (no invented sources/endpoints).")

        registry = self._load_registry()
        records = M.registry_to_catalog_records(registry,
                                                retrieved_at=utcnow_iso())
        self._stage_notes.append(
            f"catalog: {len(records)} verified historical-event source(s) from "
            f"{len(registry)} registry entr(ies)")

        # Optional, honest liveness probe (never fabricated). Only if an operator
        # injected a client exposing fetch_source_page(); a failure is noted, not
        # invented away, and does not delete the verified catalog rows.
        self._probe_ok: bool | None = None
        if self._client is not None and hasattr(self._client,
                                                 "fetch_source_page"):
            self._probe_ok = self._probe_page()

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "historical_catalog"})

    def _probe_page(self) -> bool:
        """Attempt to fetch a verified historical source page. Returns True only if
        the page responded with some content; records the outcome in stage notes.
        Any exception is caught and reported as unreachable — never suppressed into
        a false success. This reads only a public reference page; it does NOT parse
        any inventory into event rows or labels."""
        try:
            html = self._client.fetch_source_page()
        except Exception as exc:  # noqa: BLE001 — honest: source unreachable
            self._stage_notes.append(
                f"probe: historical source unreachable ({exc})")
            return False
        ok = bool(html)
        self._stage_notes.append(
            "probe: historical source reachable" if ok
            else "probe: historical source returned empty response")
        return ok

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Catalog records are verified source references, not events and not labels,
        so event/geometry sanity checks do not apply. We only require the
        honesty-critical shape: a source_key and (for a usable catalog entry) a
        source_url. A record carrying anything that looks like an event geometry, an
        event time or a numeric label would be a bug — there is no such field in the
        catalog schema, so none can appear."""
        issues: list[Issue] = []
        for i, r in enumerate(raw.records):
            if not isinstance(r, dict):
                issues.append(Issue("BAD",
                                     "historical catalog record is not an object", i))
                continue
            if not r.get("source_key"):
                issues.append(Issue("BAD", "catalog record missing source_key", i))
                continue
            if not r.get("source_url"):
                issues.append(Issue("WARNING",
                                    "catalog record has no source_url", i))
            if r.get("stage") != M.CATALOG_ONLY:
                issues.append(Issue("BAD",
                                    f"catalog record stage must be CATALOG_ONLY "
                                    f"(got {r.get('stage')!r})", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Catalog records are already in internal shape (produced by
        historical_mapping from the verified registry). No event, geometry or label
        exists to normalize; pass through unchanged."""
        return list(raw.records)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Catalog only: persist verified historical-event sources ->
        # historical_sources. There is deliberately NO write to any events/labels
        # or observation table here: the verified package ships no inventory parser,
        # so we do not fabricate a confirmed event, an event geometry, or a 1/0/-1
        # training label.
        for d in records:
            try:
                repo.upsert_historical_source(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "parse: skipped (no verified inventory parser — catalog-only; the "
            "three-state 1/0/-1 labeling rule is applied only after a gated parse)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run. Cataloging the verified registry is an offline
        operation that succeeds whenever the source is verified, so on success we
        report LIVE (verified official sources). If an optional source probe was
        attempted and the page was unreachable, we downgrade the health to STALE
        (the verified catalog rows are still written — the sources are verified
        static metadata, not invented). A genuine failure flows through base.run()
        and lands as ERROR. Mirrors GsiCollector / CwcCollector / LgdCollector."""
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
        # probe_ok False means a verified source page was unreachable.
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
        within-run success during store(), but this call runs afterwards and must be
        able to DOWNGRADE that to STALE (source unreachable) by clearing
        last_success_at. On a genuine LIVE success it rewrites the same timestamp."""
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
            self._log_quality(note, table="historical_sources", flag="INFO")
