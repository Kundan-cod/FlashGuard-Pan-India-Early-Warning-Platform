# SIH 26192 — Historical Flood / Landslide Training-Label Layer

This layer defines verified historical-event sources for model training and replay.

Primary official sources:
1. NRSC/ISRO Landslide Atlas of India
2. NRSC/ISRO historical flood / flood-hazard products
3. NDEM historical disaster-specific data (protected/portal-dependent)

Key verified facts:
- NRSC Landslide Atlas covers about 80,000 landslides mapped during 1998–2022 across 17 states and 2 UTs in the Himalayas and Western Ghats.
- The atlas contains seasonal, event-based and route-wise inventories.
- NRSC flood-hazard work uses historical satellite-derived flood inundation layers; its current Bhuvan hazard service shows maximum inundation layers from 1998–2019 and explicitly warns that flash floods/minor flooding may not be captured in every case.
- NDEM documentation states disaster-specific historical datasets exist from 1999 onward, organized by disaster/year/event, but access can be protected.

Engineering decision:
- Keep flood and landslide labels separate.
- Store event geometry/time/source/quality rather than reducing an event to a fake point label.
- Generate training windows by joining event polygons/points to rainfall, soil moisture, terrain, land cover and hydrology features.
- Do not label "no flood" simply because no historical event was found: satellite/event inventories have observation gaps.
- Use source-specific confidence and observation coverage masks.
