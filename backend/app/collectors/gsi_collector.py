"""GSI / Bhusanket bridge collector (Track B) — sixth verified external source.

Ties the vendored, ChatGPT-verified GSI adapter
(app/data_layer/sources/gsi_bhusanket) into this project's collector contract
(fetch -> validate -> normalize -> store), so source-health/ingestion logging,
the DAL seam and the API treat GSI like any other collector.

WHY GSI IS CATALOG-ONLY (NOT a numeric landslide feed):
GSI's National Landslide Forecasting Centre (Bhusanket portal) exposes a forecast
bulletin, LSM 10K susceptibility maps, an impact-probability map and a field-
validated landslide inventory. The verified note (gsi_verified.md) is explicit:
  1. "This adapter intentionally does not hard-code an undocumented JSON API." The
     public portal is the verified entry point; specific resources are discovered
     from it and then normalized. So we NEVER invent a bulletin value or a numeric
     susceptibility/probability.
  2. GSI forecasting is REGIONAL (Darjeeling/Kalimpong/Nilgiris operational,
     others experimental), NOT a nationwide live API — so each layer carries a
     geographic/operational COVERAGE note, and the system must "explicitly mark
     GSI as unavailable" where it does not cover a location rather than fabricate
     a forecast.
So the honest integration is a CATALOG: we record the verified portal layers +
their roles + coverage in the `gsi_layers` table (stage='CATALOG_ONLY'), and that
is all. No numeric landslide value is ever produced here. The ML landslide model
reads landslide_data and NEVER reads gsi_layers, so a catalog row can never
masquerade as a landslide value. Real GSI inventory/bulletin values only enter
after a future gated, verified parse of a specific documented public resource.

CONFIGURATION GATE (same shape as Bhuvan's catalog gate): the verified registry
hard-codes the REAL public portal (https://bhusanket.gsi.gov.in) and cataloging
needs no credentials, so `verified=true` alone is enough to build the catalog — a
pure, offline operation over verified static metadata. Therefore:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

Optionally, if an operator injects a `client` exposing fetch_portal() (the
vendored BhusanketClient), a lightweight portal-reachability probe confirms the
portal responds; a failed probe is reported honestly (STALE) while the verified
catalog rows are still written (the layers themselves are verified static
metadata, not invented). httpx is imported lazily (Track B dep, absent in the
sandbox), so importing this module never breaks the Track A suite; a fake
`client=` can be injected for tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import gsi_mapping as M
from app.database import repositories as repo


# GSI susceptibility/inventory layers are static/periodic context, not a
# real-time feed. We treat a successfully built catalog over the verified live
# public portal as LIVE; there is no NRT/latency concept for these layers.
GSI_REALTIME_CLASS = "static_periodic"


class GsiCollector(BaseCollector):
    """Bridge collector for GSI/Bhusanket portal-layer cataloging.

    Parameters come from the data_sources.yml `gsi` entry. `verified` gates the
    catalog exactly like the other collectors: it refuses to catalog unless the
    registry marks the source verified. No credentials are required — the
    verified portal is public and hard-coded, and cataloging is an offline
    operation over that verified static metadata.
    """

    source_key = "gsi"
    realtime_class = GSI_REALTIME_CLASS

    def __init__(self, *, verified: bool, client: Any = None,
                 registry: dict | None = None):
        self.verified = verified
        # Optional client exposing fetch_portal() -> str (the vendored
        # BhusanketClient). In production this stays None (pure catalog) unless an
        # operator wires a portal probe. Injecting a fake here lets the probe path
        # be unit-tested with zero network. The vendored client imports httpx at
        # module load, so it cannot be imported in the portable sandbox.
        self._client = client
        # Optional explicit registry override (used by tests). In production this
        # stays None and fetch() reads the VENDORED, verified GSI_LAYERS.
        self._registry = registry
        self._stage_notes: list[str] = []

    # ---- lifecycle ----
    def _load_registry(self) -> dict:
        """Return the verified GSI_LAYERS registry. Reads the vendored,
        ChatGPT-verified registry module; never invents layers or endpoints."""
        if self._registry is not None:
            return self._registry
        from app.data_layer.sources.gsi_bhusanket.sih_gsi.registry import (
            GSI_LAYERS)
        return GSI_LAYERS

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'gsi' is NOT verified in config/data_sources.yml — "
                "refusing to catalog (no invented endpoints/layers).")

        registry = self._load_registry()
        records = M.registry_to_catalog_records(registry,
                                                retrieved_at=utcnow_iso())
        self._stage_notes.append(
            f"catalog: {len(records)} verified portal layer(s) from "
            f"{len(registry)} registry entr(ies)")

        # Optional, honest liveness probe (never fabricated). Only if an operator
        # injected a client exposing fetch_portal(); a failure is noted, not
        # invented away, and does not delete the verified catalog rows.
        self._probe_ok: bool | None = None
        if self._client is not None and hasattr(self._client, "fetch_portal"):
            self._probe_ok = self._probe_portal()

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "gsi_catalog"})

    def _probe_portal(self) -> bool:
        """Attempt to fetch the verified Bhusanket portal. Returns True only if
        the portal responded with some content; records the outcome in stage
        notes. Any exception is caught and reported as unreachable — never
        suppressed into a false success. This reads only the public portal HTML;
        it does NOT parse any bulletin into a numeric value."""
        try:
            html = self._client.fetch_portal()
        except Exception as exc:  # noqa: BLE001 — honest: portal unreachable
            self._stage_notes.append(f"probe: Bhusanket portal unreachable ({exc})")
            return False
        ok = bool(html)
        self._stage_notes.append(
            "probe: Bhusanket portal reachable" if ok
            else "probe: Bhusanket portal returned empty response")
        return ok

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Catalog records are portal-layer metadata, not measurements, so
        landslide sanity checks do not apply. We only require the honesty-critical
        shape: a layer_key and (for a usable catalog entry) a service_url. A
        record carrying anything that looks like a numeric susceptibility would be
        a bug — there is no such field in the catalog schema, so none can
        appear."""
        issues: list[Issue] = []
        for i, r in enumerate(raw.records):
            if not isinstance(r, dict):
                issues.append(Issue("BAD", "gsi catalog record is not an object", i))
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
        """Catalog records are already in internal shape (produced by gsi_mapping
        from the verified registry). No numeric value exists to normalize; pass
        through unchanged."""
        return list(raw.records)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Catalog only: persist verified portal layers -> gsi_layers. There is
        # deliberately NO write to landslide_data here: the verified package does
        # not parse a bulletin/inventory into numeric values, so we do not
        # fabricate a susceptibility/probability.
        for d in records:
            try:
                repo.upsert_gsi_layer(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "parse: skipped (no verified bulletin/inventory parser — catalog-only)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run. Cataloging the verified registry is an offline
        operation that succeeds whenever the source is verified, so on success we
        report LIVE (verified public portal). If an optional portal probe was
        attempted and the portal was unreachable, we downgrade the health to STALE
        (the verified catalog rows are still written — the layers are verified
        static metadata, not invented). A genuine failure flows through base.run()
        and lands as ERROR. Mirrors BhuvanCollector."""
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
        # probe_ok False means the verified portal was unreachable.
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
            self._log_quality(note, table="gsi_layers", flag="INFO")
