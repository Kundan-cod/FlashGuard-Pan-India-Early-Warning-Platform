# SIH 26192 — NASA SMAP Data Layer

Verified source: NASA/NSIDC DAAC SMAP L4 Global 3-hourly 9 km EASE-Grid Surface and Root Zone Soil Moisture, Version 8.

Primary collection identifiers:
- SPL4SMAU V008 — Analysis Update
- SPL4SMGP V008 — Geophysical Data
- SPL4SMLM V008 — Land Model Constants

This package implements the discovery/normalization layer only. It does NOT pretend that CMR metadata contains numeric soil-moisture values.

Flow:
CMR collection/granule search -> Earthdata download URL discovery -> local/raw storage -> downstream HDF5/NetCDF parsing -> spatial extraction -> normalized SoilMoistureObservation.

Authentication:
Earthdata/NSIDC downloads may require Earthdata Login. Put credentials/token handling in the application's secret manager; do not hard-code credentials.

Recommended SIH role:
Use SPL4SMAU V008 as the primary 3-hourly soil-moisture analysis source. Keep SPL4SMGP V008 as a compatible geophysical-data option. Do not make the entire system depend on SMAP being live at every prediction cycle; source-health/staleness logic must remain active.

The CMR search API supports temporal, point, bounding-box, polygon and downloadable filters. This package uses those documented search capabilities.
