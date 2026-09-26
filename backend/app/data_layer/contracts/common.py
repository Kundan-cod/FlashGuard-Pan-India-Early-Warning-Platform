from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field

class SourceStatus(str, Enum):
    LIVE = "LIVE"
    NRT = "NRT"
    STALE = "STALE"
    ERROR = "ERROR"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    REPLAY = "REPLAY"
    SIMULATED = "SIMULATED"

class ObservationQuality(BaseModel):
    status: SourceStatus = SourceStatus.LIVE
    quality_flag: str = "UNKNOWN"
    observed_at: datetime | None = None
    ingested_at: datetime | None = None
    stale_after_seconds: int | None = None
    message: str | None = None

class NormalizedObservation(BaseModel):
    source: str
    source_record_id: str | None = None
    observation_time: datetime
    latitude: float | None = None
    longitude: float | None = None
    value: float | None = None
    unit: str | None = None
    variable: str
    quality: ObservationQuality = Field(default_factory=ObservationQuality)
    raw_reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
