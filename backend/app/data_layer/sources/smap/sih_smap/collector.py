from __future__ import annotations

from datetime import datetime
from typing import Any
import time
import httpx

from .config import SmapConfig
from .contracts import SmapGranule

class SmapCollector:
    """CMR discovery adapter for NASA SMAP L4 V008.

    It discovers granules and their documented GETDATA URLs. It intentionally
    does not convert metadata into fake numeric soil-moisture observations.
    """

    def __init__(self, config: SmapConfig | None = None, client: httpx.Client | None = None):
        self.config = config or SmapConfig()
        self.client = client or httpx.Client(timeout=self.config.timeout_seconds)

    def _get(self, path: str, params: dict[str, Any]) -> dict[str, Any]:
        last = None
        for attempt in range(self.config.max_retries):
            try:
                r = self.client.get(f"{self.config.cmr_base_url}/{path}", params=params)
                r.raise_for_status()
                data = r.json()
                if not isinstance(data, dict):
                    raise ValueError("CMR response is not a JSON object")
                return data
            except Exception as exc:
                last = exc
                if attempt + 1 < self.config.max_retries:
                    time.sleep(0.5 * (2 ** attempt))
        raise RuntimeError(f"SMAP CMR request failed: {last}") from last

    def search_granules(
        self,
        *,
        start: datetime | None = None,
        end: datetime | None = None,
        point: tuple[float, float] | None = None,
        bounding_box: tuple[float, float, float, float] | None = None,
        downloadable: bool = True,
        page_size: int = 20,
    ) -> list[SmapGranule]:
        params: dict[str, Any] = {
            "short_name": self.config.short_name,
            "version": self.config.version,
            "page_size": page_size,
            "provider": self.config.provider,
            "sort_key[]": "-start_date",
            "downloadable": "true" if downloadable else "false",
        }
        if start or end:
            a = start.isoformat().replace("+00:00", "Z") if start else ""
            b = end.isoformat().replace("+00:00", "Z") if end else ""
            params["temporal[]"] = f"{a},{b}"
        if point:
            lon, lat = point
            params["point"] = f"{lon},{lat}"
        if bounding_box:
            west, south, east, north = bounding_box
            params["bounding_box"] = f"{west},{south},{east},{north}"

        payload = self._get("granules.json", params)
        out: list[SmapGranule] = []
        for item in payload.get("items", []):
            concept_id = item.get("meta", {}).get("concept-id") or item.get("concept_id")
            if not concept_id:
                continue
            urls: list[str] = []
            for link in item.get("umm", {}).get("RelatedUrls", []):
                if link.get("Type") == "GET DATA" and link.get("URL"):
                    urls.append(link["URL"])
            title = item.get("umm", {}).get("EntryTitle")
            temporal = item.get("umm", {}).get("TemporalExtents", [])
            begin = end_time = None
            if temporal:
                rng = temporal[0].get("RangeDateTime", {})
                begin = rng.get("BeginningDateTime")
                end_time = rng.get("EndingDateTime")
            out.append(SmapGranule(
                concept_id=concept_id,
                producer_granule_id=item.get("umm", {}).get("ProducerGranuleId"),
                title=title,
                start_time=begin,
                end_time=end_time,
                downloadable_urls=urls,
                metadata=item,
            ))
        return out
