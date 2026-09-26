BHUVAN_LAYERS = {
    "lulc_50k": {
        "service": "WMS/WMTS",
        "role": "land_use_land_cover_context",
        "verified_service_url": "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms",
    },
    "geomorphology_50k": {
        "service": "WMS/WMTS",
        "role": "geomorphology_context",
        "verified_service_url": "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms",
    },
    "lineament_50k": {
        "service": "WMS/WMTS",
        "role": "lineament_context",
        "verified_service_url": "https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms",
    },
    "flood_hazard": {
        "service": "WMS",
        "role": "historical_flood_hazard_context",
        "verified_service_url": "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/hazard.exe",
    },
    "flood_annual_layers": {
        "service": "WMS",
        "role": "historical_flood_context",
        "verified_service_url": "https://bhuvan-ras2.nrsc.gov.in/cgi-bin/flood.exe",
    },
}
