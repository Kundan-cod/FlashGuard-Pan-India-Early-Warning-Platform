# Verified GSI / Bhusanket facts

## Current portal
The current GSI National Landslide Forecasting Centre portal exposes:
- Landslide Forecast Bulletin
- LSM 10K Maps
- Landslide Impact Probability Map
- field-validated landslide inventory
- susceptibility views for India and multiple states
- state-wise reports.

The portal was last updated 04 September 2026 in the current crawl.

## Forecast coverage
GSI's official hazard note describes the National Landslide Forecasting Centre and regional landslide early-warning development. It documents operational public bulletins for Darjeeling and Kalimpong in West Bengal and Nilgiris in Tamil Nadu, with experimental bulletins for additional districts.

Therefore the SIH system must NOT claim that GSI provides a nationwide real-time landslide forecast API.

## Current engineering use
1. Use GSI susceptibility/hazard layers as static/contextual risk features.
2. Use field-validated inventory as high-value historical labels/features where data access permits.
3. Ingest GSI public forecast bulletins where they are actually available.
4. Store coverage region, publication time, validity time and source status.
5. If GSI forecast is unavailable for a location, the SIH model continues using its own rainfall/soil/terrain/landslide model and explicitly marks GSI as unavailable.

## No invented endpoint
This adapter intentionally does not hard-code an undocumented JSON API. The public portal is the verified entry point; specific downloadable resources should be discovered from the portal and then normalized.
