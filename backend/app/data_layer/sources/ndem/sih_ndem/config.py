from dataclasses import dataclass
import os

@dataclass(frozen=True)
class NdemConfig:
    base_url:str=os.getenv("NDEM_BASE_URL","https://ndem.nrsc.gov.in")
    timeout_seconds:float=float(os.getenv("NDEM_TIMEOUT_SECONDS","30"))
    max_retries:int=int(os.getenv("NDEM_MAX_RETRIES","3"))
    username:str|None=os.getenv("NDEM_USERNAME") or None
    password:str|None=os.getenv("NDEM_PASSWORD") or None
