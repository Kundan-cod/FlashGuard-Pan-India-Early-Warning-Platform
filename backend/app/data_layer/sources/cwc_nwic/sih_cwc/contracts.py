from datetime import datetime
from typing import Literal
from pydantic import BaseModel

class NwdpResource(BaseModel):
    title:str
    resource_url:str
    format:str|None=None
    description:str|None=None

class RiverWaterLevelObservation(BaseModel):
    source:Literal["CWC_NWIC"]="CWC_NWIC"
    station_id:str|None=None
    station_name:str|None=None
    river:str|None=None
    timestamp:datetime
    water_level_m:float|None=None
    latitude:float|None=None
    longitude:float|None=None
    quality_flag:str="UNKNOWN"
    source_reference:str|None=None

class CwcRainfallObservation(BaseModel):
    source:Literal["CWC_NWIC"]="CWC_NWIC"
    station_id:str|None=None
    timestamp:datetime
    rainfall_mm:float|None=None
    latitude:float|None=None
    longitude:float|None=None
    quality_flag:str="UNKNOWN"
    source_reference:str|None=None
