-- =============================================================================
-- SQLite schema — Track A portable core (mirrors the PostGIS schema, Track B)
-- SIH 2026 PS 26192 Flash Flood Prediction System
--
-- Geometry note: SQLite (stdlib, no SpatiaLite) has no native geometry type.
-- We store geometry as GeoJSON text in `geometry_geojson` plus a numeric
-- bounding box (minx,miny,maxx,maxy) for fast candidate filtering. Pure-Python
-- point-in-polygon (see geospatial/spatial.py) does exact tests. In Track B
-- these same columns become PostGIS geometry(…, 4326). All coords are WGS84.
-- All timestamps are ISO-8601 UTC strings ('...Z'). Rainfall mm, level metres.
-- =============================================================================

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ---- Administrative locations (India→state→district→block→village/ward) -----
CREATE TABLE IF NOT EXISTS locations (
    id              INTEGER PRIMARY KEY,
    ext_code        TEXT UNIQUE,             -- stable external/admin code
    name            TEXT NOT NULL,
    level           TEXT NOT NULL,           -- country|state|district|block|village|ward
    parent_id       INTEGER REFERENCES locations(id),
    state           TEXT,
    district        TEXT,
    block           TEXT,
    village         TEXT,
    latitude        REAL,                    -- representative point (centroid)
    longitude       REAL,
    geometry_geojson TEXT,                   -- polygon (GeoJSON) if available
    bbox_minx       REAL, bbox_miny REAL, bbox_maxx REAL, bbox_maxy REAL,
    is_synthetic    INTEGER NOT NULL DEFAULT 0,  -- 1 = demo/synthetic polygon (labelled)
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_locations_level ON locations(level);
CREATE INDEX IF NOT EXISTS ix_locations_parent ON locations(parent_id);
CREATE INDEX IF NOT EXISTS ix_locations_bbox ON locations(bbox_minx,bbox_miny,bbox_maxx,bbox_maxy);

-- ---- Terrain (static, derived once from DEM) --------------------------------
CREATE TABLE IF NOT EXISTS terrain_features (
    location_id     INTEGER PRIMARY KEY REFERENCES locations(id) ON DELETE CASCADE,
    elevation       REAL,      -- m
    slope           REAL,      -- degrees
    aspect          REAL,      -- degrees
    curvature       REAL,
    flow_accumulation REAL,
    drainage_density  REAL,
    distance_to_drainage REAL, -- m
    relative_relief REAL,
    is_synthetic    INTEGER NOT NULL DEFAULT 0,
    source          TEXT,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ---- Rainfall observations --------------------------------------------------
CREATE TABLE IF NOT EXISTS rainfall_observations (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,           -- registry key: gpm|imd|mosdac|iot|replay
    ts              TEXT NOT NULL,           -- UTC ISO-8601
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    rainfall_30m    REAL,                    -- mm
    rainfall_3h     REAL,
    rainfall_24h    REAL,
    quality_flag    TEXT NOT NULL DEFAULT 'GOOD',  -- GOOD|WARNING|BAD|MISSING|STALE
    resolution_m    REAL,                    -- native spatial resolution (m), provenance
    realtime_class  TEXT,                    -- live|near_real_time|replay|simulation
    units           TEXT DEFAULT 'mm',
    granule_id      TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, ts, latitude, longitude)  -- idempotency (section 7)
);
CREATE INDEX IF NOT EXISTS ix_rain_ts ON rainfall_observations(ts);
CREATE INDEX IF NOT EXISTS ix_rain_src ON rainfall_observations(source);

-- ---- Soil moisture observations ---------------------------------------------
CREATE TABLE IF NOT EXISTS soil_moisture_observations (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    ts              TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    surface_moisture   REAL,                 -- 0..1 or %  (normalized to % internally)
    root_zone_moisture REAL,
    quality_flag    TEXT NOT NULL DEFAULT 'GOOD',
    resolution_m    REAL,
    realtime_class  TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, ts, latitude, longitude)
);
CREATE INDEX IF NOT EXISTS ix_soil_ts ON soil_moisture_observations(ts);

-- ---- River observations -----------------------------------------------------
CREATE TABLE IF NOT EXISTS river_observations (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    station_id      TEXT,
    ts              TEXT NOT NULL,
    latitude        REAL, longitude REAL,
    water_level     REAL,                    -- m
    flow            REAL,                    -- m3/s
    rate_of_rise    REAL,                    -- m/h (computed)
    quality_flag    TEXT NOT NULL DEFAULT 'GOOD',
    realtime_class  TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, station_id, ts)
);
CREATE INDEX IF NOT EXISTS ix_river_ts ON river_observations(ts);

