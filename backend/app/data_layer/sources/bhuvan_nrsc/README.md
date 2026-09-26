# SIH 26192 — Bhuvan / NRSC Terrain & GIS Data Layer

Verified against current NRSC/Bhuvan pages.

Primary use in SIH 26192:
1. CartoDEM -> elevation, slope, aspect, curvature, drainage derivatives.
2. Bhuvan thematic WMS/WMTS -> LULC, geomorphology, lineament, flood hazard and related contextual layers.
3. Preprocess terrain once and store derived rasters/features internally; do not request WMS repeatedly during ML inference.

Verified official WMS:
https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms

Verified official WMTS:
https://bhuvan-vec2.nrsc.gov.in/bhuvan/gwc/service/wmts

Important:
WMS/WMTS are visualization/interoperability services. They should not be treated as the numerical DEM ingestion path. DEM tiles should be acquired through the Bhuvan open-data/download mechanism and processed locally.

The current NRSC thematic overview lists Carto DEM, LULC, geomorphology, lineament, flood hazard zonation and flood annual layers among the available thematic products.
