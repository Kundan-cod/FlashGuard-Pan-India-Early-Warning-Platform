from datetime import datetime
from typing import Literal
from pydantic import BaseModel

class HistoricalEvent(BaseModel):
    event_id:str
    hazard:Literal["FLOOD","LANDSLIDE"]
    source:str
    event_time_start:datetime|None=None
    event_time_end:datetime|None=None
    geometry_ref:str|None=None
    state:str|None=None
    district:str|None=None
    source_quality:str="UNKNOWN"
    observation_coverage:str="UNKNOWN"
    notes:str|None=None

class TrainingLabel(BaseModel):
    spatial_unit_id:str
    hazard:Literal["FLOOD","LANDSLIDE"]
    target:int
    label_source:str
    label_confidence:float
    observation_coverage:float|None=None
    event_id:str|None=None
