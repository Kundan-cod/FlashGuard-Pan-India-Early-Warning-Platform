from typing import Literal
from pydantic import BaseModel

class NdemCapability(BaseModel):
    name:str
    access:Literal["PUBLIC","AUTHORIZED"]
    role:str
    source_url:str

class NdemSourceHealth(BaseModel):
    source:Literal["NDEM"]="NDEM"
    status:Literal["AVAILABLE","AUTH_REQUIRED","ERROR","NOT_CONFIGURED"]
    access_level:Literal["PUBLIC","AUTHORIZED","UNKNOWN"]
    detail:str|None=None
