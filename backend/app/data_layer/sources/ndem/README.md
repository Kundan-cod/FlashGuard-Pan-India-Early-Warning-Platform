# SIH 26192 — NDEM Data Layer

NDEM (National Database for Emergency Management) is an NRSC/ISRO national GIS repository and DSS for disaster management. Current NRSC material describes near-real-time flood/cyclone monitoring, flood hazard/risk zonation, spatial flood early warning, landslide zonation/inventory and related disaster services.

Critical access decision:
NDEM's protected data services require authorized credentials. NRSC documentation says authorized Central/State/District/NDRF/SDRF users access the protected portal; public/base layers may be visible without login. Therefore NDEM is an OPTIONAL/STRATEGIC connector for SIH, not an MVP hard dependency.

This package implements:
- NDEM source registry
- source-health/access contract
- protected/public capability separation
- safe portal discovery adapter
- no invented private API endpoints

Do not scrape or bypass protected NDEM services. If official credentials/API access are later granted, add an authenticated adapter behind the same interface.
