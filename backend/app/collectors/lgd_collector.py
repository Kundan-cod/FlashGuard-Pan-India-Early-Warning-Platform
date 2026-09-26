"""LGD bridge collector (Track B) — eighth verified external source.

Ties the vendored, ChatGPT-verified LGD adapter (app/data_layer/sources/lgd) into
this project's collector contract (fetch -> validate -> normalize -> store), so
source-health/ingestion logging, the DAL seam and the API treat LGD like any other
collector.

WHY LGD IS CATALOG-ONLY (NOT geometry and NOT a measurement feed):
The Local Government Directory (LGD) is the Government of India's AUTHORITATIVE
directory of administrative identity + codes for the India -> State/UT -> District
-> Sub-district -> Development Block -> Village/ULB -> Ward hierarchy, exposed as
downloadable directories at the official portal. The verified note
(lgd_verified.md / README.md) is explicit about two honesty-critical boundaries:
  1. "Do not assume LGD directory tables are themselves polygon datasets. Boundary
     geometry must be sourced from an authoritative GIS boundary product and
     versioned separately ... joined using LGD codes." So we NEVER fabricate a
     boundary polygon or a coordinate from this directory; geometry lives in the
     locations layer and is joined by LGD code.
  2. "Use LGD codes as stable join keys. Names are display fields only ... Never
     use village/ward names as primary keys because names can repeat or change."
The vendored adapter fetches only the directory DOWNLOAD PAGE and "does not guess
file names or fabricate geometry URLs"; it implements no row parser. So the honest
integration is a CATALOG: we record the verified LGD directory DATASETS (one per
administrative level) + their level + purpose + the verified download-portal URL in
the `lgd_directory` table (stage='CATALOG_ONLY'), and that is all. No
administrative-unit row and no measurement is ever produced here. The ML feature
pipeline never reads lgd_directory, so a catalog row can never masquerade as a unit
or a value. Real LGD unit rows (codes+hierarchy) only enter a separate
administrative table after a future gated, verified directory-file parse.

CONFIGURATION GATE (same shape as Bhuvan's/GSI's/CWC's catalog gate): the verified
config hard-codes the REAL public portal
(https://lgdirectory.gov.in/demo/downloadDirectory.do) and cataloging the directory
datasets needs no credentials, so `verified=true` alone is enough to build the
catalog — a pure, offline operation over verified static metadata. Therefore:

  verified=false in yaml   -> refuses to catalog                 -> ERROR
  verified=true            -> catalogs the verified registry     -> LIVE

Optionally, if an operator injects a `client` exposing fetch_directory_page() (the
vendored LgdClient), a lightweight portal-reachability probe confirms the LGD
download page responds; a failed probe is reported honestly (STALE) while the
verified catalog rows are still written (the directory datasets themselves are
verified static metadata, not invented). httpx is imported lazily (Track B dep,
absent in the sandbox), so importing this module never breaks the Track A suite;
a fake `client=` can be injected for tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import lgd_mapping as M
from app.database import repositories as repo


# LGD directory datasets are static administrative catalog context, not a
# real-time feed. We treat a successfully built catalog over the verified public
# portal as LIVE; there is no NRT/latency concept for the catalog itself.
LGD_REALTIME_CLASS = "static_periodic"


class LgdCollector(BaseCollector):
    """Bridge collector for LGD administrative-directory cataloging.

    Parameters come from the data_sources.yml `lgd` entry. `verified` gates the
    catalog exactly like the other catalog collectors: it refuses to catalog
    unless the registry marks the source verified. No credentials are required —
    the verified LGD portal is public and hard-coded, and cataloging is an offline
    operation over that verified static metadata.
    """

    source_key = "lgd"
    realtime_class = LGD_REALTIME_CLASS

    def __init__(self, *, verified: bool, client: Any = None,
                 registry: dict | None = None,
                 directory_url: str | None = None):
        self.verified = verified
        # Optional client exposing fetch_directory_page() -> str (the vendored
        # LgdClient). In production this stays None (pure catalog) unless an
        # operator wires a portal probe. Injecting a fake here lets the probe path
        # be unit-tested with zero network. The vendored client imports httpx at
        # module load, so it cannot be imported in the portable sandbox.
        self._client = client
        # Optional explicit registry override (used by tests). In production this
        # stays None and fetch() reads the VENDORED, verified LGD_DATASETS.
        self._registry = registry
        # Optional LGD download-portal URL override. None -> verified vendored
        # default.
        self._directory_url = directory_url
        self._stage_notes: list[str] = []

    # ---- lifecycle ----
    def _load_registry(self) -> dict:
        """Return the verified LGD_DATASETS registry. Reads the vendored,
        ChatGPT-verified registry module; never invents datasets or endpoints."""
        if self._registry is not None:
            return self._registry
        from app.data_layer.sources.lgd.sih_lgd.registry import LGD_DATASETS
        return LGD_DATASETS

    def _resolve_directory_url(self) -> str:
        """Return the LGD download-portal URL to catalog against. Prefers an
        explicit override, else the vendored verified LgdConfig default; falls back
        to the mapping module constant if the config import is unavailable
        (sandbox)."""
        if self._directory_url:
            return self._directory_url
        try:
            from app.data_layer.sources.lgd.sih_lgd.config import LgdConfig
            return LgdConfig().download_url
        except Exception:  # noqa: BLE001 — sandbox has no vendored deps loaded
            return M.DEFAULT_LGD_DOWNLOAD_URL

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'lgd' is NOT verified in config/data_sources.yml — "
                "refusing to catalog (no invented endpoints/datasets).")

        registry = self._load_registry()
        directory_url = self._resolve_directory_url()
        records = M.registry_to_catalog_records(registry,
                                                directory_url=directory_url,
                                                retrieved_at=utcnow_iso())
        self._stage_notes.append(
            f"catalog: {len(records)} verified LGD directory dataset(s) from "
            f"{len(registry)} registry entr(ies) at {directory_url}")

        # Optional, honest liveness probe (never fabricated). Only if an operator
        # injected a client exposing fetch_directory_page(); a failure is noted,
        # not invented away, and does not delete the verified catalog rows.
        self._probe_ok: bool | None = None
        if self._client is not None and hasattr(self._client,
                                                 "fetch_directory_page"):
            self._probe_ok = self._probe_page()

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "lgd_catalog"})

    def _probe_page(self) -> bool:
        """Attempt to fetch the verified LGD download page. Returns True only if
        the page responded with some content; records the outcome in stage notes.
        Any exception is caught and reported as unreachable — never suppressed into
        a false success. This reads only the public download-page HTML; it does NOT
        parse any directory file into administrative rows."""
        try:
            html = self._client.fetch_directory_page()
        except Exception as exc:  # noqa: BLE001 — honest: portal unreachable
            self._stage_notes.append(f"probe: LGD download page unreachable ({exc})")
            return False
        ok = bool(html)
        self._stage_notes.append(
            "probe: LGD download page reachable" if ok
            else "probe: LGD download page returned empty response")
        return ok

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Catalog records are directory-dataset metadata, not measurements and not
        geometry, so hydrological/geometric sanity checks do not apply. We only
        require the honesty-critical shape: a dataset_key and (for a usable catalog
        entry) a directory_url. A record carrying anything that looks like a
        coordinate or a numeric value would be a bug — there is no such field in the
        catalog schema, so none can appear."""
        issues: list[Issue] = []
        for i, r in enumerate(raw.records):
            if not isinstance(r, dict):
                issues.append(Issue("BAD", "lgd catalog record is not an object", i))
                continue
            if not r.get("dataset_key"):
                issues.append(Issue("BAD", "catalog record missing dataset_key", i))
                continue
            if not r.get("directory_url"):
                issues.append(Issue("WARNING",
                                    "catalog record has no directory_url", i))
            if r.get("stage") != M.CATALOG_ONLY:
                issues.append(Issue("BAD",
                                    f"catalog record stage must be CATALOG_ONLY "
                                    f"(got {r.get('stage')!r})", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Catalog records are already in internal shape (produced by lgd_mapping
        from the verified registry). No numeric value or geometry exists to
        normalize; pass through unchanged."""
        return list(raw.records)

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Catalog only: persist verified LGD directory datasets -> lgd_directory.
        # There is deliberately NO write to any observation/administrative table
        # here: the verified package does not parse a directory file into rows, so
        # we do not fabricate an administrative-unit row or a geometry.
        for d in records:
            try:
                repo.upsert_lgd_directory(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "parse: skipped (no verified directory-file parser — catalog-only)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run. Cataloging the verified registry is an offline
        operation that succeeds whenever the source is verified, so on success we
        report LIVE (verified public portal). If an optional portal probe was
        attempted and the download page was unreachable, we downgrade the health to
        STALE (the verified catalog rows are still written — the directory datasets
        are verified static metadata, not invented). A genuine failure flows through
        base.run() and lands as ERROR. Mirrors GsiCollector / CwcCollector."""
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
        # probe_ok False means the verified download page was unreachable.
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
            self._log_quality(note, table="lgd_directory", flag="INFO")
