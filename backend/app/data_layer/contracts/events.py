from datetime import datetime
from pydantic import BaseModel, Field

class HistoricalEvent(BaseModel):
    event_id: str
    hazard: str
    source: str
    start_time: datetime | None = None
    end_time: datetime | None = None
    geometry_ref: str | None = None
    confidence: float = Field(default=1.0, ge=0, le=1)
    observation_coverage: float | None = Field(default=None, ge=0, le=1)
    notes: str | None = None
