SOURCE_REGISTRY = {
    "imd": {
        "name": "India Meteorological Department API",
        "organization": "India Meteorological Department, Ministry of Earth Sciences",
        "official_portal": "https://api.imd.gov.in/public/index.php",
        "official_reference": "https://api.imd.gov.in/public/api_reference.html",
        "base_url": "https://api.imd.gov.in/api/v1",
        "access": "Official account/API access",
        "status": "verified",
        "endpoints": {
            "current_weather": "/current_wx",
            "district_nowcast": "/districtnowcast",
            "district_rainfall": "/districtrainfall",
            "district_warning": "/districtwarning",
            "station_nowcast": "/stationnowcast",
            "state_rainfall": "/staterainfall",
        },
        "notes": (
            "The official reference documents additional forecast, AWS/ARG, "
            "QPF, radar and lightning APIs. Add those as separate contracts."
        ),
    }
}
