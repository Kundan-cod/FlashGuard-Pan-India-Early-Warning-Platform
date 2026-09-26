from __future__ import annotations
import re
import httpx
from .config import NwicConfig
from .contracts import NwdpResource

class NwdpClient:
    def __init__(self,config:NwicConfig|None=None,client:httpx.Client|None=None):
        self.config=config or NwicConfig()
        self.client=client or httpx.Client(timeout=self.config.timeout_seconds)

    def fetch_dataset_page(self,path:str)->str:
        url=self.config.base_url.rstrip("/") + path
        r=self.client.get(url)
        r.raise_for_status()
        return r.text

    @staticmethod
    def extract_resource_links(html:str)->list[str]:
        return sorted(set(re.findall(r'href=["\'](https?://[^"\']+)["\']',html)))

    @staticmethod
    def normalize_resources(items:list[dict])->list[NwdpResource]:
        return [NwdpResource(**x) for x in items]
