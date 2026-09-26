from datetime import datetime
from typing import Any, Literal
from pydantic import BaseModel, Field

class SmapGranule(BaseModel):
    concept_id: str
    producer_granule_id: str | None = None
    title: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    downloadable_urls: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

class SoilMoistureObservation(BaseModel):
    source: Literal["NASA_SMAP"] = "NASA_SMAP"
    product: str
    version: str
    observation_time: datetime
    latitude: float
    longitude: float
    surface_soil_moisture_m3_m3: float | None = None
    rootzone_soil_moisture_m3_m3: float | None = None
    quality_flag: str = "UNKNOWN"
    source_granule_id: str | None = None
    source_url: str | None = None
    raw_reference: str | None = None
