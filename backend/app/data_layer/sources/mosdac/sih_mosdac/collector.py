from __future__ import annotations

from datetime import date
from typing import Any
import time
import httpx

from .config import MosdacConfig
from .contracts import MosdacGranule, MosdacSearchRequest

class MosdacCollector:
    """Adapter for the documented MOSDAC mdapi search/download workflow.

    MOSDAC intentionally exposes a configuration-driven client. The exact
    service URL is not hard-coded here because the current public manual
    documents the client/config contract rather than a stable public endpoint
    to be embedded by third-party applications.
    """

    def __init__(self, config: MosdacConfig | None = None, client: httpx.Client | None = None):
        self.config = config or MosdacConfig()
        self.client = client or httpx.Client(timeout=self.config.timeout_seconds)

    @staticmethod
    def build_search_config(req: MosdacSearchRequest) -> dict[str, Any]:
        box = ""
        if req.bounding_box:
            box = ",".join(str(v) for v in req.bounding_box)
        return {
            "datasetId": req.dataset_id,
            "startTime": req.start_time.isoformat() if req.start_time else "",
            "endTime": req.end_time.isoformat() if req.end_time else "",
            "count": str(req.count) if req.count is not None else "",
            "boundingBox": box,
            "gId": req.granule_id or "",
        }

    def validate_download_ready(self) -> None:
        if not self.config.username or not self.config.password:
            raise RuntimeError(
                "MOSDAC download requires configured MOSDAC credentials. "
                "Search configuration can be prepared without credentials."
            )

    def search(self, config: dict[str, Any]) -> list[dict[str, Any]]:
        """Search MOSDAC catalog via the documented apios/datasets.json endpoint."""
        base = (self.config.api_base_url or "https://mosdac.gov.in").rstrip("/")
        url = f"{base}/apios/datasets.json"
        params = {k: v for k, v in config.items() if v}
        try:
            resp = self.client.get(url, params=params)
            if resp.status_code == 200:
                data = resp.json()
                return data.get("entries", [])
            return []
        except Exception:
            return []

    def normalize_search_items(self, dataset_id: str, items: list[dict[str, Any]]) -> list[MosdacGranule]:
        result = []
        for item in items:
            gid = item.get("gId") or item.get("granuleId") or item.get("id")
            title = item.get("title") or item.get("name") or item.get("identifier")
            st = item.get("startTime") or item.get("updated")
            et = item.get("endTime") or item.get("updated")
            url = item.get("downloadUrl") or item.get("url") or item.get("enclosureLink")
            result.append(MosdacGranule(
                dataset_id=dataset_id,
                granule_id=str(gid) if gid else None,
                title=title,
                start_time=st,
                end_time=et,
                download_url=url,
                metadata=item,
            ))
        return result
