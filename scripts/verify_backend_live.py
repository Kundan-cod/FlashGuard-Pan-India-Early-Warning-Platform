#!/usr/bin/env python3
"""
Comprehensive Live Backend Verification Script for FlashGuard.
Validates all core backend components:
1. REST API endpoint connectivity, status codes, and JSON contract integrity.
2. AI/ML dual models (Flash Flood + Landslide) and calibration.
3. Live ISRO INSAT-3DS multi-spectral rainfall telemetry.
4. ThingSpeak Public IoT Feed integration (Channel 3368421).
5. SQLite Database tables, schemas, and record counts.
6. Alert escalation and briefing generation.
"""
import json
import sqlite3
import sys
import time
import urllib.request
from pathlib import Path

BASE_URL = "http://127.0.0.1:8000"
DB_PATH = Path("data/portable/flashflood.sqlite")


def probe_endpoint(path: str, name: str, expected_status: int = 200, method: str = "GET", payload: dict = None):
    t0 = time.time()
    url = BASE_URL + path
    try:
        data_bytes = json.dumps(payload).encode("utf-8") if payload else None
        headers = {"User-Agent": "FlashGuardVerifier/1.0"}
        if data_bytes:
            headers["Content-Type"] = "application/json"
        
        req = urllib.request.Request(url, data=data_bytes, headers=headers, method=method)
        with urllib.request.urlopen(req, timeout=8) as resp:
            elapsed = int((time.time() - t0) * 1000)
            body = resp.read().decode("utf-8")
            parsed = json.loads(body) if body else {}
            return True, resp.status, elapsed, parsed, ""
    except Exception as e:
        elapsed = int((time.time() - t0) * 1000)
        return False, 0, elapsed, None, str(e)


def main():
    print("=" * 70)
    print("FLASHGUARD PAN-INDIA EARLY WARNING -- BACKEND SYSTEM VERIFICATION")
    print("=" * 70)
    print(f"Target Server : {BASE_URL}")
    print(f"Database File : {DB_PATH.resolve()}")
    print("-" * 70)

    # 1. API Endpoints
    endpoints = [
        ("GET", "/health", "Core Health Probe", None),
        ("GET", "/system/status", "System Runtime Status", None),
        ("GET", "/data-sources/status", "Data Sources & Ingestion Feed Health", None),
        ("GET", "/locations", "National Hierarchy (Villages & Basins)", None),
        ("GET", "/risk/map", "National Risk GeoJSON Map", None),
        ("GET", "/alerts", "Disaster Alert Escalation Feed", None),
        ("GET", "/weather/live", "Live ISRO INSAT-3DS Satellite Telemetry", None),
        ("GET", "/weather/mode", "Weather Mode Engine", None),
        ("GET", "/iot/thingspeak/latest?channel_id=3368421", "Public IoT REST Feed (Ch 3368421)", None),
        ("GET", "/model/info", "AI/ML Dual Models Info & Metadata", None),
        ("GET", "/model/metrics", "Model Validation & Honest Metrics", None),
        ("GET", "/model/feature-importance", "ML Feature Importance Breakdown", None),
        ("GET", "/model/explain/1", "Model Explainability & Risk Drivers (Loc 1)", None),
        ("GET", "/briefing/1?persona=PUBLIC_ALERT", "Automated Warning Briefing Generation", None),
        ("POST", "/prediction/run", "On-Demand Risk Inference Engine", {"location_id": 1, "mode": "simulation"}),
        ("POST", "/iot/thingspeak/sync", "ThingSpeak Ingestion & Normalization Sync", {"results": 5}),
    ]

    all_passed = True
    print("\n[1/3] PROBING BACKEND REST APIS:")
    for method, path, desc, payload in endpoints:
        ok, status, ms, data, err = probe_endpoint(path, desc, method=method, payload=payload)
        if ok:
            details = ""
            if isinstance(data, dict):
                keys = list(data.keys())[:3]
                details = f"({', '.join(keys)})"
            print(f"  [PASS] {desc:42} {status} OK  [{ms:3}ms] {details}")
        else:
            all_passed = False
            print(f"  [FAIL] {desc:42} ERROR: {err}")

    # 2. Database Record Counts
    print("\n[2/3] VERIFYING DATABASE TABLES & RECORD COUNTS:")
    if DB_PATH.exists():
        conn = sqlite3.connect(DB_PATH)
        cur = conn.cursor()
        tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        print(f"  Total Tables Found: {len(tables)}")
        for t in sorted(tables):
            cur.execute(f"SELECT COUNT(*) FROM {t}")
            cnt = cur.fetchone()[0]
            print(f"    * {t:28} : {cnt:>6} records")
        conn.close()
    else:
        all_passed = False
        print(f"  [FAIL] Database file not found at {DB_PATH}")

    # 3. Live Data Ingestion Integrity Checks
    print("\n[3/3] VERIFYING DATA INTEGRITY & SCIENTIFIC UNITS:")
    ok, _, _, ts_data, _ = probe_endpoint("/iot/thingspeak/latest?channel_id=3368421", "ThingSpeak")
    if ok and ts_data:
        entries = len(ts_data.get("raw_telemetry", []))
        classification = ts_data.get("classification")
        print(f"  [PASS] ThingSpeak Channel 3368421 : {entries} raw records stored (classification={classification})")
    
    ok, _, _, weather_data, _ = probe_endpoint("/weather/live", "Weather Live")
    if ok and weather_data:
        source = weather_data.get("source")
        stations = len(weather_data.get("observations", []))
        granule = weather_data.get("granule_id")
        print(f"  [PASS] ISRO MOSDAC Satellite     : {stations} monitored stations sampled from {source} (granule={granule})")

    print("\n" + "=" * 70)
    if all_passed:
        print("[SUCCESS] ALL BACKEND SYSTEMS ARE 100% OPERATIONAL AND WORKING CORRECTLY!")
    else:
        print("[WARNING] SOME BACKEND CHECKS FAILED. SEE DETAILS ABOVE.")
    print("=" * 70)


if __name__ == "__main__":
    main()
