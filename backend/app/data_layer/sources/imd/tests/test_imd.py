import httpx
import respx

from sih_imd.collector import IMDCollector

@respx.mock
def test_current_weather_contract():
    respx.get(
        "https://api.imd.gov.in/api/v1/current_wx"
    ).mock(return_value=httpx.Response(200, json=[{
        "Station Id": "42182",
        "Station": "Example",
        "Date of Observation": "2026-09-06",
        "Time of Observation": "1200",
        "Temperature": "28",
        "Humidity": "70",
        "Wind Speed": "12",
        "Wind Direction": "180",
        "M.S.L.P": "1005",
        "Last 24 hrs Rainfall": "18.4",
        "Weather Code": "65",
    }]))

    c = IMDCollector()
    rows = c.normalize_current_weather(c.current_weather("42182"))
    assert rows[0].rainfall_24h_mm == 18.4
    assert rows[0].temperature_c == 28.0

@respx.mock
def test_district_rainfall_normalization():
    respx.get(
        "https://api.imd.gov.in/api/v1/districtrainfall"
    ).mock(return_value=httpx.Response(200, json=[{
        "OBJ_ID": "164",
        "District": "ADILABAD",
        "Date": "2026-09-06",
        "Daily Actual": "25.5",
        "Daily Normal": "10.0",
        "Daily Departure Per": "155%",
        "Daily Category": "LE",
        "Cumulative Actual": "300",
        "Cumulative Normal": "200",
        "Cumulative Departure Per": "50%",
        "Cumulative Category": "E",
    }]))

    c = IMDCollector()
    rows = c.normalize_district_rainfall(c.district_rainfall("164"))
    assert rows[0].daily_actual_mm == 25.5
    assert rows[0].daily_departure_pct == 155.0

@respx.mock
def test_warning_normalization():
    respx.get(
        "https://api.imd.gov.in/api/v1/districtwarning"
    ).mock(return_value=httpx.Response(200, json=[{
        "Obj_id": "573",
        "Date": "2026-09-06",
        "UTC": "1200",
        "District": "Example",
        "Day_1": "16",
        "Day_2": "2",
        "Day_3": "1",
        "Day_4": "1",
        "Day_5": "1",
        "Day1_Color": 4,
        "Day2_Color": 3,
        "Day3_Color": 4,
        "Day4_Color": 4,
        "Day5_Color": 4,
    }]))

    c = IMDCollector()
    rows = c.normalize_warning(c.district_warning("573"))
    assert rows[0].day1 == "16"
    assert rows[0].day1_color == 4
