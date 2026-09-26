from dataclasses import dataclass
import os
@dataclass(frozen=True)
class LgdConfig:
    download_url:str=os.getenv(
        "LGD_DOWNLOAD_BASE_URL",
        "https://lgdirectory.gov.in/demo/downloadDirectory.do"
    )
    timeout_seconds:float=float(os.getenv("LGD_TIMEOUT_SECONDS","60"))
    max_retries:int=int(os.getenv("LGD_MAX_RETRIES","3"))
