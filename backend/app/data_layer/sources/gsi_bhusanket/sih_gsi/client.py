from __future__ import annotations
import httpx
from .config import GsiConfig

class BhusanketClient:
    """Safe portal client.

    The portal is used for discovery of publicly exposed bulletin/layer
    resources. No undocumented JSON API is assumed.
    """

    def __init__(self, config: GsiConfig | None = None, client: httpx.Client | None = None):
        self.config = config or GsiConfig()
        self.client = client or httpx.Client(timeout=self.config.timeout_seconds)

    def fetch_portal(self) -> str:
        r = self.client.get(self.config.base_url)
        r.raise_for_status()
        return r.text

    @staticmethod
    def extract_links(html: str) -> list[str]:
        import re
        return re.findall(r'https?://[^\"\'\s<>]+', html)
