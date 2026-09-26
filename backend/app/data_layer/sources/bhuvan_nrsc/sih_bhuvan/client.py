from __future__ import annotations

import httpx
from .config import BhuvanConfig
from .contracts import WmsRequest

class BhuvanWmsClient:
    """Small OGC WMS client for Bhuvan thematic/context layers."""

    def __init__(self, config: BhuvanConfig | None = None, client: httpx.Client | None = None):
        self.config = config or BhuvanConfig()
        self.client = client or httpx.Client(timeout=self.config.timeout_seconds)

    def get_map(self, req: WmsRequest) -> bytes:
        minx, miny, maxx, maxy = req.bbox
        params = {
            "SERVICE": "WMS",
            "VERSION": "1.1.1",
            "REQUEST": "GetMap",
            "LAYERS": req.layer,
            "SRS": req.crs,
            "BBOX": f"{minx},{miny},{maxx},{maxy}",
            "WIDTH": req.width,
            "HEIGHT": req.height,
            "FORMAT": req.image_format,
        }
        r = self.client.get(self.config.wms_url, params=params)
        r.raise_for_status()
        return r.content
