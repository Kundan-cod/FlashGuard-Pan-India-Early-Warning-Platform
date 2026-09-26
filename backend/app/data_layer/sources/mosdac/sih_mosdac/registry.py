MOSDAC_DATASETS = {
    "insat3dr_hem": {
        "dataset_id": "3RIMG_L2B_HEM",
        "satellite": "INSAT-3DR",
        "description": "Hydro-Estimator precipitation",
        "temporal_resolution": "half-hourly",
        "formats": ["HDF", "GeoTIFF"],
        "role": "satellite_precipitation",
        "verification_note": "MOSDAC DOI/product page explicitly documents this dataset ID."
    },
    "insat3ds_imr": {
        "dataset_id": "3SIMG_L2G_IMR",
        "satellite": "INSAT-3DS",
        "description": "INSAT Multi-Spectral Rainfall Algorithm",
        "temporal_resolution": "product-defined",
        "grid": "0.25 degree x 0.25 degree",
        "role": "satellite_precipitation"
    },
    "insat3ds_gpi": {
        "dataset_id": "3SIMG_L2G_GPI",
        "satellite": "INSAT-3DS",
        "description": "GOES Precipitation Index",
        "temporal_resolution": "product-defined",
        "grid": "0.5 degree x 0.5 degree",
        "role": "satellite_precipitation"
    },
    "insat3ds_daily_hem": {
        "dataset_id": "3SIMG_L3B_HEM",
        "satellite": "INSAT-3DS",
        "description": "Daily rainfall using Hydro Estimator",
        "temporal_resolution": "daily",
        "role": "historical_daily_precipitation"
    }
}
