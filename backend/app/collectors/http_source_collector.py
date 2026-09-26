"""
Adapter template for a VERIFIED external HTTP source (Track B) — pending wiring.

*** DO NOT ENABLE until the source is verified in config/data_sources.yml
    (verified: true, access_status: green/yellow). ***

This is the concrete shape a real collector takes once ChatGPT supplies a
verified endpoint spec. It subclasses the SAME BaseCollector contract as the
replay collector, so everything downstream (validation → normalization →
storage → features → risk) is identical whether data came from replay or a live
API. Credentials are read from the env var named in the registry (auth_env_var),
never hard-coded (master prompt sections 36, 55, 62).

Until a source is verified, fetch() raises so it can never silently emit
invented data (section 40, 57).
"""
from __future__ import annotations

import os

from app.collectors.base import BaseCollector, RawBatch, Issue, StoreResult, utcnow_iso
from app.processing import validate as V
from app.processing import normalize as N
from app.database import repositories as repo


class HttpSourceCollector(BaseCollector):
    """Generic verified-HTTP-source collector.

    Parameters come from the data_sources.yml registry entry. `kind` selects the
    validate/normalize/store path (rainfall|soil|river). `auth_env_var` names the
    environment variable holding the credential (may be None for open data).
    """

    def __init__(self, source_key: str, kind: str, api_url: str,
                 realtime_class: str, resolution_m: float | None = None,
                 auth_env_var: str | None = None, verified: bool = False):
        self.source_key = source_key
        self.kind = kind
        self.api_url = api_url
        self.realtime_class = realtime_class
        self.resolution_m = resolution_m
        self.auth_env_var = auth_env_var
        self.verified = verified

    def _token(self) -> str | None:
        return os.environ.get(self.auth_env_var) if self.auth_env_var else None

    def fetch(self, window: dict | None = None) -> RawBatch:
        if not self.verified:
            raise RuntimeError(
                f"source '{self.source_key}' is NOT verified — refusing to fetch. "
                f"Verify it in config/data_sources.yml and provide the real endpoint "
                f"before enabling (no invented endpoints/credentials).")
        # --- Real implementation goes here once verified, e.g.: ---
        #   import httpx
        #   headers = {"Authorization": f"Bearer {self._token()}"} if self._token() else {}
        #   resp = httpx.get(self.api_url, params=window or {}, headers=headers, timeout=30)
        #   resp.raise_for_status()
        #   records = self._parse(resp)   # map the VERIFIED response schema -> raw dicts
        # The parser must be written against the source's real, documented schema.
        raise NotImplementedError(
            f"fetch() for '{self.source_key}' pending verified endpoint spec.")

    def validate(self, raw: RawBatch) -> list[Issue]:
        check = {"rainfall": V.check_rainfall, "soil": V.check_soil,
                 "river": V.check_river}.get(self.kind)
        issues: list[Issue] = []
        if check is None:
            return [Issue("BAD", f"unknown kind '{self.kind}'", None)]
        for i, rec in enumerate(raw.records):
            for level, reason in check(rec):
                issues.append(Issue(level, reason, i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        out = []
        for rec in raw.records:
            if self.kind == "rainfall":
                out.append(N.norm_rainfall(rec, self.source_key, self.realtime_class,
                                           self.resolution_m))
            elif self.kind == "soil":
                out.append(N.norm_soil(rec, self.source_key, self.realtime_class,
                                       self.resolution_m,
                                       rec.get("unit", "percent")))
            elif self.kind == "river":
                out.append(N.norm_river(rec, self.source_key, self.realtime_class))
        return out

    def store(self, observations: list[dict]) -> StoreResult:
        res = StoreResult()
        writer = {"rainfall": repo.upsert_rainfall, "soil": repo.upsert_soil,
                  "river": repo.upsert_river}.get(self.kind)
        if writer is None:
            res.rejected = len(observations)
            return res
        for o in observations:
            try:
                writer(o)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        return res
