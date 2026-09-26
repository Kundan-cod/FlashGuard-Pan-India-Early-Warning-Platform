from dataclasses import dataclass
import os

@dataclass(frozen=True)
class BhuvanConfig:
    wms_url: str = os.getenv("BHUVAN_WMS_URL", "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms")
    wmts_url: str = os.getenv("BHUVAN_WMTS_URL", "https://bhuvan-vec2.nrsc.gov.in/bhuvan/gwc/service/wmts")
    timeout_seconds: float = float(os.getenv("BHUVAN_WMS_TIMEOUT_SECONDS", "30"))
    max_retries: int = int(os.getenv("BHUVAN_MAX_RETRIES", "3"))
