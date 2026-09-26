from datetime import date
from typing import Any, Literal
from pydantic import BaseModel, Field

class MosdacSearchRequest(BaseModel):
    dataset_id: str = Field(min_length=1)
    start_time: date | None = None
    end_time: date | None = None
    count: int | None = Field(default=None, ge=1, le=100)
    bounding_box: tuple[float, float, float, float] | None = None
    granule_id: str | None = None

class MosdacGranule(BaseModel):
    dataset_id: str
    granule_id: str | None = None
    title: str | None = None
    start_time: str | None = None
    end_time: str | None = None
    download_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

class MosdacSourceHealth(BaseModel):
    source: Literal["ISRO_MOSDAC"] = "ISRO_MOSDAC"
    status: Literal["LIVE", "STALE", "ERROR", "NOT_CONFIGURED"]
    authenticated: bool
    detail: str | None = None
