from dataclasses import dataclass
import os

@dataclass(frozen=True)
class GsiConfig:
    base_url: str = os.getenv("GSI_BHUSANKET_BASE_URL", "https://bhusanket.gsi.gov.in")
    timeout_seconds: float = float(os.getenv("GSI_TIMEOUT_SECONDS", "30"))
    max_retries: int = int(os.getenv("GSI_MAX_RETRIES", "3"))
