# SIH 26192 — ISRO MOSDAC Data Layer

Verified against the current MOSDAC Data Download API manual (reviewed 04 Sep 2026).

Official workflow:
- datasetId is required for search.
- Search/preview does not require login.
- Download requires MOSDAC account credentials / SSO.
- Search filters include startTime, endTime, count, boundingBox and gId.
- count maximum documented by the current manual: 100.
- download client has a documented daily maximum of 5000 files/user/day.

Relevant verified precipitation products:
- INSAT-3DR: 3RIMG_L2B_HEM — Hydro-Estimator precipitation; half-hourly; HDF/GeoTIFF; India-region coverage documented by MOSDAC.
- INSAT-3DS operational products document:
  - 3SIMG_L2G_IMR — INSAT Multi-Spectral Rainfall Algorithm, gridded 0.25° x 0.25°
  - 3SIMG_L2G_GPI — GOES Precipitation Index, gridded 0.5° x 0.5°
  - 3SIMG_L3B_HEM — daily rainfall using Hydro Estimator.

Important:
The package does NOT hard-code undocumented MOSDAC search/download URLs. It provides a validated adapter around the official mdapi workflow and a dataset registry using dataset IDs that are explicitly documented by MOSDAC product pages.

Authentication credentials must remain outside source code.

For SIH:
MOSDAC is an India-specific satellite layer. It should complement IMD and NASA GPM, not replace them. Use source-health/staleness state so the model can operate with a valid fallback if MOSDAC is unavailable.
