"""
Entry point for the Track A portable core (master prompt section 39, Phase 1).

Usage:
  python3 backend/app/portable/run.py                # seed + replay + serve
  python3 backend/app/portable/run.py --no-replay    # seed + serve (empty risk)
  python3 backend/app/portable/run.py --port 8080

Runs with ONLY the Python stdlib + numpy-free code, so it works in constrained
environments. Serves the API the single-file Leaflet dashboard consumes.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

# ensure 'app' package is importable when run as a script
BACKEND = Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.database import db
from app.services import seed
from app.services import replay_driver
from app.portable.api import serve

DEFAULT_REPLAY = BACKEND.parent / "data" / "replay" / "uttarakhand_flash_flood_event.json"


def main():
    ap = argparse.ArgumentParser(description="FlashGuard portable core")
    ap.add_argument("--host", default=os.environ.get("PORTABLE_API_HOST", "127.0.0.1"))
    ap.add_argument("--port", type=int, default=int(os.environ.get("PORTABLE_API_PORT", "8000")))
    ap.add_argument("--no-replay", action="store_true", help="seed only, skip replay")
    ap.add_argument("--replay-dataset", default=str(DEFAULT_REPLAY))
    args = ap.parse_args()

    print("[1/3] initializing database + synthetic seed (labelled)...")
    ids = seed.run(reset=True)
    seed.seed_national_regions(ids["country"])

    if not args.no_replay:
        print("[2/3] running synthetic replay through the full pipeline...")
        summary = replay_driver.run_replay(args.replay_dataset, reseed=False)
        print(f"      timesteps={len(summary['timesteps'])} "
              f"villages={len(summary['villages'])} "
              f"predictions={summary['predictions_written']}")
    else:
        print("[2/3] skipping replay (--no-replay)")

    print("[3/3] starting API...")
    serve(host=args.host, port=args.port)


if __name__ == "__main__":
    main()
