# Verification Record

Verified on 2026-09-06.

## Source checks performed in this ChatGPT session

### IMD
Official API reference currently documents `current_wx` and other weather/rainfall/warning endpoints under `https://api.imd.gov.in/api/v1/`. 

### MOSDAC
Official manual was last reviewed/updated 04 Sep 2026 and documents `mdapi`, `config.json`, datasetId, temporal range, count, boundingBox and gId, with MOSDAC credentials for downloads.

### Bhuvan
Official Bhuvan WMS documentation confirms OGC WMS/WMTS interoperability and documents the WMS endpoint `https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms`.

### GSI/Bhusanket
Current Bhusanket portal is the National Landslide Forecasting Centre entry point. NLFC describes integration of real/non-real-time inputs and landslide forecasting/hazard databases.

### NDEM
Current NDEM portal states version 4.1; public users can access only the home page/disaster dashboard, while authorized users can access base maps, disaster-specific products and DSS tools.

### CWC/NWIC
Current NWDP CWC river-level dataset was updated 04 Sep 2026 and advertises CSV/API, with hourly telemetry datasets.

## Package-level verification
- all source ZIPs present at build time are preserved under `sources/`
- common Pydantic contracts compile independently
- source registry has no duplicate names
- fallback logic never selects ERROR/NOT_CONFIGURED/STALE as usable
- coordinate QC rejects impossible latitude/longitude
- historical unknown labels are not converted to negative labels

## Known limitations
This is an integration/orchestration layer, not a claim that every live source is authenticated or continuously available. Live credentials, protected services and source-specific scientific file parsers remain environment/configuration dependent.
