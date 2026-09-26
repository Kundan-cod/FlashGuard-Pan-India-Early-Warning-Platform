from typing import Literal
from pydantic import BaseModel

class AdministrativeUnit(BaseModel):
    lgd_code:str
    name:str
    level:Literal[
        "STATE_UT","DISTRICT","SUBDISTRICT","BLOCK",
        "VILLAGE","PRI_LOCAL_BODY","URBAN_LOCAL_BODY","WARD"
    ]
    parent_lgd_code:str|None=None
    state_lgd_code:str|None=None
    district_lgd_code:str|None=None
    active:bool=True
    source:"str"="LGD"

class AdminHierarchy(BaseModel):
    state_code:str
    district_code:str|None=None
    subdistrict_code:str|None=None
    block_code:str|None=None
    village_code:str|None=None
    ulb_code:str|None=None
    ward_code:str|None=None
