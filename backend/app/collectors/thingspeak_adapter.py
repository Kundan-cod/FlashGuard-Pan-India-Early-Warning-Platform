"""
ThingSpeak External Public IoT Adapter (Section: External Public IoT).

Ingests real-time/historical telemetry from public ThingSpeak channel 3368421:
https://thingspeak.mathworks.com/channels/3368421

Architecture pipeline:
ThingSpeak -> External IoT Adapter -> Validation + QC -> Normalization -> PostgreSQL/PostGIS -> Feature Engine -> Flood/Landslide ML -> Risk Engine

Provenance & Classification:
- Source: EXTERNAL_PUBLIC_IOT
- Channel ID: 3368421 (preserved)
- Feed timestamps: preserved verbatim in UTC ISO-8601
- NOT a FlashGuard-deployed sensor
- NOT government infrastructure
- Public REST feed: https://api.thingspeak.com/channels/3368421/feeds.json (No Read API Key required)

Scientific Unit Rules & Honesty:
- Field 1 (Water Level cm): Converted to canonical metres (m = cm * 0.01)
- Field 2 (Soil Moisture ADC): Stored in raw telemetry ONLY. NOT converted to % or ML feature.
- Field 3 (Rain Intensity ADC): Stored in raw telemetry ONLY. NOT converted to mm/hr or ML feature.
- Field 4 (Total Tilt deg): Stored in raw telemetry. NOT mapped to DEM terrain slope.
- Field 5 (Status): Stored in raw telemetry.
- Field 6 & 7 (Lat/Lon): Flagged by check_geo; stored as NULL if invalid/missing.
"""
from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
from datetime import datetime, timezone
from typing import Any, Callable

from app.collectors.base import (
    BaseCollector,
    Issue,
    RawBatch,
    StoreResult,
    utcnow_iso,
)
from app.database import repositories as repo
from app.processing.normalize import to_utc_iso
from app.processing.validate import LAT_MAX, LAT_MIN, LON_MAX, LON_MIN, is_stale, parse_ts

logger = logging.getLogger("flashguard.iot.thingspeak")

DEFAULT_CHANNEL_ID = "3368421"
DEFAULT_FEED_URL = f"https://api.thingspeak.com/channels/{DEFAULT_CHANNEL_ID}/feeds.json"


