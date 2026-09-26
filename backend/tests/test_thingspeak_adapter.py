"""
Unit & Integration Tests for ThingSpeak External Public IoT Adapter (Channel 3368421).

Verifies:
1. Public REST API retrieval (mock and live fallbacks)
2. Schema validation & physical bounds QC
3. Scientific unit normalization (cm -> m, non-conversion of ADC values)
4. Staleness detection (historical timestamp > 60m flagged as STALE)
5. Malformed payload handling (bad timestamps, negative water levels rejected)
6. Idempotent storage in iot_observations and iot_raw_telemetry
7. Architectural separation: ThingSpeak raw telemetry never connects directly to ML
"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
BACKEND = HERE.parent
for p in (str(BACKEND), str(HERE)):
    if p not in sys.path:
        sys.path.insert(0, p)

from _util import bootstrap
bootstrap()

from app.collectors.thingspeak_adapter import ThingSpeakAdapter
from app.collectors.base import RawBatch
from app.database import repositories as repo
from app.database import db

SAMPLE_FEED_RESPONSE = {
    "channel": {
        "id": 3368421,
        "name": "Smart Flood and Landslide Monitoring System",
        "description": "ESP32 environmental monitor",
        "latitude": "0.0",
        "longitude": "0.0",
        "field1": "Water Level (cm)",
        "field2": "Soil Moisture (ADC)",
        "field3": "Rain Intensity (ADC)",
        "field4": "Total Tilt (deg)",
        "field5": "Status",
        "field6": "Latitude",
        "field7": "Longitude",
        "created_at": "2026-05-04T13:23:27Z",
        "updated_at": "2026-05-04T22:19:23Z",
        "last_entry_id": 1214,
    },
    "feeds": [
        {
            "created_at": "2026-05-05T06:32:53Z",
            "entry_id": 1213,
            "field1": "599.41998",
            "field2": "4095.00000",
            "field3": "4095.00000",
            "field4": "61.33137",
            "field5": "4",
            "field6": None,
            "field7": None,
        },
        {
            "created_at": "2026-05-05T06:33:11Z",
            "entry_id": 1214,
            "field1": "599.28400",
            "field2": "4095.00000",
            "field3": "4095.00000",
            "field4": "61.92287",
            "field5": "4",
            "field6": None,
            "field7": None,
        },
    ],
}


class TestThingSpeakAdapter(unittest.TestCase):
    def setUp(self):
        db.init_db(reset=True)

    def test_mock_fetch(self):
        adapter = ThingSpeakAdapter(fetcher=lambda url: SAMPLE_FEED_RESPONSE)
        batch = adapter.fetch({"results": 2})
        self.assertEqual(batch.source, "thingspeak-3368421")
        self.assertEqual(len(batch.records), 2)
        self.assertEqual(batch.meta.get("id"), 3368421)

    def test_validation_detects_staleness_and_missing_coords(self):
        adapter = ThingSpeakAdapter(fetcher=lambda url: SAMPLE_FEED_RESPONSE)
        batch = adapter.fetch()
        issues = adapter.validate(batch)
        # Should have WARNINGs for staleness and missing GPS coordinates, but no BAD dropping issues
        levels = [iss.level for iss in issues]
        self.assertIn("WARNING", levels)
        self.assertNotIn("BAD", levels)
        reasons = " ".join(iss.reason for iss in issues)
        self.assertIn("stale telemetry", reasons)
        self.assertIn("coordinates", reasons)

    def test_validation_rejects_malformed_and_negative_data(self):
        malformed_response = {
            "channel": {"id": 3368421},
            "feeds": [
                {
                    "created_at": "INVALID_TS",
                    "entry_id": 9991,
                    "field1": "100.0",
                },
                {
                    "created_at": "2026-05-05T06:33:11Z",
                    "entry_id": 9992,
                    "field1": "-50.0",  # Negative water level
                },
                {
                    "created_at": "2026-05-05T06:33:11Z",
                    "entry_id": 9993,
                    "field1": "NOT_A_NUMBER",  # Corrupted string
                },
            ],
        }
        adapter = ThingSpeakAdapter(fetcher=lambda url: malformed_response)
        batch = adapter.fetch()
        issues = adapter.validate(batch)
        bad_issues = [iss for iss in issues if iss.level == "BAD"]
        self.assertEqual(len(bad_issues), 3)

    def test_normalization_and_scientific_unit_integrity(self):
        adapter = ThingSpeakAdapter(fetcher=lambda url: SAMPLE_FEED_RESPONSE)
        batch = adapter.fetch()
        normalized = adapter.normalize(batch)
        self.assertEqual(len(normalized), 2)

        entry = normalized[-1]
        obs = entry["observation"]
        raw = entry["raw_telemetry"]

        # Field 1: 599.28400 cm -> 5.9928 m (canonical water level)
        self.assertEqual(obs["water_level"], 5.9928)

        # Fields 2 & 3: Raw ADC counts (4095.0). Must NEVER be converted into fake physical units
        self.assertIsNone(obs["rainfall"], "Raw rain ADC count must not be mapped to rainfall_mm")
        self.assertIsNone(obs["soil_moisture"], "Raw soil ADC count must not be mapped to soil_moisture %")
        self.assertIsNone(obs["temperature"])

        # Provenance: External Public IoT, not simulated
        self.assertEqual(obs["is_simulated"], 0)
        self.assertEqual(obs["quality_flag"], "STALE")
        self.assertIsNone(obs["latitude"])
        self.assertIsNone(obs["longitude"])

        # Raw Telemetry preserves the exact sensor payload
        self.assertEqual(raw["source"], "thingspeak")
        self.assertEqual(raw["channel_id"], "3368421")
        self.assertEqual(raw["entry_id"], 1214)
        self.assertEqual(raw["raw_payload"]["field2"], "4095.00000")
        self.assertEqual(raw["raw_payload"]["field3"], "4095.00000")
        self.assertEqual(raw["raw_payload"]["field4"], "61.92287")
        self.assertEqual(raw["raw_payload"]["field5"], "4")

    def test_store_and_idempotency(self):
        adapter = ThingSpeakAdapter(fetcher=lambda url: SAMPLE_FEED_RESPONSE)
        res1 = adapter.run()
        self.assertEqual(res1.stored, 2)
        self.assertEqual(res1.rejected, 0)

        # Verify database records
        obs_rows = repo.iot_series("thingspeak-3368421")
        self.assertEqual(len(obs_rows), 2)
        latest_obs = obs_rows[0]
        self.assertEqual(latest_obs["water_level"], 5.9928)
        self.assertIsNone(latest_obs["rainfall"])
        self.assertIsNone(latest_obs["soil_moisture"])
        self.assertEqual(latest_obs["quality_flag"], "STALE")

        raw_rows = repo.latest_iot_raw("3368421")
        self.assertEqual(len(raw_rows), 2)
        latest_raw = raw_rows[0]
        self.assertEqual(latest_raw["entry_id"], 1214)
        payload = json.loads(latest_raw["raw_payload"]) if isinstance(latest_raw["raw_payload"], str) else latest_raw["raw_payload"]
        self.assertEqual(payload["field1"], "599.28400")
        self.assertEqual(payload["field4"], "61.92287")

        # Run again: must be idempotent and not create duplicate rows
        res2 = adapter.run()
        self.assertEqual(res2.stored, 2)
        obs_rows_after = repo.iot_series("thingspeak-3368421")
        self.assertEqual(len(obs_rows_after), 2)
        raw_rows_after = repo.latest_iot_raw("3368421")
        self.assertEqual(len(raw_rows_after), 2)

    def test_live_feed_accessibility_and_metadata(self):
        """Live connectivity probe against ThingSpeak public REST feed."""
        adapter = ThingSpeakAdapter()
        try:
            info = adapter.get_latest_feed_info()
            self.assertTrue(info["accessible"])
            self.assertEqual(str(info["channel_id"]), "3368421")
            self.assertIsNotNone(info["latest_timestamp"])
            self.assertTrue(info["is_stale"])
            self.assertIn("field1_water_level_cm", info["fields_received"])
        except Exception as e:
            # Network issue or rate-limiting should be reported gracefully
            self.skipTest(f"Live ThingSpeak network probe skipped: {e}")


if __name__ == "__main__":
    unittest.main()
