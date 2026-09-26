from pydantic import BaseModel

class AdminKey(BaseModel):
    lgd_state_code: str | None = None
    lgd_district_code: str | None = None
    lgd_subdistrict_code: str | None = None
    lgd_block_code: str | None = None
    lgd_village_code: str | None = None
    lgd_ulb_code: str | None = None
    lgd_ward_code: str | None = None

class SpatialUnit(BaseModel):
    unit_id: str
    level: str
    name: str
    admin: AdminKey
    geometry_ref: str | None = None
    source_version: str | None = None
