"""
Replay collector (master prompt sections 31, 64).

Streams clearly-labelled historical/synthetic observations through the SAME
pipeline as a live collector (fetch->validate->normalize->store). This is how
the SIH demo runs without depending on live government APIs, while never
mislabelling replayed data as real: every record is stored with
realtime_class='replay'.

Reads a replay dataset JSON (see data/replay/*.json). One collector instance
handles rainfall / soil / river / iot records in one file, dispatching by kind.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.collectors.base import BaseCollector, RawBatch, Issue, StoreResult, utcnow_iso
from app.processing import validate as V
from app.processing import normalize as N
from app.database import repositories as repo


class ReplayCollector(BaseCollector):
    realtime_class = "replay"

    def __init__(self, dataset_path: str, source_key: str = "replay",
                 up_to_ts: str | None = None):
        self.dataset_path = Path(dataset_path)
        self.source_key = source_key
        self.up_to_ts = up_to_ts   # only emit records at/-before this ts (for stepped replay)

    def fetch(self, window: dict | None = None) -> RawBatch:
        with open(self.dataset_path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        records = data.get("observations", [])
        cutoff = (window or {}).get("up_to_ts", self.up_to_ts)
        if cutoff:
            records = [r for r in records if r.get("ts", "") <= cutoff]
        return RawBatch(source=self.source_key, fetched_at=utcnow_iso(),
                        records=records, meta={"dataset": str(self.dataset_path)})

    def validate(self, raw: RawBatch) -> list[Issue]:
        issues: list[Issue] = []
        for i, rec in enumerate(raw.records):
            kind = rec.get("kind")
            checks = {
                "rainfall": V.check_rainfall, "soil": V.check_soil,
                "river": V.check_river, "iot": V.check_iot,
            }.get(kind)
            if checks is None:
                issues.append(Issue("BAD", f"unknown kind '{kind}'", i))
                continue
            for level, reason in checks(rec):
                issues.append(Issue(level, reason, i))
        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        out = []
        for rec in raw.records:
            kind = rec.get("kind")
            src = rec.get("source", self.source_key)
            if kind == "rainfall":
                out.append(("rainfall",
                            N.norm_rainfall(rec, src, "replay", rec.get("resolution_m"))))
            elif kind == "soil":
                out.append(("soil",
                            N.norm_soil(rec, src, "replay", rec.get("resolution_m"),
                                        rec.get("unit", "percent"))))
            elif kind == "river":
                out.append(("river", N.norm_river(rec, src, "replay")))
            elif kind == "iot":
                r = N.norm_iot(rec)
                r["is_simulated"] = 1
                out.append(("iot", r))
        return out

    def store(self, observations: list[tuple]) -> StoreResult:
        res = StoreResult()
        for kind, o in observations:
            try:
                if kind == "rainfall":
                    repo.upsert_rainfall(o)
                elif kind == "soil":
                    repo.upsert_soil(o)
                elif kind == "river":
                    repo.upsert_river(o)
                elif kind == "iot":
                    repo.upsert_iot(o)
                res.stored += 1
            except Exception:  # noqa: BLE001
                res.rejected += 1
        return res
