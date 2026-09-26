# Verified SMAP specification

## Current collection
NSIDC's current collection directory lists:
- SPL4SMAU V008 — SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture Analysis Update
- SPL4SMGP V008 — SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture Geophysical Data
- SPL4SMLM V008 — SMAP L4 Global 9 km EASE-Grid Surface and Root Zone Soil Moisture Land Model Constants

The Version 8 user guide is published by NSIDC.

## Discovery
NASA CMR supports granule search by collection, time, point, bounding box, polygon and downloadable status. This collector uses collection/version + optional temporal/spatial filters and extracts only documented GET DATA URLs.

## Authentication
The discovery metadata can be searched through CMR. Actual protected data downloads may require NASA Earthdata Login. Keep credentials outside source code.

## Numeric values
Do not treat CMR metadata, footprint polygons, or filenames as numeric soil-moisture measurements. A downstream raw-file parser must read the downloaded scientific product and map the documented variables/quality flags to the internal SoilMoistureObservation contract.

## SIH 26192 integration
Recommended normalized fields:
- source
- product
- version
- observation_time
- latitude/longitude or grid-cell geometry
- surface soil moisture
- root-zone soil moisture
- quality flag
- source granule id
- raw reference

Use source-health states such as LIVE/NRT, STALE, ERROR, and NOT_CONFIGURED at the application layer rather than silently substituting values.
