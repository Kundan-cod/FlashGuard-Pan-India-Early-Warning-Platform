from dataclasses import dataclass
import os

@dataclass(frozen=True)
class SmapConfig:
    cmr_base_url: str = os.getenv("SMAP_CMR_BASE_URL", "https://cmr.earthdata.nasa.gov/search")
    short_name: str = os.getenv("SMAP_COLLECTION_SHORT_NAME", "SPL4SMAU")
    version: str = os.getenv("SMAP_COLLECTION_VERSION", "008")
    provider: str = os.getenv("SMAP_PROVIDER", "NSIDC_CPRD")
    timeout_seconds: float = float(os.getenv("SMAP_TIMEOUT_SECONDS", "30"))
    max_retries: int = int(os.getenv("SMAP_MAX_RETRIES", "3"))
    earthdata_token: str | None = os.getenv("EARTHDATA_TOKEN") or None
