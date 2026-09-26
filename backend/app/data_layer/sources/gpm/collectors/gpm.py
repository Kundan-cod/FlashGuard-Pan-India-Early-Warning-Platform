from __future__ import annotations

import os
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx

from ..config import Settings
from ..contracts import RainfallObservation
from .base import BaseCollector, CollectorError


def _iso_z(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class GPMCollector(BaseCollector):
    """Collector for NASA GPM IMERG using NASA CMR (Common Metadata Repository)
    UMM-JSON granule search API.
    """

    ALLOWED_PRODUCTS = {
        "GPM_3IMERGHHL",
        "GPM_3IMERGDF",
        "GPM_3IMERGM",
        "precip_30mn",
        "precip_1d",
    }

    def __init__(self, settings: Settings | None = None,
                 client: httpx.Client | None = None):
        self.settings = settings or Settings()
        self._client = client or httpx.Client(
            timeout=self.settings.timeout_seconds
        )

    def _params(
        self,
        product: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        point: str | None = None,
        bounding_box: str | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        days: int = 14,
        limit: int = 10,
        provider: str | None = None,
        version: str | None = None,
    ) -> dict[str, Any]:
        short_name = product or self.settings.short_name
        # normalize legacy product name if passed
        if short_name in ("precip_30mn", "precip_1d"):
            short_name = "GPM_3IMERGHHL"

        if not 1 <= limit <= 1000:
            raise ValueError("limit must be between 1 and 1000")

        params: dict[str, Any] = {
            "provider": provider or self.settings.provider,
            "short_name": short_name,
            "version": version or self.settings.version,
            "downloadable": "true",
            "page_size": limit,
            "sort_key[]": "-start_date",
        }

        # Spatial constraint: CMR accepts point="lon,lat"
        if point:
            params["point"] = point
        elif longitude is not None and latitude is not None:
            if not -90 <= latitude <= 90:
                raise ValueError("latitude must be between -90 and 90")
            if not -180 <= longitude <= 180:
                raise ValueError("longitude must be between -180 and 180")
            params["point"] = f"{longitude},{latitude}"
        elif bounding_box:
            params["bounding_box"] = bounding_box

        # Temporal window: CMR accepts temporal[]="start,end"
        if start_date and end_date:
            params["temporal[]"] = f"{start_date},{end_date}"
        elif start_date:
            params["temporal[]"] = f"{start_date},"
        else:
            now = datetime.now(timezone.utc)
            start = now - timedelta(days=days)
            params["temporal[]"] = f"{_iso_z(start)},{_iso_z(now)}"

        return params

    def fetch(self, **kwargs: Any) -> dict[str, Any]:
        params = self._params(**kwargs)
        base = self.settings.gpm_api_base_url.rstrip("/")
        endpoint = base if base.endswith(".json") else f"{base}/granules.umm_json"

        token = (os.environ.get("NASA_EARTHDATA_TOKEN") or "").strip()
        headers = {"Authorization": f"Bearer {token}"} if token else {}

        last_error: Exception | None = None
        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self._client.get(
                    endpoint,
                    params=params,
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
                self.validate(payload)
                return payload
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    break
                time.sleep(min(2 ** attempt, 8))

        raise CollectorError(
            f"GPM CMR request failed after retries: {last_error}"
        )

    def search(
        self,
        product: str = "GPM_3IMERGHHL",
        latitude: float | None = None,
        longitude: float | None = None,
        start_date: str | None = None,
        end_date: str | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return self.fetch(
            product=product,
            latitude=latitude,
            longitude=longitude,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
            **kwargs,
        )

    def validate(self, payload: Any) -> None:
        if not isinstance(payload, dict):
            raise ValueError("GPM response must be a JSON object")
        if "items" not in payload:
            raise ValueError("GPM response is missing 'items'")
        if not isinstance(payload["items"], list):
            raise ValueError("GPM response 'items' must be a list")

    @staticmethod
    def extract_downloads(item: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract ONLY verified GET DATA URLs returned by CMR.
        Never constructs a GES DISC file URL manually.
        """
        downloads = []
        # CMR UMM-JSON structure
        umm = item.get("umm", {}) if isinstance(item, dict) else {}
        meta = item.get("meta", {}) if isinstance(item, dict) else {}
        concept_id = meta.get("concept-id") or item.get("@id")

        related_urls = umm.get("RelatedUrls", []) or []
        for r in related_urls:
            url = r.get("URL")
            if r.get("Type") == "GET DATA" and url and url.startswith("http"):
                downloads.append({
                    "id": concept_id,
                    "url": url,
                    "media_type": r.get("MimeType"),
                    "type": "GET DATA",
                    "description": r.get("Description"),
                })

        # Backward compatibility for legacy tests or PMM item shapes:
        if not downloads and "action" in item:
            for action in item.get("action", []):
                if action.get("@type") != "ojo:download":
                    continue
                for request in action.get("using", []):
                    u = request.get("url")
                    if u and u.startswith("http"):
                        downloads.append({
                            "id": request.get("@id") or concept_id,
                            "url": u,
                            "media_type": request.get("mediaType"),
                            "type": "GET DATA",
                            "display_name": request.get("displayName"),
                        })

        return downloads

    def normalize(self, payload: dict[str, Any]) -> list[RainfallObservation]:
        self.validate(payload)
        normalized = []

        for item in payload["items"]:
            umm = item.get("umm", {})
            meta = item.get("meta", {})
            props = item.get("properties", {})
            granule_ur = umm.get("GranuleUR") or item.get("@id") or "unknown"
            concept_id = meta.get("concept-id") or item.get("@id")

            temporal = umm.get("TemporalExtent", {}).get("RangeDateTime", {})
            obs_date = temporal.get("BeginningDateTime") or props.get("date", {}).get("@value", "")

            downloads = self.extract_downloads(item)
            if not downloads:
                continue

            normalized.append(
                RainfallObservation(
                    source="NASA_GPM",
                    product=umm.get("CollectionReference", {}).get("ShortName", "GPM_3IMERGHHL"),
                    observed_date=obs_date,
                    latitude=0.0,
                    longitude=0.0,
                    resolution="0.1 degree",
                    source_metadata={
                        "concept_id": concept_id,
                        "granule_ur": granule_ur,
                        "downloads": downloads,
                        "retrieved_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
            )

        return normalized
