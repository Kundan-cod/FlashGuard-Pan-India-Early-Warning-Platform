from pydantic import BaseModel, Field
from typing import Any

class RainfallObservation(BaseModel):
    source: str
    product: str
    observed_date: str
    latitude: float
    longitude: float
    resolution: str = "0.1 degree"
    unit: str = "mm accumulation"
    value: float | None = None
    source_metadata: dict[str, Any] = Field(default_factory=dict)