-- ---- GPM dataset-discovery records (NOT a rainfall observation) -------------
-- The NASA GPM PMM Publisher API is a dataset-DISCOVERY interface: a response
-- item is a dataset footprint + download URL(s), NOT a numeric rainfall value
-- (see app/data_layer/docs/gpm_verified.md). Storing these here — in a table the
-- ML feature pipeline NEVER reads — guarantees a discovery record can never
-- masquerade as a numeric rainfall observation. A real mm value only enters
-- rainfall_observations after the gated raster-sampling stage parses the
-- downloaded product. `numeric_value` stays NULL at the discovery stage by design.
CREATE TABLE IF NOT EXISTS gpm_discovery (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'gpm',
    product         TEXT,                    -- PMM product display name
    observed_date   TEXT,                    -- dataset date as reported by the API
    latitude        REAL,                    -- footprint centroid (provenance only)
    longitude       REAL,
    resolution      TEXT,                    -- as reported (e.g. '0.1 degree')
    download_url    TEXT,                    -- parsed from the item's ojo:download action
    media_type      TEXT,
    item_id         TEXT,                    -- API item @id (natural key with url)
    numeric_value   REAL,                    -- ALWAYS NULL at discovery; set only after raster sampling
    stage           TEXT NOT NULL DEFAULT 'DISCOVERY_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                    -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(item_id, download_url)            -- idempotent re-discovery
);
CREATE INDEX IF NOT EXISTS ix_gpmdisc_date ON gpm_discovery(observed_date);

-- ---- SMAP granule discovery (NASA CMR) --------------------------------------
-- Twin of gpm_discovery for NASA SMAP L4 soil-moisture. Stores CMR granule
-- metadata + documented GET DATA URLs, which are NOT numeric soil-moisture
-- values. numeric fields stay NULL at discovery; a real m3/m3 value only enters
-- soil_moisture_observations after a gated raster/HDF5-parsing stage. The ML
-- feature pipeline never reads this table, so a discovery record can never
-- masquerade as a measurement (master prompt: never invent measurements).
CREATE TABLE IF NOT EXISTS smap_discovery (
    id                INTEGER PRIMARY KEY,
    source            TEXT NOT NULL DEFAULT 'smap',
    product           TEXT,                    -- short_name (e.g. SPL4SMAU)
    version           TEXT,                    -- collection version (e.g. 008)
    observed_date     TEXT,                    -- granule start time as reported
    end_time          TEXT,                    -- granule end time as reported
    latitude          REAL,                    -- footprint centroid (provenance only)
    longitude         REAL,
    grid              TEXT,                    -- as reported (e.g. '9 km EASE-Grid')
    download_url      TEXT,                    -- documented GET DATA URL (never fabricated)
    concept_id        TEXT,                    -- CMR granule concept-id (natural key with url)
    producer_granule_id TEXT,
    -- ALWAYS NULL at discovery; set only after the gated HDF5/NetCDF parse stage.
    surface_sm        REAL,                    -- surface soil moisture m3/m3
    rootzone_sm       REAL,                    -- root-zone soil moisture m3/m3
    quality_flag      TEXT DEFAULT 'UNKNOWN',
    stage             TEXT NOT NULL DEFAULT 'DISCOVERY_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference     TEXT,                    -- opaque provenance blob (JSON)
    retrieved_at      TEXT,
    ingested_at       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(concept_id, download_url)           -- idempotent re-discovery
);
CREATE INDEX IF NOT EXISTS ix_smapdisc_date ON smap_discovery(observed_date);

