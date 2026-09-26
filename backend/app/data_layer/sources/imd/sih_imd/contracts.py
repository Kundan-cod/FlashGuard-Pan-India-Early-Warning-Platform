from typing import Any
from pydantic import BaseModel, Field

class IMDCurrentWeather(BaseModel):
    station_id: str | None = None
    station: str | None = None
    observation_date: str | None = None
    observation_time_utc: str | None = None
    temperature_c: float | None = None
    humidity_pct: float | None = None
    wind_speed_kmph: float | None = None
    wind_direction_code: float | None = None
    pressure_hpa: float | None = None
    rainfall_24h_mm: float | None = None
    weather_code: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

class IMDDistrictRainfall(BaseModel):
    district_id: str | None = None
    district: str | None = None
    date: str | None = None
    daily_actual_mm: float | None = None
    daily_normal_mm: float | None = None
    daily_departure_pct: float | None = None
    daily_category: str | None = None
    cumulative_actual_mm: float | None = None
    cumulative_normal_mm: float | None = None
    cumulative_departure_pct: float | None = None
    cumulative_category: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

class IMDWarning(BaseModel):
    district_id: str | None = None
    district: str | None = None
    issued_date: str | None = None
    issued_utc: str | None = None
    day1: str | None = None
    day2: str | None = None
    day3: str | None = None
    day4: str | None = None
    day5: str | None = None
    day1_color: int | None = None
    day2_color: int | None = None
    day3_color: int | None = None
    day4_color: int | None = None
    day5_color: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)

class IMDNowcast(BaseModel):
    station: str | None = None
    date: str | None = None
    issue_time: str | None = None
    valid_upto: str | None = None
    color: int | None = None
    message: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)
