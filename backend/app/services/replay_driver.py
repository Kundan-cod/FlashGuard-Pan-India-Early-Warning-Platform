"""
Replay driver (master prompt sections 31, 64).

Steps a synthetic event forward in time, ingesting observations up to each
timestep and running predictions, so the dashboard can animate risk rising.
Uses the SAME collector + prediction service as live mode; only the data source
and the stepped cutoff differ. Everything is labelled mode='replay'.
"""
from __future__ import annotations

import json
from pathlib import Path

from app.collectors.replay_collector import ReplayCollector
from app.services import prediction_service as psvc
from app.database import repositories as repo


def timesteps(dataset_path: str) -> list[str]:
    with open(dataset_path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    ts = sorted({r["ts"] for r in data.get("observations", []) if "ts" in r})
    return ts


def run_replay(dataset_path: str, reseed: bool = True) -> dict:
    """Ingest the whole event, then run predictions at every timestep for every
    village. Returns a summary. Safe to call from an API endpoint (bounded work
    on the small demo dataset)."""
    from app.services import seed
    if reseed:
        ids = seed.run(reset=True)
    else:
        ids = {"villages": [l["id"] for l in repo.list_locations(level="village")]}

    steps = timesteps(dataset_path)
    total_preds = 0
    for step_ts in steps:
        # ingest everything up to this timestep (idempotent upserts)
        rc = ReplayCollector(dataset_path, source_key="replay", up_to_ts=step_ts)
        rc.run(window={"up_to_ts": step_ts})
        # predict for each village as of this timestep
        for vid in ids["villages"]:
            psvc.run_for_location(vid, as_of=step_ts, mode="replay", emit_alert=True)
            total_preds += 1

    return {"timesteps": steps, "villages": ids["villages"],
            "predictions_written": total_preds}
