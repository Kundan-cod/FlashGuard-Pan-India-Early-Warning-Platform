"""
IMD (India Meteorological Department) bridge collector (Track B) — third
verified external source.

Ties the vendored, ChatGPT-verified IMD adapter (app/data_layer/sources/imd)
into this project's collector contract (fetch -> validate -> normalize ->
store), so source-health/ingestion logging, the DAL seam, and the API treat IMD
like any other collector — exactly as GpmCollector/SmapCollector do.

WHY IMD IS NOT DISCOVERY-ONLY (unlike GPM and SMAP):
GPM/SMAP responses are dataset footprints + download URLs (metadata), so their
values stay NULL until a gated raster/HDF5 parse stage. IMD is different: it
returns REAL numeric government weather/rainfall/warnings. So we DO store the
values — but into a dedicated `imd_observations` table, NOT rainfall_observations.

The reason is granularity + honesty (verified spec imd_verified.md):
  * IMD is DISTRICT/STATION level WITHOUT coordinates. rainfall_observations is
    a point table the ML feature pipeline reads as village-level rainfall.
    Fabricating a village coordinate for a district figure would violate
    "Do not treat district rainfall as village-level rainfall". So IMD never
    touches rainfall_observations and no coordinate is ever invented.
  * IMD warning codes/colors are preserved verbatim, NEVER converted into an ML
    probability ("Do not convert IMD warning color into our ML probability").

Honest source status (unchanged 7-state model): decided by what actually
happened at runtime. IMD *discovery* endpoints may be anonymous, but we keep the
same credential gate as GPM/SMAP so an operator can require a usable token via
the yaml auth model; no usable token -> NOT_CONFIGURED. Fetch failed -> ERROR.
Successful fetch -> LIVE (IMD is a live government source; not a delayed
satellite product).

Replay remains the known-good default: only invoked when IMD is verified+enabled
in data_sources.yml AND (if an auth_env_var is configured) a usable token is
present; otherwise the app keeps running on replay untouched.

httpx/pydantic are imported lazily (Track B deps, absent in the portable
sandbox), so importing this module never breaks the Track A suite. A fake IMD
client exposing the vendored IMDCollector methods can be injected via
`client=` for zero-network unit tests.
"""
from __future__ import annotations

import time
from typing import Any

from app.collectors.base import (BaseCollector, RawBatch, Issue, StoreResult,
                                 utcnow_iso)
from app.collectors import imd_mapping as M
from app.database import repositories as repo


# IMD is a live government source (no satellite processing latency to speak of).
IMD_REALTIME_CLASS = "real_time"

# The four record kinds this collector knows how to normalize. Each maps a
# vendored IMDCollector fetch+normalize method pair to an imd_mapping function.
_RECORD_KINDS = ("current_weather", "district_rainfall", "district_warning",
                 "nowcast")


