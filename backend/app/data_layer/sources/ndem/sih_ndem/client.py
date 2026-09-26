from __future__ import annotations
import httpx
from .config import NdemConfig

class NdemClient:
    """Public portal discovery only.

    Protected NDEM products are deliberately not scraped or bypassed.
    An authorized API adapter can be added later without changing the
    normalized source-health contract.
    """
    def __init__(self,config:NdemConfig|None=None,client:httpx.Client|None=None):
        self.config=config or NdemConfig()
        self.client=client or httpx.Client(timeout=self.config.timeout_seconds)

    def check_public_portal(self)->str:
        r=self.client.get(self.config.base_url)
        r.raise_for_status()
        return r.text

    def access_state(self)->str:
        if self.config.username and self.config.password:
            return "AUTHORIZED_CONFIGURED"
        return "PUBLIC_ONLY"
