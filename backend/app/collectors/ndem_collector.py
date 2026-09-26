"""NDEM bridge collector (Track B) — tenth (final) verified external source.

Ties the vendored, ChatGPT-verified NDEM adapter (app/data_layer/sources/ndem) into
this project's collector contract (fetch -> validate -> normalize -> store), so
source-health/ingestion logging, the DAL seam and the API treat NDEM like any other
collector.

WHY NDEM IS CATALOG-ONLY (and access-gated):
NDEM (National Database for Emergency Management) is an NRSC/ISRO national GIS
repository + DSS for disaster management, run with MHA for near-real-time disaster
support (near-real-time flood monitoring, flood early warning/vulnerability,
landslide hazard inventory, district nowcast, historical flood reference). The
verified note (ndem_verified.md / README.md) is explicit on two honesty-critical
boundaries:
  1. NDEM's non-base products are PROTECTED: "the portal is protected and requires
     username/password obtained through an authorization form"; authorized users are
     Central/State/District/NDRF/SDRF officials; only public/base layers may be
     visible without login. So this connector must "never bypass authentication or
     invent an undocumented API" — it does not scrape protected products.
  2. "Store access_level and source-health separately from risk score." So NDEM's
     access classification is cataloged as metadata, never folded into a risk value.
The vendored adapter implements ONLY public-portal discovery + a capability/access
registry; it implements no product parser. So the honest integration is a CATALOG:
we record the verified NDEM CAPABILITIES (one per registry entry) + their access
level + role + the verified public portal URL in the `ndem_capabilities` table
(stage='CATALOG_ONLY'), and that is all. No measurement, no geometry, no event and
no risk score is ever produced here. The ML feature pipeline never reads
ndem_capabilities, so a catalog row can never masquerade as a value. Real NDEM
products would only enter observation/event tables after a future AUTHORIZED, gated
adapter behind the same interface.

CONFIGURATION GATE (same shape as Bhuvan's/GSI's/CWC's/LGD's catalog gate): the
verified config hard-codes the REAL public portal (https://ndem.nrsc.gov.in) and
cataloging the PUBLIC capability list needs no credentials, so `verified=true` alone
is enough to build the catalog — a pure, offline operation over verified static
metadata. Credentials (NDEM_USERNAME/NDEM_PASSWORD), when present, only change the
reported access_state of a future authorized adapter; they are NOT required to
catalog and are NEVER required or used here. Therefore:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

Optionally, if an operator injects a `client` exposing check_public_portal() (the
vendored NdemClient), a lightweight public-portal-reachability probe confirms the
NDEM public portal responds; a failed probe is reported honestly (STALE) while the
verified catalog rows are still written (the capabilities themselves are verified
static metadata, not invented). This probe reads only the PUBLIC portal HTML; it
never touches a protected product and never authenticates. httpx is imported lazily
(Track B dep, absent in the sandbox), so importing this module never breaks the
Track A suite; a fake `client=` can be injected for tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import ndem_mapping as M
from app.database import repositories as repo


# NDEM capabilities are a static disaster-management catalog, not a real-time feed.
# We treat a successfully built catalog over the verified public portal as LIVE;
# there is no NRT/latency concept for the catalog itself.
NDEM_REALTIME_CLASS = "static_periodic"


class NdemCollector(BaseCollector):
    """Bridge collector for NDEM capability/access cataloging.

    Parameters come from the data_sources.yml `ndem` entry. `verified` gates the
    catalog exactly like the other catalog collectors: it refuses to catalog unless
    the registry marks the source verified. No credentials are required — the
    verified NDEM public portal is hard-coded, and cataloging the PUBLIC capability
    list is an offline operation over that verified static metadata. NDEM's
    protected products are deliberately never fetched here.
    """

    source_key = "ndem"
    realtime_class = NDEM_REALTIME_CLASS

    def __init__(self, *, verified: bool, client: Any = None,
                 registry: dict | None = None):
        self.verified = verified
        # Optional client exposing check_public_portal() -> str (the vendored
        # NdemClient). In production this stays None (pure catalog) unless an
        # operator wires a public-portal probe. Injecting a fake here lets the probe
        # path be unit-tested with zero network. The vendored client imports httpx at
        # module load, so it cannot be imported in the portable sandbox.
        self._client = client
        # Optional explicit registry override (used by tests). In production this
        # stays None and fetch() reads the VENDORED, verified NDEM_CAPABILITIES.
        self._registry = registry
        self._stage_notes: list[str] = []

    # ---- lifecycle ----
    def _load_registry(self) -> dict:
        """Return the verified NDEM_CAPABILITIES registry. Reads the vendored,
        ChatGPT-verified registry module; never invents capabilities or endpoints."""
        if self._registry is not None:
            return self._registry
        from app.data_layer.sources.ndem.sih_ndem.registry import NDEM_CAPABILITIES
        return NDEM_CAPABILITIES

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'ndem' is NOT verified in config/data_sources.yml — "
                "refusing to catalog (no invented endpoints/capabilities).")

        registry = self._load_registry()
        records = M.registry_to_catalog_records(registry,
                                                retrieved_at=utcnow_iso())
        # Honest visibility into the access split (public vs authorized) without
        # ever bypassing authentication — this is metadata only.
        n_public = sum(1 for r in records if r.get("access") == "PUBLIC")
        self._stage_notes.append(
            f"catalog: {len(records)} verified NDEM capabilit(ies) from "
            f"{len(registry)} registry entr(ies) "
            f"({n_public} PUBLIC, {len(records) - n_public} AUTHORIZED/protected)")

        # Optional, honest liveness probe (never fabricated). Only if an operator
        # injected a client exposing check_public_portal(); a failure is noted, not
        # invented away, and does not delete the verified catalog rows. This reads
        # ONLY the public portal — it never authenticates or touches a protected
        # product.
        self._probe_ok: bool | None = None
        if self._client is not None and hasattr(self._client,
                                                 "check_public_portal"):
            self._probe_ok = self._probe_portal()

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "ndem_catalog"})

    def _probe_portal(self) -> bool:
        """Attempt to fetch the verified NDEM PUBLIC portal. Returns True only if the
        portal responded with some content; records the outcome in stage notes. Any
        exception is caught and reported as unreachable — never suppressed into a
        false success. This reads only the public portal HTML; it does NOT
        authenticate and does NOT fetch any protected product."""
        try:
            html = self._client.check_public_portal()
        except Exception as exc:  # noqa: BLE001 — honest: portal unreachable
            self._stage_notes.append(f"probe: NDEM public portal unreachable ({exc})")
            return False
        ok = bool(html)
        self._stage_notes.append(
            "probe: NDEM public portal reachable" if ok
            else "probe: NDEM public portal returned empty response")
        return ok

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Catalog records are capability metadata, not measurements and not
        geometry, so hydrological/geometric sanity checks do not apply. We only
        require the honesty-critical shape: a capability_key and (for a usable
        catalog entry) a source_url. A record carrying anything that looks like a
        coordinate or a numeric value would be a bug — there is no such field in the
        catalog schema, so none can appear."""
        issues: list[Issue] = []
        for i, r in enumerate(raw.records):
            if not isinstance(r, dict):
                issues.append(Issue("BAD", "ndem catalog record is not an object", i))
                continue
            if not r.get("capability_key"):
                issues.append(Issue("BAD",
                                    "catalog record missing capability_key", i))
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
        """Catalog records are already in internal shape (produced by ndem_mapping
        from the verified registry). No numeric value or geometry exists to
        normalize; pass through unchanged."""
        return list(raw.records)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Catalog only: persist verified NDEM capabilities -> ndem_capabilities.
        # There is deliberately NO write to any observation/event table here: the
        # verified package does not parse a protected product into rows, so we do not
        # fabricate a measurement, an event or a geometry.
        for d in records:
            try:
                repo.upsert_ndem_capability(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "parse: skipped (no verified product parser; protected products are "
            "never bypassed — catalog-only)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run. Cataloging the verified registry is an offline
        operation that succeeds whenever the source is verified, so on success we
        report LIVE (verified public portal). If an optional portal probe was
        attempted and the public portal was unreachable, we downgrade the health to
        STALE (the verified catalog rows are still written — the capabilities are
        verified static metadata, not invented). A genuine failure flows through
        base.run() and lands as ERROR. Mirrors GsiCollector / LgdCollector."""
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
        # probe_ok False means the verified public portal was unreachable.
        status = "STALE" if self._probe_ok is False else "LIVE"
        self._report_status_ext(status, int((time.time() - t0) * 1000),
                                 records=res.stored, error=None,
                                 success=(status == "LIVE"))
        self._log_stage_notes()
        return res

    def _report_status_ext(self, status: str, latency_ms: int, records: int,
                           error: str | None, success: bool = False) -> None:
        """Record an honest source_health row using the extended 7-state vocabulary,
        stored verbatim. last_success_at is only set on a genuine success (a fully
        reachable/verified catalog).

        force_success_ts=True is passed so this write OVERWRITES last_success_at
        rather than COALESCE-preserving it: BaseCollector.run() already recorded a
        within-run success during store(), but this call runs afterwards and must be
        able to DOWNGRADE that to STALE (portal unreachable) by clearing
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
            self._log_quality(note, table="ndem_capabilities", flag="INFO")