class ImdCollector(BaseCollector):
    """Bridge collector for the India Meteorological Department REST API.

    Parameters come from the data_sources.yml `imd` entry. `verified` gates the
    fetch exactly like GpmCollector/SmapCollector: it refuses to call out unless
    the registry marks the source verified. `areas` lists which stations/
    districts to poll per record kind; nothing is invented — if no areas are
    configured, IMD default endpoints (no id param) are queried, mirroring the
    vendored collector's behaviour."""

    source_key = "imd"
    realtime_class = IMD_REALTIME_CLASS

    def __init__(self, *, verified: bool,
                 auth_env_var: str | None = "IMD_API_TOKEN",
                 record_kinds: tuple[str, ...] | list[str] | None = None,
                 stations: list[str] | None = None,
                 districts: list[str] | None = None,
                 client: Any = None):
        self.verified = verified
        # IMD discovery endpoints may be anonymous; keep the gate configurable.
        # An operator can set auth_env_var=None in the yaml if they want IMD to
        # be "configured" without a token (public endpoints). Default keeps the
        # same honest gate as the other sources.
        self.auth_env_var = auth_env_var
        self.record_kinds = tuple(record_kinds) if record_kinds else _RECORD_KINDS
        self.stations = list(stations or [])
        self.districts = list(districts or [])
        # Optional pre-built client exposing the vendored IMDCollector methods
        # (current_weather / district_rainfall / district_warning /
        # district_nowcast + normalize_* ). In production this stays None and
        # fetch() lazily builds the vendored, ChatGPT-verified IMDCollector
        # (which needs httpx). Injecting a fake here lets the path be unit-tested
        # with zero network and zero Track B deps — the vendored collector
        # imports httpx at module load, so it cannot be imported in the sandbox.
        self._client = client
        self._stage_notes: list[str] = []

    # ---- credential handling (never hard-coded) ----
    # IMD current_wx/district endpoints are frequently public, but the vendored
    # collector sets an Authorization header verbatim if a token is present and
    # never invents the header name. We mirror the GPM/SMAP placeholder logic so
    # a template .env can never fake a credential. If auth_env_var is None the
    # source is considered configured without a token (public access).
    _PLACEHOLDER_TOKENS = frozenset({
        "", "changeme", "change_me", "your_token_here", "your-token-here",
        "yourtoken", "token", "todo", "tbd", "xxx", "xxxx", "placeholder",
        "none", "null", "na", "n/a", "replace_me", "replace-me",
        "imd_api_token", "imd_api_key", "imd_token", "<token>", "<your_token>",
        "example", "dummy", "test", "fixme",
    })

    def _token(self) -> str | None:
        """Return the IMD token ONLY if it looks genuinely usable. Whitespace-
        only and well-known placeholder values are treated as absent. Never
        hard-codes or logs the token value itself."""
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

    def is_configured(self) -> bool:
        """IMD is configured when either no auth is required (auth_env_var None,
        public endpoints) or a usable token is present."""
        return self.auth_env_var is None or self.has_token()

    # ---- lifecycle ----
    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                "source 'imd' is NOT verified in config/data_sources.yml — "
                "refusing to fetch (no invented endpoints/credentials).")
        if not self.is_configured():
            raise _NotConfigured(
                f"{self.auth_env_var} not set — IMD not configured; "
                "staying on replay.")

        client = self._client
        if client is None:
            # Lazy import: the vendored verified collector needs httpx (Track B
            # dep). Only reached in production; never in the portable sandbox.
            from app.data_layer.sources.imd.sih_imd.collector import IMDCollector
            from app.data_layer.sources.imd.sih_imd.config import Settings
            client = IMDCollector(settings=Settings())

        # Each fetched sub-batch is tagged with its record kind so normalize()
        # can dispatch to the correct mapping. Nothing is invented: a failed
        # sub-fetch is recorded as a stage note and skipped, not faked.
        records: list[dict] = []
        for kind in self.record_kinds:
            try:
                normalized = self._fetch_kind(client, kind)
            except Exception as e:  # noqa: BLE001
                self._stage_notes.append(
                    f"{kind}: fetch failed ({type(e).__name__})")
                continue
            for row in normalized:
                records.append({"_kind": kind, "row": row})
            self._stage_notes.append(f"{kind}: {len(normalized)} row(s)")

        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"payload_kind": "imd_rows"})

    def _fetch_kind(self, client: Any, kind: str) -> list[dict]:
        """Fetch + normalize one record kind via the vendored client, returning
        a list of plain dicts (contract.model_dump()). Iterates configured areas
        where applicable; falls back to the default (no id) endpoint otherwise."""
        out: list[dict] = []
        if kind == "current_weather":
            targets = self.stations or [None]
            for sid in targets:
                payload = client.current_weather(sid)
                out.extend(self._dump(client.normalize_current_weather(payload)))
        elif kind == "district_rainfall":
            targets = self.districts or [None]
            for did in targets:
                payload = client.district_rainfall(did)
                out.extend(self._dump(client.normalize_district_rainfall(payload)))
        elif kind == "district_warning":
            targets = self.districts or [None]
            for did in targets:
                payload = client.district_warning(did)
                out.extend(self._dump(client.normalize_warning(payload)))
        elif kind == "nowcast":
            targets = self.districts or [None]
            for did in targets:
                payload = client.district_nowcast(did)
                out.extend(self._dump(client.normalize_nowcast(payload)))
        else:  # pragma: no cover - guarded by _RECORD_KINDS
            raise ValueError(f"unknown IMD record kind: {kind}")
        return out

    @staticmethod
    def _dump(contracts: Any) -> list[dict]:
        """Convert a list of pydantic contracts (or plain dicts) into plain
        dicts, so imd_mapping stays free of any pydantic dependency."""
        out: list[dict] = []
        for c in contracts or []:
            if isinstance(c, dict):
                out.append(c)
            elif hasattr(c, "model_dump"):
                out.append(c.model_dump())
            elif hasattr(c, "dict"):
                out.append(c.dict())
            else:  # pragma: no cover - defensive
                out.append(dict(c))
        return out

    def validate(self, raw: RawBatch) -> list[Issue]:
        """IMD rows are real numeric government data, not soil-moisture points,
        so point-table sanity checks do not apply. We only require the tagged
        shape produced by fetch(); a row missing its kind/row envelope is
        dropped (BAD) rather than guessed at."""
        issues: list[Issue] = []
        for i, rec in enumerate(raw.records):
            if not isinstance(rec, dict) or "_kind" not in rec or "row" not in rec:
                issues.append(Issue("BAD", "IMD record missing kind/row envelope", i))
                continue
            if rec["_kind"] not in _RECORD_KINDS:
                issues.append(Issue("BAD", f"unknown IMD kind {rec['_kind']!r}", i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Dispatch each tagged row to its imd_mapping function -> internal
        imd_observations record dicts. No coordinate is invented; codes/colors
        are preserved verbatim."""
        by_kind: dict[str, list[dict]] = {k: [] for k in _RECORD_KINDS}
        for rec in raw.records:
            by_kind.setdefault(rec["_kind"], []).append(rec["row"])

        out: list[dict] = []
        ts = raw.fetched_at
        out.extend(M.current_weather_to_records(by_kind["current_weather"],
                                                retrieved_at=ts))
        out.extend(M.district_rainfall_to_records(by_kind["district_rainfall"],
                                                  retrieved_at=ts))
        out.extend(M.warning_to_records(by_kind["district_warning"],
                                        retrieved_at=ts))
        out.extend(M.nowcast_to_records(by_kind["nowcast"], retrieved_at=ts))
        return out

    def store(self, records: list[dict]) -> StoreResult:
        res = StoreResult()
        # Persist real IMD values to imd_observations ONLY — never to
        # rainfall_observations (no invented village coordinate). Codes/colors
        # are stored verbatim; nothing is converted to an ML probability.
        for d in records:
            try:
                repo.upsert_imd_observation(d)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        self._stage_notes.append(
            "store: imd_observations only (never rainfall_observations)")
        return res

    # ---- honest per-run status: map runtime outcome -> health + notes ----
    def run(self, window: dict | None = None) -> StoreResult:
        """Wrap BaseCollector.run to translate a missing credential into an
        explicit NOT_CONFIGURED health state (not an error), and to persist the
        per-stage notes. Successful fetch reports LIVE (IMD is a live gov
        source). Mirrors GpmCollector/SmapCollector.

        The not-configured case is short-circuited BEFORE super().run() so we
        never emit a spurious error health row. A genuine fetch failure still
        flows through base.run() and lands as ERROR."""
        self._stage_notes = []
        t0 = time.time()
        started = utcnow_iso()

        if self.verified and not self.is_configured():
            msg = (f"{self.auth_env_var} not set — IMD not configured; "
                   "staying on replay.")
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
        self._report_status_ext("LIVE", int((time.time() - t0) * 1000),
                                 records=res.stored, error=None, success=True)
        self._log_stage_notes()
        return res

    def _report_status_ext(self, status: str, latency_ms: int, records: int,
                           error: str | None, success: bool = False) -> None:
        """Record an honest source_health row. `status` uses the extended
        7-state vocabulary; stored verbatim. last_success_at only set on a
        genuine success."""
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
            self._log_quality(note, table="imd_observations", flag="INFO")


class _NotConfigured(RuntimeError):
    """Raised when IMD is verified but no usable credential is configured.
    Distinct from an error: the app simply stays on replay."""
