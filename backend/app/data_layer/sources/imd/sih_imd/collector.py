from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from .config import Settings
from .contracts import (
    IMDCurrentWeather,
    IMDDistrictRainfall,
    IMDWarning,
    IMDNowcast,
)

class IMDCollector:
    def __init__(
        self,
        settings: Settings | None = None,
        client: httpx.Client | None = None,
    ):
        self.settings = settings or Settings()
        self.client = client or httpx.Client(
            timeout=self.settings.timeout_seconds
        )

    def _headers(self) -> dict[str, str]:
        # Do not invent the header name for credentials.
        # When IMD provides the account's API-token mechanism, configure it
        # here without committing the secret.
        if self.settings.api_token:
            return {"Authorization": self.settings.api_token}
        return {}

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = self.settings.base_url.rstrip("/") + "/" + path.lstrip("/")
        last_error = None

        for attempt in range(self.settings.max_retries + 1):
            try:
                response = self.client.get(
                    url,
                    params=params,
                    headers=self._headers(),
                )
                response.raise_for_status()
                return response.json()
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt >= self.settings.max_retries:
                    raise RuntimeError(
                        f"IMD request failed: {url}: {last_error}"
                    ) from exc
                time.sleep(min(2 ** attempt, 8))

    def current_weather(self, station_id: str | None = None) -> Any:
        params = {"id": station_id} if station_id else None
        return self._get("/current_wx", params)

    def district_nowcast(self, district_id: str | None = None) -> Any:
        params = {"id": district_id} if district_id else None
        return self._get("/districtnowcast", params)

    def district_rainfall(self, district_id: str | None = None) -> Any:
        params = {"id": district_id} if district_id else None
        return self._get("/districtrainfall", params)

    def district_warning(self, district_id: str | None = None) -> Any:
        params = {"id": district_id} if district_id else None
        return self._get("/districtwarning", params)

    def station_nowcast(self, station: str | None = None) -> Any:
        params = {"id": station} if station else None
        return self._get("/stationnowcast", params)

    def state_rainfall(self, state: str | None = None) -> Any:
        params = {"id": state} if state else None
        return self._get("/staterainfall", params)

    @staticmethod
    def _rows(payload: Any) -> list[dict[str, Any]]:
        if isinstance(payload, list):
            return payload
        if isinstance(payload, dict):
            for key in ("data", "Data", "result", "results"):
                if isinstance(payload.get(key), list):
                    return payload[key]
            return [payload]
        raise ValueError("Unexpected IMD response type")

    def normalize_current_weather(self, payload: Any) -> list[IMDCurrentWeather]:
        rows = self._rows(payload)
        out = []
        for row in rows:
            out.append(IMDCurrentWeather(
                station_id=str(row.get("Station Id")) if row.get("Station Id") is not None else None,
                station=row.get("Station"),
                observation_date=row.get("Date of Observation"),
                observation_time_utc=row.get("Time of Observation"),
                temperature_c=self._float(row.get("Temperature")),
                humidity_pct=self._float(row.get("Humidity")),
                wind_speed_kmph=self._float(row.get("Wind Speed")),
                wind_direction_code=self._float(row.get("Wind Direction")),
                pressure_hpa=self._float(row.get("M.S.L.P")),
                rainfall_24h_mm=self._float(row.get("Last 24 hrs Rainfall")),
                weather_code=str(row.get("Weather Code")) if row.get("Weather Code") is not None else None,
                raw=row,
            ))
        return out

    def normalize_district_rainfall(self, payload: Any) -> list[IMDDistrictRainfall]:
        rows = self._rows(payload)
        out = []
        for row in rows:
            out.append(IMDDistrictRainfall(
                district_id=str(row.get("OBJ_ID")) if row.get("OBJ_ID") is not None else None,
                district=row.get("District"),
                date=row.get("Date"),
                daily_actual_mm=self._float(row.get("Daily Actual")),
                daily_normal_mm=self._float(row.get("Daily Normal")),
                daily_departure_pct=self._percent(row.get("Daily Departure Per")),
                daily_category=row.get("Daily Category"),
                cumulative_actual_mm=self._float(row.get("Cumulative Actual")),
                cumulative_normal_mm=self._float(row.get("Cumulative Normal")),
                cumulative_departure_pct=self._percent(row.get("Cumulative Departure Per")),
                cumulative_category=row.get("Cumulative Category"),
                raw=row,
            ))
        return out

    def normalize_warning(self, payload: Any) -> list[IMDWarning]:
        rows = self._rows(payload)
        return [
            IMDWarning(
                district_id=str(r.get("Obj_id")) if r.get("Obj_id") is not None else None,
                district=r.get("District"),
                issued_date=r.get("Date"),
                issued_utc=r.get("UTC"),
                day1=r.get("Day_1"),
                day2=r.get("Day_2"),
                day3=r.get("Day_3"),
                day4=r.get("Day_4"),
                day5=r.get("Day_5"),
                day1_color=self._int(r.get("Day1_Color")),
                day2_color=self._int(r.get("Day2_Color")),
                day3_color=self._int(r.get("Day3_Color")),
                day4_color=self._int(r.get("Day4_Color")),
                day5_color=self._int(r.get("Day5_Color")),
                raw=r,
            )
            for r in rows
        ]

    def normalize_nowcast(self, payload: Any) -> list[IMDNowcast]:
        rows = self._rows(payload)
        return [
            IMDNowcast(
                station=r.get("Station"),
                date=r.get("Date"),
                issue_time=r.get("toi"),
                valid_upto=r.get("Vupto"),
                color=self._int(r.get("color")),
                message=r.get("message"),
                raw=r,
            )
            for r in rows
        ]

    @staticmethod
    def _float(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace("%", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _percent(value: Any) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(str(value).replace("%", "").strip())
        except ValueError:
            return None

    @staticmethod
    def _int(value: Any) -> int | None:
        try:
            return int(value) if value is not None and value != "" else None
        except (ValueError, TypeError):
            return None
