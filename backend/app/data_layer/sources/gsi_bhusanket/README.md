# SIH 26192 — GSI / Bhusanket Landslide Data Layer

Verified against the current Geological Survey of India National Landslide Forecasting Centre (NLFC) Bhusanket portal.

Official portal:
https://bhusanket.gsi.gov.in/

Current portal exposes:
- Landslide Forecast Bulletin
- LSM 10K Maps
- Landslide Impact Probability Map
- field-validated landslide inventory
- India/state susceptibility views
- state-wise landslide reports

Important coverage limitation:
GSI's operational landslide forecasting is regional, not a nationwide universal live API. Historical GSI material documents operational public bulletins for Darjeeling, Kalimpong and Nilgiris, while experimental forecasts have covered additional districts. The current portal should therefore be treated as a source with geographic/operational coverage metadata, not assumed to provide a national live forecast.

This package provides a safe source adapter/registry. It does not invent an undocumented API endpoint or fabricate bulletin values.

Recommended SIH role:
- baseline landslide susceptibility/hazard context
- historical/field-validated inventory for labels/features
- GSI bulletin ingestion where a documented/public bulletin is available
- source coverage and staleness tracking
