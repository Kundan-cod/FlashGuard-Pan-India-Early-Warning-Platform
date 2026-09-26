from dataclasses import dataclass
import os

@dataclass(frozen=True)
class Settings:
    base_url: str = os.getenv(
        "IMD_API_BASE_URL",
        "https://api.imd.gov.in/api/v1"
    )
    timeout_seconds: float = float(os.getenv("IMD_TIMEOUT_SECONDS", "30"))
    max_retries: int = int(os.getenv("IMD_MAX_RETRIES", "3"))
    api_token: str = os.getenv("IMD_API_TOKEN", "")
