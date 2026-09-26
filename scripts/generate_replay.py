"""
Generate a SYNTHETIC flash-flood replay dataset (master prompt s.45/64/67).

Output: data/replay/uttarakhand_flash_flood_event.json
All records are flagged synthetic and are intended for REPLAY mode only. This
does NOT represent real NASA/IMD/CWC observations.

Scenario: a ~4 hour window over a small hilly cluster where rainfall intensifies,
soil saturates, and a river rises — driving risk LOW -> MODERATE -> HIGH -> CRITICAL.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "data" / "replay" / "uttarakhand_flash_flood_event.json"

# three synthetic villages (lon/lat) in a hilly cluster (labelled synthetic)
SITES = [
    {"name": "Devgaon",  "lat": 30.05, "lon": 78.05},
    {"name": "Ranikhet-South", "lat": 30.07, "lon": 78.08},
    {"name": "Talli",    "lat": 30.03, "lon": 78.02},
]

def main():
    start = datetime(2026, 7, 15, 6, 0, tzinfo=timezone.utc)
    obs = []
    # 9 steps, 30 min apart (06:00 -> 10:00)
    intensities = [3, 8, 18, 35, 55, 78, 95, 70, 40]     # 30-min rainfall (mm)
    for step, rain30 in enumerate(intensities):
        ts = (start + timedelta(minutes=30 * step)).strftime("%Y-%m-%dT%H:%M:%SZ")
        # accumulations grow over the event
        rain3 = sum(intensities[max(0, step - 5):step + 1])
        rain24 = sum(intensities[:step + 1]) + 20
        soil = min(98.0, 45 + step * 6.5)                # soil saturates
        level = round(1.5 + 0.35 * sum(intensities[:step + 1]) / 50, 2)  # river rises
        for s in SITES:
            obs.append({"kind": "rainfall", "source": "replay", "synthetic": True,
                        "ts": ts, "latitude": s["lat"], "longitude": s["lon"],
                        "rainfall_30m": rain30, "rainfall_3h": rain3,
                        "rainfall_24h": rain24, "resolution_m": 10000})
            obs.append({"kind": "soil", "source": "replay", "synthetic": True,
                        "ts": ts, "latitude": s["lat"], "longitude": s["lon"],
                        "surface_moisture": round(soil, 1), "resolution_m": 9000})
        # one shared river station near the cluster
        obs.append({"kind": "river", "source": "replay", "synthetic": True,
                    "station_id": "SYN-RIV-01", "ts": ts,
                    "latitude": 30.04, "longitude": 78.04,
                    "water_level": level})
        # one synthetic IoT gauge
        obs.append({"kind": "iot", "source": "replay", "synthetic": True,
                    "sensor_id": "SYN-IOT-01", "ts": ts,
                    "latitude": 30.05, "longitude": 78.05,
                    "rainfall_mm": rain30, "soil_moisture": round(soil, 1),
                    "water_level_m": level, "temperature": 21.0,
                    "is_simulated": True})
    payload = {
        "meta": {
            "synthetic": True,
            "description": "SYNTHETIC flash-flood replay scenario (NOT real data)",
            "scenario": "hilly cluster, intensifying rainfall over ~4h",
            "generated_for": "SIH26192 demo replay mode",
        },
        "observations": obs,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)
    print(f"wrote {len(obs)} synthetic records -> {OUT}")


if __name__ == "__main__":
    main()
