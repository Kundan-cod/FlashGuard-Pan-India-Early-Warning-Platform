# Verified MOSDAC facts

## Current official API/client
MOSDAC's current Data Download API manual was reviewed 04 September 2026.

The official workflow uses:
- Python 3
- requests
- MOSDAC account credentials
- datasetId
- config.json

Search does not require login; downloads do.

Documented search parameters:
- datasetId — required
- startTime — YYYY-MM-DD
- endTime — YYYY-MM-DD
- count — maximum 100
- boundingBox — minLon,minLat,maxLon,maxLat
- gId — exact granule ID

The documented download quota is 5000 files per user per day.

## Verified precipitation products

### INSAT-3DR
`3RIMG_L2B_HEM`
- Hydro-Estimator precipitation
- half-hourly
- HDF and GeoTIFF
- product page documents India-region coverage and every-pixel geolocation.

### INSAT-3DS
Operational Product V1 documents:
- `3SIMG_L2G_IMR` — INSAT Multi-Spectral Rainfall Algorithm, 0.25° x 0.25° gridded
- `3SIMG_L2G_GPI` — GOES Precipitation Index, 0.5° x 0.5° gridded
- `3SIMG_L3B_HEM` — daily Hydro-Estimator rainfall

## Engineering decision
Do not invent a public REST endpoint from the website. Treat the official MOSDAC mdapi/config workflow as the source contract. Put the official client behind our collector interface, keep credentials in secrets, and normalize results into the internal schema.

The raw satellite files should then be parsed by a separate product parser. ML must consume normalized values from the internal database, never call MOSDAC directly.