def _num(v: Any) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class ThingSpeakAdapter(BaseCollector):
    """External Public IoT Adapter for ThingSpeak Channels."""

    source_key: str = "thingspeak-3368421"
    realtime_class: str = "external_public_iot"

    def __init__(
        self,
        channel_id: str = DEFAULT_CHANNEL_ID,
        feed_url: str | None = None,
        fetcher: Callable[[str], dict] | None = None,
    ) -> None:
        self.channel_id = str(channel_id)
        self.source_key = f"thingspeak-{self.channel_id}"
        self.feed_url = feed_url or f"https://api.thingspeak.com/channels/{self.channel_id}/feeds.json"
        self._fetcher = fetcher

    def fetch(self, window: dict | None = None) -> RawBatch:
        """Pulls JSON feed from public ThingSpeak REST API without requiring an API key."""
        results = 10
        if window and "results" in window:
            results = int(window["results"])
        url = f"{self.feed_url}?results={results}"

        if self._fetcher is not None:
            data = self._fetcher(url)
        else:
            req = urllib.request.Request(
                url,
                headers={"User-Agent": "FlashGuard-ExternalIoT/1.0", "Accept": "application/json"},
            )
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw_bytes = resp.read()
                    data = json.loads(raw_bytes.decode("utf-8"))
            except urllib.error.HTTPError as e:
                raise RuntimeError(f"ThingSpeak HTTP error {e.code}: {e.reason}") from e
            except urllib.error.URLError as e:
                raise RuntimeError(f"ThingSpeak connection error: {e.reason}") from e

        channel_meta = data.get("channel", {})
        feeds = data.get("feeds", [])
        return RawBatch(
            source=self.source_key,
            fetched_at=utcnow_iso(),
            records=feeds,
            meta=channel_meta,
        )

    def validate(self, raw: RawBatch) -> list[Issue]:
        """Validates timestamp, coordinates, and physical bounds. Flags staleness."""
        issues: list[Issue] = []
        for i, rec in enumerate(raw.records):
            # 1. Timestamp validation
            ts_str = rec.get("created_at")
            dt = parse_ts(ts_str)
            if not dt:
                issues.append(Issue(level="BAD", reason="missing or unparseable created_at timestamp", record_index=i))
                continue

            # 2. Staleness check (flagged as WARNING so historical feeds can be ingested)
            if is_stale(ts_str, max_age_minutes=60.0):
                issues.append(Issue(level="WARNING", reason=f"stale telemetry: timestamp {ts_str} > 60m old", record_index=i))

            # 3. Water level sanity check (Field 1: cm)
            wl_raw = rec.get("field1")
            wl_cm = _num(wl_raw)
            if wl_raw is not None and wl_cm is None:
                issues.append(Issue(level="BAD", reason=f"malformed non-numeric field1 water level '{wl_raw}'", record_index=i))
            elif wl_cm is not None and wl_cm < 0:
                issues.append(Issue(level="BAD", reason=f"negative water level {wl_cm} cm", record_index=i))

            # 4. Coordinates sanity check (Fields 6 & 7)
            lat = _num(rec.get("field6"))
            lon = _num(rec.get("field7"))
            if lat is None or lon is None:
                issues.append(Issue(level="WARNING", reason="missing/unconfigured GPS coordinates in field6/field7", record_index=i))
            elif not (LAT_MIN <= lat <= LAT_MAX and LON_MIN <= lon <= LON_MAX):
                issues.append(Issue(level="WARNING", reason=f"coordinates ({lat}, {lon}) outside India bounding box", record_index=i))

        return issues

    def normalize(self, raw: RawBatch) -> list[dict]:
        """Normalizes Field 1 (cm -> m), leaves ADC fields unmapped to ML, and preserves raw payload."""
        out: list[dict] = []
        for rec in raw.records:
            ts_iso = to_utc_iso(rec["created_at"])
            stale = is_stale(rec["created_at"], max_age_minutes=60.0)

            # Field 1: Water Level cm -> canonical metres
            wl_cm = _num(rec.get("field1"))
            wl_m = round(wl_cm * 0.01, 4) if wl_cm is not None else None

            # Fields 6 & 7: Coordinates
            lat = _num(rec.get("field6"))
            lon = _num(rec.get("field7"))
            valid_geo = (
                lat is not None
                and lon is not None
                and (LAT_MIN <= lat <= LAT_MAX)
                and (LON_MIN <= lon <= LON_MAX)
            )
            canonical_lat = lat if valid_geo else None
            canonical_lon = lon if valid_geo else None

            # Scientific Honesty:
            # - Field 2 (Soil Moisture ADC: 4095.0) -> NOT converted to %, stored in raw only
            # - Field 3 (Rain Intensity ADC: 4095.0) -> NOT converted to mm/hr, stored in raw only
            # - Field 4 (Total Tilt deg) -> hardware tilt, NOT DEM slope
            # - Field 5 (Status) -> firmware code
            canonical_obs = {
                "sensor_id": self.source_key,
                "ts": ts_iso,
                "latitude": canonical_lat,
                "longitude": canonical_lon,
                "water_level": wl_m,
                "rainfall": None,         # Strictly None (no calibration formula)
                "soil_moisture": None,    # Strictly None (no calibration formula)
                "temperature": None,
                "quality_flag": "STALE" if stale else "GOOD",
                "is_simulated": 0,        # External Public IoT is NOT simulated
            }

            raw_item = {
                "source": "thingspeak",
                "channel_id": self.channel_id,
                "entry_id": int(rec["entry_id"]),
                "ts": ts_iso,
                "raw_payload": rec,
                "quality_flag": "STALE" if stale else "GOOD",
            }

            out.append({
                "observation": canonical_obs,
                "raw_telemetry": raw_item,
                **canonical_obs,
            })
        return out

    def store(self, observations: list[dict]) -> StoreResult:
        """Idempotently persists canonical observations into iot_observations and full payload into iot_raw_telemetry."""
        stored = 0
        for item in observations:
            obs = item.get("observation", item)
            raw = item.get("raw_telemetry")
            repo.upsert_iot(obs)
            if raw:
                repo.upsert_iot_raw(raw)
            stored += 1
        return StoreResult(received=len(observations), stored=stored, rejected=0)

    def get_latest_feed_info(self) -> dict:
        """Utility to retrieve latest feed metadata, values, freshness, and scientific units."""
        raw = self.fetch({"results": 1})
        if not raw.records:
            return {"accessible": True, "entries_count": 0, "status": "empty"}

        latest = raw.records[-1]
        ts_str = latest.get("created_at")
        stale = is_stale(ts_str, max_age_minutes=60.0) if ts_str else True

        return {
            "accessible": True,
            "channel_id": self.channel_id,
            "channel_name": raw.meta.get("name"),
            "latest_entry_id": latest.get("entry_id"),
            "latest_timestamp": ts_str,
            "is_stale": stale,
            "fields_received": {
                "field1_water_level_cm": latest.get("field1"),
                "field2_soil_moisture_adc": latest.get("field2"),
                "field3_rain_intensity_adc": latest.get("field3"),
                "field4_total_tilt_deg": latest.get("field4"),
                "field5_status": latest.get("field5"),
                "field6_latitude": latest.get("field6"),
                "field7_longitude": latest.get("field7"),
            },
        }