-- ---- IMD observations (India Meteorological Department, api.imd.gov.in) ------
-- IMD returns REAL numeric government weather/rainfall/warnings, but at
-- DISTRICT or STATION granularity and WITHOUT coordinates (verified spec
-- docs/imd_verified.md). It therefore must NOT enter rainfall_observations
-- (which is a point table requiring lat/lon and is read by the ML feature
-- pipeline as village-level rainfall). Fabricating a village coordinate for a
-- district figure would violate the honesty rules ("Do not treat district
-- rainfall as village-level rainfall"). So IMD lands here, keyed by its own
-- area id, preserving the original code/color/validity + raw payload verbatim.
-- A separate, explicit spatial-join step (district polygon -> villages) would be
-- required before any IMD value could inform a village prediction; that join is
-- deliberately NOT done at ingestion and no such join exists yet.
CREATE TABLE IF NOT EXISTS imd_observations (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'imd',
    -- record_type: current_weather | district_rainfall | district_warning | nowcast
    record_type     TEXT NOT NULL,
    -- area_kind: station | district | state  (what area_id/area_name refer to)
    area_kind       TEXT,
    area_id         TEXT,                    -- IMD station id / district OBJ_ID (as reported)
    area_name       TEXT,                    -- station or district name (as reported)
    observed_at     TEXT,                    -- observation/issue time as reported (may be non-UTC label)
    valid_upto      TEXT,                    -- nowcast/warning validity as reported
    -- numeric weather (current_weather); NULL when not applicable
    temperature_c   REAL,
    humidity_pct    REAL,
    wind_speed_kmph REAL,
    pressure_hpa    REAL,
    rainfall_24h_mm REAL,                    -- "Last 24 hrs Rainfall" as reported (station-level)
    -- district rainfall context; NULL when not applicable
    daily_actual_mm REAL,
    daily_normal_mm REAL,
    cumulative_actual_mm REAL,
    cumulative_normal_mm REAL,
    rainfall_category TEXT,                  -- IMD's own category label (NOT our ML threshold)
    -- warning/nowcast; codes and colors preserved verbatim, never mapped to ML prob
    warning_code    TEXT,                    -- e.g. Day_1 code, or nowcast message code
    warning_color   INTEGER,                 -- IMD color int, preserved (NOT converted to probability)
    warning_day     INTEGER,                 -- 1..5 for district warnings, NULL otherwise
    message         TEXT,                    -- nowcast message text as reported
    quality_flag    TEXT NOT NULL DEFAULT 'GOOD',
    realtime_class  TEXT,                    -- real_time (IMD is a live gov source)
    raw_reference   TEXT,                    -- full original row as JSON (provenance)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    -- idempotent re-ingestion: one row per (type, area, time, warning-day)
    UNIQUE(source, record_type, area_id, observed_at, warning_day)
);
CREATE INDEX IF NOT EXISTS ix_imd_type ON imd_observations(record_type);
CREATE INDEX IF NOT EXISTS ix_imd_area ON imd_observations(area_id);

-- ---- MOSDAC granule discovery (ISRO/MOSDAC INSAT precipitation) -------------
-- Twin of gpm_discovery / smap_discovery for ISRO MOSDAC INSAT-3DR/3DS
-- precipitation products. The verified MOSDAC mdapi workflow (docs/
-- mosdac_verified.md) is a SEARCH + DOWNLOAD contract: a search item is granule
-- metadata + a download URL for an HDF/GeoTIFF product, NOT a numeric rainfall
-- value. The verified note is explicit: "The raw satellite files should then be
-- parsed by a separate product parser. ML must consume normalized values from
-- the internal database, never call MOSDAC directly." So discovery lands here —
-- in a table the ML feature pipeline NEVER reads — and numeric_value stays NULL
-- at discovery. A real mm value only enters rainfall_observations after a gated
-- raster/HDF-parsing stage (not part of the verified package, so not faked).
-- Search does NOT require login; downloads DO — mirrored by the collector's
-- honest NOT_CONFIGURED (no credentials) vs LIVE (search succeeded) states.
CREATE TABLE IF NOT EXISTS mosdac_discovery (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'mosdac',
    dataset_id      TEXT,                    -- e.g. 3RIMG_L2B_HEM (verified product id)
    satellite       TEXT,                    -- e.g. INSAT-3DR (from the verified registry)
    product         TEXT,                    -- registry key / description (as reported)
    observed_date   TEXT,                    -- granule start time as reported
    end_time        TEXT,                    -- granule end time as reported
    latitude        REAL,                    -- footprint centroid if reported (provenance only)
    longitude       REAL,
    resolution      TEXT,                    -- as reported (e.g. '0.25 degree x 0.25 degree')
    download_url    TEXT,                    -- documented download URL (never fabricated)
    granule_id      TEXT,                    -- MOSDAC gId (natural key with dataset+url)
    numeric_value   REAL,                    -- ALWAYS NULL at discovery; set only after raster parsing
    quality_flag    TEXT DEFAULT 'UNKNOWN',
    stage           TEXT NOT NULL DEFAULT 'DISCOVERY_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                    -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(dataset_id, granule_id, download_url)  -- idempotent re-discovery
);
CREATE INDEX IF NOT EXISTS ix_mosdacdisc_date ON mosdac_discovery(observed_date);
CREATE INDEX IF NOT EXISTS ix_mosdacdisc_dataset ON mosdac_discovery(dataset_id);

-- ---- Bhuvan / NRSC layer catalog (CATALOG-ONLY, never numeric terrain) ------
-- Bhuvan/NRSC is a STATIC terrain/context source exposed as OGC WMS/WMTS layers
-- (CartoDEM, LULC, geomorphology, lineament, flood-hazard/annual layers). The
-- verified note (docs/bhuvan_verified.md) is explicit on two points:
--   (1) "Do not scrape rendered map pixels as a substitute for the DEM or
--       authoritative vector/raster data." So we NEVER turn a WMS GetMap image
--       into a numeric elevation/slope value.
--   (2) Quantitative terrain (elevation/slope/aspect/curvature/drainage) must be
--       derived from downloaded DEM *tiles* and "preprocessed once", then joined
--       to villages. That DEM-tile parse stage is NOT part of the verified
--       package, so we do not fake it.
-- Therefore this table is a CATALOG of verified layer endpoints + roles ONLY. It
-- carries NO measured terrain value and is deliberately NOT read by the ML
-- feature pipeline (which reads terrain_features). A catalog row can never
-- masquerade as a numeric terrain feature. Real terrain values only enter
-- terrain_features after a gated DEM-tile processing stage (future work).
CREATE TABLE IF NOT EXISTS bhuvan_layers (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'bhuvan',
    layer_key       TEXT NOT NULL,             -- registry key, e.g. 'flood_hazard'
    service_type    TEXT,                      -- WMS | WMTS (as reported)
    role            TEXT,                      -- verified role/context label
    service_url     TEXT,                      -- verified OGC endpoint (never fabricated)
    layer_name      TEXT,                      -- OGC layer identifier if reported
    stage           TEXT NOT NULL DEFAULT 'CATALOG_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                      -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, layer_key, service_url)     -- idempotent re-catalog
);
CREATE INDEX IF NOT EXISTS ix_bhuvanlayer_key ON bhuvan_layers(layer_key);

-- ---- GSI / Bhusanket layer catalog (CATALOG-ONLY, never a landslide value) --
-- GSI's National Landslide Forecasting Centre (Bhusanket portal) exposes a
-- forecast bulletin, LSM 10K susceptibility maps, an impact-probability map and
-- a field-validated landslide inventory. The verified note (docs/gsi_verified.md)
-- is explicit:
--   (1) "This adapter intentionally does not hard-code an undocumented JSON API"
--       — the public portal is the verified entry point; specific resources are
--       discovered from it and then normalized. So we NEVER invent a bulletin
--       value or a numeric susceptibility/probability.
--   (2) GSI forecasting is REGIONAL (Darjeeling/Kalimpong/Nilgiris operational,
--       others experimental), NOT a nationwide live API — so each layer carries
--       a geographic/operational COVERAGE note that must be preserved, and the
--       system must "explicitly mark GSI as unavailable" where it does not cover
--       a location rather than fabricate a forecast.
-- Therefore this is a CATALOG of verified portal layers + roles + coverage ONLY.
-- It carries NO numeric landslide susceptibility/probability. The ML landslide
-- model reads landslide_data (its own susceptibility/impact_probability), NEVER
-- this catalog, so a GSI catalog row can never masquerade as a landslide value.
-- Real GSI inventory/bulletin values would only enter after a separate, gated,
-- verified parse of a specific documented public resource (future work).
CREATE TABLE IF NOT EXISTS gsi_layers (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'gsi',
    layer_key       TEXT NOT NULL,             -- registry key, e.g. 'lsm_10k'
    role            TEXT,                      -- landslide_inventory|susceptibility|impact_probability|forecast_bulletin
    service_url     TEXT,                      -- verified portal URL (never fabricated)
    geographic_scope TEXT,                     -- verified coverage note (regional, NOT nationwide)
    public          INTEGER NOT NULL DEFAULT 1,-- 1 = publicly listed on the portal
    stage           TEXT NOT NULL DEFAULT 'CATALOG_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                      -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, layer_key, service_url)     -- idempotent re-catalog
);
CREATE INDEX IF NOT EXISTS ix_gsilayer_key ON gsi_layers(layer_key);

-- ---- CWC / NWIC dataset catalog (CATALOG-ONLY, never a numeric hydro value) --
-- CWC/NWIC hydrology (river water level, telemetry rainfall, reservoir storage)
-- is high-value for the flash-flood model, but the verified note
-- (docs/cwc_nwic_verified.md) is explicit:
--   (1) "This package intentionally does not invent an undocumented API URL." The
--       public National Water Data Portal (NWDP) dataset pages are the verified
--       entry point; CSV/API resource links are DISCOVERED from those pages and
--       recorded — we NEVER fabricate a station reading or an API endpoint.
--   (2) The portal advertises API as a data format, but "the exact API endpoint/
--       auth contract was not verified in this pass", and we must "not claim that
--       every station is live or that every API is anonymous." So a clean adapter
--       boundary is kept: cataloging the verified dataset resources needs no
--       credentials; a future authenticated/live parse stage is separate.
-- Therefore this is a CATALOG of verified NWDP dataset pages + roles + advertised
-- resource formats ONLY. It carries NO measured water-level / rainfall value. The
-- ML feature pipeline reads river_observations / rainfall_observations and NEVER
-- reads this catalog, so a CWC catalog row can never masquerade as a numeric
-- hydrological value. Real CWC values only enter those observation tables after a
-- separate, gated, verified CSV/API parse of a specific dataset resource (future
-- work). Twin of bhuvan_layers / gsi_layers.
CREATE TABLE IF NOT EXISTS cwc_resources (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'cwc',
    dataset_key     TEXT NOT NULL,             -- registry key, e.g. 'river_water_level_telemetry_hourly'
    role            TEXT,                      -- real_time_hydrological_observation|hydrological_rainfall_observation|reservoir_context
    dataset_url     TEXT,                      -- verified NWDP dataset-page URL (never fabricated)
    resource_format TEXT,                      -- advertised format(s), e.g. 'CSV/API' (verbatim)
    frequency       TEXT,                      -- verified cadence, e.g. 'hourly' | 'daily/manual'
    stage           TEXT NOT NULL DEFAULT 'CATALOG_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                      -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, dataset_key, dataset_url)   -- idempotent re-catalog
);
CREATE INDEX IF NOT EXISTS ix_cwcresource_key ON cwc_resources(dataset_key);

-- ---- LGD administrative directory catalog (CATALOG-ONLY, never geometry) -----
-- The Government of India's Local Government Directory (LGD) is the AUTHORITATIVE
-- directory of administrative identity + codes for the India -> State/UT ->
-- District -> Sub-district -> Development Block -> Village/ULB -> Ward hierarchy.
-- It is exposed as downloadable directories at the official portal
-- (https://lgdirectory.gov.in/demo/downloadDirectory.do). The verified note
-- (docs/lgd_verified.md) is explicit about TWO honesty-critical boundaries:
--   (1) "Do not assume LGD directory tables are themselves polygon datasets.
--       Boundary geometry must be sourced from an authoritative GIS boundary
--       product and versioned separately ... joined using LGD codes." So this
--       catalog carries NO geometry at all (no PostGIS geom) — an LGD row is an
--       administrative-code directory entry, NOT a boundary polygon and NOT a
--       point observation. Village/ward geometry lives in the locations layer and
--       is joined by LGD code, never fabricated from this directory.
--   (2) "Use LGD codes as stable join keys. Names are display fields only ...
--       Never use village/ward names as primary keys because names can repeat or
--       change." So the natural key is the LGD code, and name is display-only.
-- The vendored verified adapter fetches only the directory DOWNLOAD PAGE and "does
-- not guess file names or fabricate geometry URLs"; it implements no row parser.
-- So the honest integration CATALOGS the verified LGD directory DATASETS (one per
-- administrative level: districts, subdistricts, blocks, villages, PRI/urban local
-- bodies, wards) + their level + purpose in this table (stage='CATALOG_ONLY'). It
-- produces NO administrative-unit rows and NO measurement. The ML feature pipeline
-- never reads this catalog. Real LGD unit rows (codes+hierarchy) would only enter
-- a separate administrative table after a gated, verified directory-file parse
-- (future work). Twin of bhuvan_layers / gsi_layers / cwc_resources.
CREATE TABLE IF NOT EXISTS lgd_directory (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'lgd',
    dataset_key     TEXT NOT NULL,             -- registry key, e.g. 'villages'
    admin_level     TEXT,                      -- STATE_UT|DISTRICT|SUBDISTRICT|BLOCK|VILLAGE|PRI_LOCAL_BODY|URBAN_LOCAL_BODY|WARD
    purpose         TEXT,                      -- verified directory purpose (verbatim)
    directory_url   TEXT,                      -- verified LGD download-portal URL (never fabricated)
    stage           TEXT NOT NULL DEFAULT 'CATALOG_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                      -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, dataset_key, directory_url) -- idempotent re-catalog
);
CREATE INDEX IF NOT EXISTS ix_lgddirectory_key ON lgd_directory(dataset_key);

-- ---- Historical-label source catalog (CATALOG-ONLY, never a fabricated event) -
-- The historical-labels layer defines the VERIFIED official sources of historical
-- flood / landslide events used for model training and replay validation: the
-- NRSC/ISRO Landslide Atlas (~80,000 landslides mapped 1998-2022 across 17 states
-- + 2 UTs), NRSC flood-hazard zonation, the Bhuvan historical flood-inundation
-- service (1998-2019 maximum-inundation layers), and NDEM disaster-specific
-- historical data (1999-present, portal/auth dependent). The verified note
-- (docs/historical_labels_verified.md) is explicit on the honesty-critical points:
--   (1) These are AUTHORITATIVE EVENT-INVENTORY sources, NOT complete presence/
--       absence censuses. "Do not interpret the inventory as a complete nationwide
--       absence/presence census" and "Do not convert missing observations into
--       negatives." The vendored package ships NO event rows and NO parser — it
--       provides the source registry + the three-state labeling RULE only.
--   (2) The labeling rule is three-state: 1=confirmed/observed event, 0=confirmed
--       non-event ONLY where observation coverage is demonstrably adequate,
--       -1=unobserved/unknown. This prevents the model from learning the false
--       rule "no record = no disaster." Absence of an observed event is NEVER a
--       confirmed negative when inventory coverage is incomplete.
-- Therefore this is a CATALOG of the verified historical-event SOURCES + their
-- hazard + period + role + access ONLY. It carries NO event geometry, NO event
-- time, and NO training label. Real historical event rows (and the 1/0/-1 training
-- labels derived from them via the verified labeling rule) would only enter a
-- separate events/labels table after a gated, verified parse of a specific
-- downloaded inventory (future work) — and negatives would be sampled only from
-- areas/times with adequate observation coverage. The ML training pipeline that
-- would consume labels reads that future table, never this catalog, so a catalog
-- row can never masquerade as a confirmed event or a label. Twin of cwc_resources
-- (distinct source_url per row). Flood and landslide labels are kept separate.
CREATE TABLE IF NOT EXISTS historical_sources (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'historical',
    source_key      TEXT NOT NULL,             -- registry key, e.g. 'nrsc_landslide_atlas'
    hazard          TEXT,                      -- FLOOD | LANDSLIDE | FLOOD_OR_LANDSLIDE (verbatim)
    role            TEXT,                      -- verified role, e.g. 'historical_landslide_inventory'
    source_url      TEXT,                      -- verified official source URL (never fabricated)
    period          TEXT,                      -- verified temporal coverage (verbatim, e.g. '1998-2022')
    access_note     TEXT,                      -- e.g. 'portal/authentication dependent' when reported
    stage           TEXT NOT NULL DEFAULT 'CATALOG_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                      -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, source_key, source_url)     -- idempotent re-catalog
);
CREATE INDEX IF NOT EXISTS ix_histsource_key ON historical_sources(source_key);

-- ---- NDEM capability catalog (verified source #10, CATALOG-ONLY) ------------
-- NDEM (National Database for Emergency Management) is an NRSC/ISRO national GIS
-- repository + DSS for disaster management. The verified note (ndem_verified.md)
-- is explicit: NDEM's non-base products are PROTECTED and require authorized
-- credentials (Central/State/District/NDRF/SDRF officials); only public/base
-- layers may be visible without login. The vendored package therefore implements
-- ONLY public-portal discovery + a capability/access registry and "does not invent
-- private API endpoints" and must "never bypass authentication". So this table
-- catalogs the verified NDEM CAPABILITIES (name + access level + role + portal URL)
-- ONLY. It carries NO measurement, NO geometry, NO event and NO risk score. The
-- verified engineering decision is explicit that access_level and source-health are
-- stored SEPARATELY from any risk score — so `access` here is a capability-access
-- classification (PUBLIC | AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC), copied
-- verbatim from the registry, never a data value. The ML pipeline never reads this
-- catalog, so a catalog row can never masquerade as a flood/landslide value. Every
-- NDEM capability shares the SAME public portal URL (like GSI/LGD), so capability_key
-- is what keeps rows distinct. `stage` is an observation-stage flag
-- (CATALOG_ONLY | PARSED), NOT a source-health status.
CREATE TABLE IF NOT EXISTS ndem_capabilities (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL DEFAULT 'ndem',
    capability_key  TEXT NOT NULL,             -- registry key, e.g. 'near_real_time_flood'
    access          TEXT,                      -- PUBLIC | AUTHORIZED | AUTHORIZED_OR_PRODUCT_SPECIFIC (verbatim)
    role            TEXT,                      -- verified role, e.g. 'near-real-time flood products'
    source_url      TEXT,                      -- verified NDEM portal URL (never fabricated, never a private API)
    stage           TEXT NOT NULL DEFAULT 'CATALOG_ONLY',  -- observation-stage flag, NOT a source health status
    raw_reference   TEXT,                      -- opaque provenance blob (JSON)
    retrieved_at    TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, capability_key, source_url) -- idempotent re-catalog
);
CREATE INDEX IF NOT EXISTS ix_ndemcap_key ON ndem_capabilities(capability_key);

-- ---- Weather forecasts ------------------------------------------------------
CREATE TABLE IF NOT EXISTS weather_forecasts (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    latitude        REAL, longitude REAL,
    issued_at       TEXT NOT NULL,
    forecast_time   TEXT NOT NULL,
    rainfall        REAL,                    -- mm expected in horizon
    severity        TEXT,                    -- none|watch|warning|severe
    horizon_hours   REAL,
    realtime_class  TEXT,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(source, issued_at, forecast_time, latitude, longitude)
);

-- ---- Landslide data (susceptibility / forecast / inventory) -----------------
CREATE TABLE IF NOT EXISTS landslide_data (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    event_time      TEXT,                    -- null for static susceptibility
    latitude        REAL, longitude REAL,
    geometry_geojson TEXT,
    susceptibility  REAL,                    -- 0..1 prototype scale
    impact_probability REAL,
    severity        TEXT,
    is_synthetic    INTEGER NOT NULL DEFAULT 0,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ---- Flood events (historical labels + inventory) ---------------------------
CREATE TABLE IF NOT EXISTS flood_events (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    event_time      TEXT,
    latitude        REAL, longitude REAL,
    geometry_geojson TEXT,
    severity        TEXT,
    is_synthetic    INTEGER NOT NULL DEFAULT 0,
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ---- IoT observations (our own real-time layer) -----------------------------
CREATE TABLE IF NOT EXISTS iot_observations (
    id              INTEGER PRIMARY KEY,
    sensor_id       TEXT NOT NULL,
    ts              TEXT NOT NULL,
    latitude        REAL, longitude REAL,
    rainfall        REAL,        -- mm
    soil_moisture   REAL,        -- %
    water_level     REAL,        -- m
    temperature     REAL,        -- °C
    quality_flag    TEXT NOT NULL DEFAULT 'GOOD',
    is_simulated    INTEGER NOT NULL DEFAULT 1,   -- demo stream = simulated, labelled
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(sensor_id, ts)
);
CREATE INDEX IF NOT EXISTS ix_iot_ts ON iot_observations(ts);

-- ---- IoT raw telemetry (unmapped public/third-party feeds) ------------------
CREATE TABLE IF NOT EXISTS iot_raw_telemetry (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,               -- e.g. thingspeak
    channel_id      TEXT NOT NULL,               -- e.g. 3368421
    entry_id        INTEGER NOT NULL,            -- sequential feed entry id
    ts              TEXT NOT NULL,               -- original feed timestamp (UTC)
    raw_payload     TEXT NOT NULL,               -- JSON payload string
    quality_flag    TEXT NOT NULL DEFAULT 'GOOD',
    ingested_at     TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    UNIQUE(channel_id, entry_id)
);
CREATE INDEX IF NOT EXISTS ix_iot_raw_ts ON iot_raw_telemetry(ts);

-- ---- Predictions ------------------------------------------------------------
CREATE TABLE IF NOT EXISTS predictions (
    id              INTEGER PRIMARY KEY,
    location_id     INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    ts              TEXT NOT NULL,           -- prediction timestamp (UTC)
    horizon         TEXT NOT NULL,           -- now|15m|30m|1h|3h|6h
    flood_probability     REAL,
    landslide_probability REAL,
    risk_level      TEXT,                    -- LOW|MODERATE|HIGH|CRITICAL
    confidence      REAL,                    -- 0..1
    lead_time_min_lo INTEGER,                -- estimated high-risk window (minutes)
    lead_time_min_hi INTEGER,
    data_completeness REAL,                  -- 0..1 (available/expected sources)
    top_factors     TEXT,                    -- JSON array of {factor, contribution}
    model_version   TEXT,
    mode            TEXT,                    -- live|replay|simulation
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_pred_loc ON predictions(location_id);
CREATE INDEX IF NOT EXISTS ix_pred_ts ON predictions(ts);

-- ---- Evacuation Centres (SIH 26192) -----------------------------------------
CREATE TABLE IF NOT EXISTS evacuation_centres (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    address         TEXT,
    village         TEXT NOT NULL,
    ward            TEXT,
    district        TEXT NOT NULL,
    latitude        REAL NOT NULL,
    longitude       REAL NOT NULL,
    capacity        INTEGER NOT NULL DEFAULT 100,
    contact_number  TEXT,
    accessibility   TEXT,
    verified        INTEGER NOT NULL DEFAULT 1,
    active          INTEGER NOT NULL DEFAULT 1,
    is_demo         INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_evac_village ON evacuation_centres(village);
CREATE INDEX IF NOT EXISTS ix_evac_district ON evacuation_centres(district);

-- ---- Alert Recipients (SIH 26192) -------------------------------------------
CREATE TABLE IF NOT EXISTS alert_recipients (
    id              INTEGER PRIMARY KEY,
    name            TEXT NOT NULL,
    phone_number    TEXT NOT NULL,
    village         TEXT NOT NULL,
    ward            TEXT,
    district        TEXT NOT NULL,
    preferred_language TEXT NOT NULL DEFAULT 'en', -- en|hi|ta
    active          INTEGER NOT NULL DEFAULT 1,
    emergency_notification_enabled INTEGER NOT NULL DEFAULT 1,
    is_demo         INTEGER NOT NULL DEFAULT 1,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_recip_village ON alert_recipients(village);

-- ---- Alerts -----------------------------------------------------------------
CREATE TABLE IF NOT EXISTS alerts (
    id              INTEGER PRIMARY KEY,
    location_id     INTEGER NOT NULL REFERENCES locations(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now')),
    severity        TEXT NOT NULL,           -- INFO|WATCH|WARNING|CRITICAL
    hazard_type     TEXT NOT NULL,           -- flood|landslide|combined
    message         TEXT NOT NULL,
    prediction_id   INTEGER REFERENCES predictions(id),
    status          TEXT NOT NULL DEFAULT 'active',  -- active|acknowledged|expired
    mode            TEXT,
    risk_level      TEXT,                    -- LOW|MODERATE|HIGH|CRITICAL
    risk_probability REAL,
    lead_time_window TEXT,
    evacuation_centre_id INTEGER REFERENCES evacuation_centres(id),
    evacuation_guidance TEXT,
    recipient_count INTEGER DEFAULT 0,
    sms_status      TEXT DEFAULT 'PENDING',  -- PENDING|MOCK_SENT|SENT|SUPPRESSED|FAILED
    push_status     TEXT DEFAULT 'PENDING',  -- PENDING|MOCK_SENT|SENT
    fingerprint     TEXT,
    dispatched_at   TEXT
);
CREATE INDEX IF NOT EXISTS ix_alert_loc ON alerts(location_id);
CREATE INDEX IF NOT EXISTS ix_alert_fingerprint ON alerts(fingerprint);

-- ---- Source health (sections 24, 32) ----------------------------------------
CREATE TABLE IF NOT EXISTS source_health (
    source          TEXT PRIMARY KEY,
    status          TEXT NOT NULL DEFAULT 'unknown',  -- online|delayed|offline|unknown
    last_success_at TEXT,
    last_attempt_at TEXT,
    last_latency_ms INTEGER,
    last_error      TEXT,
    records_last_run INTEGER,
    updated_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);

-- ---- Data quality flags log (section 11) ------------------------------------
CREATE TABLE IF NOT EXISTS data_quality_flags (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    table_name      TEXT NOT NULL,
    ts              TEXT,
    flag            TEXT NOT NULL,           -- GOOD|WARNING|BAD|MISSING|STALE
    reason          TEXT,
    created_at      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ','now'))
);
CREATE INDEX IF NOT EXISTS ix_dq_source ON data_quality_flags(source);

-- ---- Ingestion run log (section 34) -----------------------------------------
CREATE TABLE IF NOT EXISTS ingestion_log (
    id              INTEGER PRIMARY KEY,
    source          TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT,                    -- ok|error|partial
    records_received INTEGER DEFAULT 0,
    records_stored   INTEGER DEFAULT 0,
    records_rejected INTEGER DEFAULT 0,
    latency_ms      INTEGER,
    error           TEXT
);
CREATE INDEX IF NOT EXISTS ix_inglog_source ON ingestion_log(source);
