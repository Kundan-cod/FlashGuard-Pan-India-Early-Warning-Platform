# Verified Bhuvan / NRSC facts

## Thematic services
NRSC's current thematic overview lists:
- Carto DEM
- LULC 1:250K
- LULC 1:50K
- LULC 1:10K
- Geomorphology
- Lineament
- Flood Hazard Zonation
- Flood Annual Layers
- Erosion and other natural-resource layers.

Bhuvan states that thematic datasets can be consumed as OGC web services.

## OGC endpoints
The Bhuvan WMS documentation identifies:
- WMS: https://bhuvan-vec2.nrsc.gov.in/bhuvan/wms
- WMTS: https://bhuvan-vec2.nrsc.gov.in/bhuvan/gwc/service/wmts

The Bhuvan Store currently lists these endpoints for multiple thematic products.

## DEM
Bhuvan documentation describes CartoDEM as a countrywide digital surface model with 30 m posting and downloadable 1-degree x 1-degree tiles.

## Engineering decision
Use downloaded DEM tiles for quantitative terrain processing. Derive slope/aspect/curvature/drainage locally and persist those products in PostGIS/raster or object storage.

Use WMS/WMTS for contextual visualization and thematic overlays. Do not scrape rendered map pixels as a substitute for the DEM or authoritative vector/raster data.

For model features, terrain is static and should be preprocessed once, then joined spatially to villages/wards/grid cells.
