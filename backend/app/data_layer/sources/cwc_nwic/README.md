# SIH 26192 — CWC / NWIC Data Layer

Verified against the current National Water Data Portal (NWDP/NWIC) and CWC flood-forecasting documentation.

Core verified datasets:
- CWC River Water Level — Telemetry Hourly
- CWC Rainfall — Telemetry Hourly
- CWC Reservoir Water Storage/Level datasets
- Manual hourly/daily variants

Current NWDP dataset pages expose CSV and API as data formats. The river-water-level portal currently lists 2026–2030 telemetry datasets for major river systems including Subernarekha, Mahanadi, Godavari, Krishna, Pennar, Cauvery, Tapi, Narmada, Mahi, Sabarmati and others.

CWC's flood-forecast appraisal documents confirm that real-time water level and inflow/outflow are received from WIMS through NWIC and are used with rainfall/forecast inputs in operational flood forecasting.

This package intentionally does not invent an undocumented API URL. It supports:
- NWDP dataset-page discovery
- resource-link extraction
- normalized river-level/rainfall contracts
- source health
- CSV/API resource metadata
- a clean adapter boundary for a future authenticated/live API.

ML must consume normalized internal observations, not call NWIC/CWC directly.
