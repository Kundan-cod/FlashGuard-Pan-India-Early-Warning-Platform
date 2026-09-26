from __future__ import annotations
import httpx
from .config import LgdConfig

class LgdClient:
    """Thin client for the official LGD download portal.

    The portal is configuration-driven because download options are exposed
    through the official web application. The adapter does not guess file
    names or fabricate geometry URLs.
    """
    def __init__(self,config:LgdConfig|None=None,client:httpx.Client|None=None):
        self.config=config or LgdConfig()
        self.client=client or httpx.Client(timeout=self.config.timeout_seconds)

    def fetch_directory_page(self)->str:
        r=self.client.get(self.config.download_url)
        r.raise_for_status()
        return r.text
