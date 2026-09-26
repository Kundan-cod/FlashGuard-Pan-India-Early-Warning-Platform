# Verified CWC / NWIC facts

## National Water Data Portal
The current NWDP page for CWC river water level states that the dataset contains hourly river water-level measurements from telemetry stations and includes timestamp, station identifier/geographic hierarchy and water-level values. The page currently advertises CSV and API formats and 2026–2030 datasets. citeturn1view0

The current CWC rainfall telemetry dataset similarly provides hourly rainfall measurements from telemetry stations, with timestamp, station/geographic information and rainfall values; current 2026–2030 state datasets are listed. citeturn1view1

Reservoir water-level/storage datasets are also exposed through NWDP as CSV/API. citeturn0search1

## Operational forecasting architecture
CWC's flood-forecasting appraisal says the operational 7-day advisory system uses GPM 10 km/30 min rainfall, GsMaP, India gridded rainfall and IMD forecast products. It also states that real-time water level and inflow/outflow are received from WIMS through NWIC and then fed into river models. citeturn0search24

## Engineering decision
CWC/NWIC is high-value for the flash-flood model:
- river level trend
- rainfall at hydrological stations
- reservoir context
- flood-forecast validation/benchmarking

Use NWDP public resources where available. Keep a separate live API adapter boundary because the portal advertises API as a data format but the exact API endpoint/auth contract was not verified in this pass.

Do not claim that every station is live or that every API is anonymous.
