from typing import Literal
from pydantic import BaseModel, Field

class WmsRequest(BaseModel):
    layer: str = Field(min_length=1)
    bbox: tuple[float, float, float, float]
    width: int = Field(default=1024, ge=1, le=4096)
    height: int = Field(default=1024, ge=1, le=4096)
    crs: str = "EPSG:4326"
    image_format: str = "image/png"

class TerrainFeature(BaseModel):
    latitude: float
    longitude: float
    elevation_m: float | None = None
    slope_deg: float | None = None
    aspect_deg: float | None = None
    curvature: float | None = None
    source: Literal["BHUVAN_CARTODEM"] = "BHUVAN_CARTODEM"
    quality_flag: str = "UNKNOWN"

class BhuvanLayer(BaseModel):
    name: str
    service_type: Literal["WMS", "WMTS"]
    url: str
    role: str
