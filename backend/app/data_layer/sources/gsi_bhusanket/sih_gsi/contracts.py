from typing import Literal
from pydantic import BaseModel, Field

class GsiLayer(BaseModel):
    name: str
    role: Literal[
        "landslide_inventory",
        "susceptibility",
        "impact_probability",
        "forecast_bulletin",
        "report"
    ]
    url: str
    public: bool = True
    geographic_scope: str = "UNKNOWN"

class LandslideInventoryRecord(BaseModel):
    source: Literal["GSI_BHUSANKET"] = "GSI_BHUSANKET"
    inventory_id: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    occurrence_date: str | None = None
    district: str | None = None
    state: str | None = None
    validation_status: str = "UNKNOWN"
    raw_reference: str | None = None

class GsiSourceHealth(BaseModel):
    source: Literal["GSI_BHUSANKET"] = "GSI_BHUSANKET"
    status: Literal["LIVE", "STALE", "ERROR", "NOT_CONFIGURED"]
    coverage_note: str
