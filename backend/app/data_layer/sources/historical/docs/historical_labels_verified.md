# Verified historical-label sources

## 1. NRSC/ISRO Landslide Atlas
NRSC states that its landslide inventory covers about 80,000 landslides mapped during 1998–2022 in 17 states and 2 UTs covering landslide-prone Himalayan and Western Ghats regions. The inventory includes seasonal, event-based and route-wise datasets. citeturn0search3turn0search25

The atlas documents satellite mapping plus some field/news validation. citeturn0search25

Use:
- positive landslide labels
- event-season analysis
- spatial hotspot features
- validation/replay cases

Do not interpret the inventory as a complete nationwide absence/presence census.

## 2. NRSC flood hazard / historical inundation
NRSC states it has a repository of historical flood data and uses these datasets for flood-prone-area identification and risk assessment. Its flood hazard zonation atlas uses historical satellite datasets and documents peer review/ground validation for the Bihar atlas. citeturn0search2

The current Bhuvan flood-hazard service shows maximum inundation layers for 1998–2019 and explicitly warns that satellite coverage may miss peak flooding; flash floods and minor flooding may not be captured. citeturn0search13

Use:
- historical flood-positive labels
- inundation frequency/hazard features
- replay validation

Do not convert missing observations into negatives.

## 3. NDEM historical disaster data
NDEM V4 documentation states disaster-specific datasets are available from 1999 onward and are organized by disaster, year and event. citeturn0search26

NRSC's current DMS page describes NDEM as the national GIS repository and notes historical/current flood products and disaster services. citeturn0search4

Access may require protected portal credentials, so NDEM remains optional for the MVP.

## Labeling rule
Use three states:
- `1` = confirmed/observed event
- `0` = confirmed non-event only where observation coverage is demonstrably adequate
- `-1` = unobserved/unknown

This prevents the model from learning the false rule "no record = no disaster."

## Recommended training window
For each confirmed event:
1. identify event time/location/geometry;
2. aggregate rainfall at 1h/3h/6h/12h/24h/72h windows;
3. join antecedent soil moisture;
4. join slope/elevation/land cover/geology;
5. join nearby river level/inflow where available;
6. create positive event samples;
7. sample negatives only from areas/times with adequate observation coverage;
8. split train/validation/test chronologically to avoid temporal leakage.
