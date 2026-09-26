# SIH 26192 Unified Data Layer

## Purpose
This package combines the previously verified source adapters into one traceable source layer without pretending that every source has the same access mode.

### Source policy
- Core MVP: GPM, IMD, SMAP, Bhuvan/NRSC, CWC/NWIC, LGD, historical labels.
- Optional/enrichment: MOSDAC, GSI/Bhusanket, NDEM.
- NDEM is disabled by default because the public portal exposes only the home page/disaster dashboard; protected products require authorized credentials.
- No source is allowed to be called directly by ML code.

## Data flow

external source
  -> collector/adapter
  -> raw artifact reference
  -> validation/QC
  -> normalized contract
  -> PostgreSQL/PostGIS
  -> feature engineering
  -> model
  -> risk engine
  -> API/dashboard

## Non-negotiable rules
1. Never infer numeric measurements from metadata or map images.
2. Every observation keeps source, timestamp, raw reference and quality.
3. Source health is separate from hazard risk and model confidence.
4. Missing source != zero value.
5. Unknown historical event coverage != confirmed non-event.
6. Administrative names are display fields; LGD codes are keys.
7. Static terrain is preprocessed once.
8. Replay/simulation observations are explicitly labelled.
9. External APIs never become the ML runtime dependency.
10. No undocumented endpoint is hard-coded.

## Handoff
Claude/Cowork can copy this entire package into the main repository. The `sources/` directory preserves the earlier verified packages, while the top-level `sih_data_layer/` directory provides the common contracts and orchestration interfaces.
