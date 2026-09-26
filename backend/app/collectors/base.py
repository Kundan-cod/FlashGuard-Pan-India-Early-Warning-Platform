"""
Collector contract (master prompt sections 7, 63).

Every data source — real, replay, mock, or IoT — implements this same
interface so nothing downstream can tell them apart. A real collector for a
verified source (e.g. GPM) will subclass this and implement fetch() against the
verified endpoint; until ChatGPT verifies a source, only replay/mock collectors
exist, and they are clearly labelled.

Lifecycle:  fetch() -> validate() -> normalize() -> store() -> report_status()

Canonical observation dicts (produced by normalize) use these keys depending on
kind; see processing/normalize.py for the canonical schema per variable.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

# Go through the repositories DAL — NOT app.database.db directly — so that on
# Track B the sys.modules swap (repositories -> repositories_prod) routes these
# source-health / ingestion / quality writes to PostGIS. Importing `db` here was
# a seam leak: it bypassed the swap and wrote to an empty in-image SQLite file.
from app.database import repositories as repo


def utcnow_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class RawBatch:
    """Whatever a source hands back before validation/normalization."""
    source: str
    fetched_at: str
    records: list[dict]
    meta: dict = field(default_factory=dict)


@dataclass
class Issue:
    level: str          # WARNING | BAD
    reason: str
    record_index: int | None = None


@dataclass
class StoreResult:
    received: int = 0
    stored: int = 0
    rejected: int = 0


@dataclass
class SourceHealth:
    source: str
    status: str                 # online | delayed | offline | unknown
    last_success_at: str | None = None
    last_attempt_at: str | None = None
    last_latency_ms: int | None = None
    last_error: str | None = None
    records_last_run: int | None = None


class BaseCollector:
    """Abstract collector. Subclasses set `source_key` and implement fetch/
    validate/normalize/store. run() orchestrates the lifecycle + logging."""

    source_key: str = "base"
    realtime_class: str = "unknown"   # live | near_real_time | replay | simulation

    # ---- lifecycle steps (override as needed) ----
    def fetch(self, window: dict | None = None) -> RawBatch:
        raise NotImplementedError

    def validate(self, raw: RawBatch) -> list[Issue]:
        return []

    def normalize(self, raw: RawBatch) -> list[dict]:
        raise NotImplementedError

    def store(self, observations: list[dict]) -> StoreResult:
        raise NotImplementedError

    # ---- orchestration ----
    def run(self, window: dict | None = None) -> StoreResult:
        started = utcnow_iso()
        t0 = time.time()
        status = "ok"
        err = None
        received = stored = rejected = 0
        try:
            raw = self.fetch(window)
            received = len(raw.records)
            issues = self.validate(raw)
            bad_idx = {i.record_index for i in issues if i.level == "BAD"
                       and i.record_index is not None}
            # drop BAD records before normalization (section 11)
            if bad_idx:
                raw = RawBatch(
                    source=raw.source, fetched_at=raw.fetched_at,
                    records=[r for i, r in enumerate(raw.records) if i not in bad_idx],
                    meta=raw.meta,
                )
                rejected = len(bad_idx)
                for iss in issues:
                    if iss.level == "BAD":
                        self._log_quality(iss.reason)
            obs = self.normalize(raw)
            res = self.store(obs)
            res.received = received
            res.rejected = rejected + res.rejected
            stored = res.stored
            self._report(status="online", latency_ms=int((time.time() - t0) * 1000),
                         records=stored, success=True)
            self._log_ingestion(started, status, received, stored, res.rejected,
                                int((time.time() - t0) * 1000), None)
            return res
        except Exception as e:  # noqa: BLE001
            status = "error"
            err = f"{type(e).__name__}: {e}"
            self._report(status="offline", latency_ms=int((time.time() - t0) * 1000),
                         records=0, success=False, error=err)
            self._log_ingestion(started, status, received, stored, rejected,
                                int((time.time() - t0) * 1000), err)
            raise

    def report_status(self) -> SourceHealth:
        row = repo.get_source_health(self.source_key)
        if not row:
            return SourceHealth(source=self.source_key, status="unknown")
        return SourceHealth(
            source=self.source_key, status=row["status"],
            last_success_at=row["last_success_at"],
            last_attempt_at=row["last_attempt_at"],
            last_latency_ms=row["last_latency_ms"],
            last_error=row["last_error"],
            records_last_run=row["records_last_run"],
        )

    # ---- internal logging helpers (all go through the repositories DAL) ----
    def _report(self, status: str, latency_ms: int, records: int,
                success: bool, error: str | None = None) -> None:
        now = utcnow_iso()
        repo.record_source_health({
            "source": self.source_key, "status": status,
            "last_attempt_at": now,
            "last_success_at": now if success else None,
            "last_latency_ms": latency_ms, "last_error": error,
            "records_last_run": records, "updated_at": now,
        })

    def _log_ingestion(self, started: str, status: str, received: int,
                       stored: int, rejected: int, latency_ms: int,
                       error: str | None) -> None:
        repo.log_ingestion({
            "source": self.source_key, "started_at": started,
            "finished_at": utcnow_iso(), "status": status,
            "records_received": received, "records_stored": stored,
            "records_rejected": rejected, "latency_ms": latency_ms,
            "error": error,
        })

    def _log_quality(self, reason: str, table: str = "", flag: str = "BAD") -> None:
        repo.log_quality({
            "source": self.source_key, "table_name": table,
            "ts": utcnow_iso(), "flag": flag, "reason": reason,
        })
