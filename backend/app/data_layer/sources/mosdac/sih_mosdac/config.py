from dataclasses import dataclass
import os

@dataclass(frozen=True)
class MosdacConfig:
    api_base_url: str = os.getenv("MOSDAC_API_BASE_URL", "")
    username: str | None = os.getenv("MOSDAC_USERNAME") or None
    password: str | None = os.getenv("MOSDAC_PASSWORD") or None
    timeout_seconds: float = float(os.getenv("MOSDAC_TIMEOUT_SECONDS", "60"))
    max_retries: int = int(os.getenv("MOSDAC_MAX_RETRIES", "3"))
    download_path: str = os.getenv("MOSDAC_DOWNLOAD_PATH", "./data/raw/mosdac")
