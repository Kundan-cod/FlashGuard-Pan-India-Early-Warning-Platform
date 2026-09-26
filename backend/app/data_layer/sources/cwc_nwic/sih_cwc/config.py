from dataclasses import dataclass
import os
@dataclass(frozen=True)
class NwicConfig:
    base_url:str=os.getenv("NWDP_BASE_URL","https://www.nwdp.nwic.gov.in")
    timeout_seconds:float=float(os.getenv("NWDP_TIMEOUT_SECONDS","30"))
    max_retries:int=int(os.getenv("NWDP_MAX_RETRIES","3"))
