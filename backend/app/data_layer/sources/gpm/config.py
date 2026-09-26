from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    gpm_api_base_url: str = os.getenv(
        "GPM_CMR_BASE_URL",
        os.getenv("GPM_API_BASE_URL", "https://cmr.earthdata.nasa.gov/search"),
    )
    provider: str = os.getenv("GPM_CMR_PROVIDER", "GES_DISC")
    short_name: str = os.getenv("GPM_CMR_SHORT_NAME", "GPM_3IMERGHHL")
    version: str = os.getenv("GPM_CMR_VERSION", "07")
    timeout_seconds: float = float(os.getenv("GPM_TIMEOUT_SECONDS", "30"))
    max_retries: int = int(os.getenv("GPM_MAX_RETRIES", "3"))
