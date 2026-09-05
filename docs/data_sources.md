# Data Source Master Table — SIH 2026 PS 26192

**Flash Flood Prediction System for Hilly Regions using Multi-Source Data**
Ministry of Home Affairs · NDRF, DM Division · Software · Disaster Management

---

## ⚠️ Verification status notice

This project separates **software engineering** (done in-environment) from
**external data-source verification** (done by ChatGPT via live web research —
master prompt sections 60–63). The build environment has **no live web
access**, so this document does **not** assert endpoints, resolutions, auth
mechanisms, latencies, or update frequencies from memory.

Every unverified external field is written literally as
`EXTERNAL VERIFICATION REQUIRED`. This is deliberate (sections 40, 57, 62,
67): a placeholder must never be mistaken for a fact in front of judges.

As ChatGPT delivers a verified specification for a source, we:
1. fill the real values in `backend/app/config/data_sources.yml`,
2. set `verified: true` + `verified_on`,
3. update the access-status triage below,
4. implement/enable that collector,
5. update this table.

**Access-status triage**

| Status | Meaning |
|--------|---------|
| 🟢 GREEN | Verified and programmatically usable now |
| 🟡 YELLOW | Usable but needs registration / manual step / license acceptance |
| 🔴 RED | Not currently accessible programmatically → adapter + manual import |
| ⚪ UNKNOWN | Not yet verified (default for all external sources) |

Current triage: **11 external sources ⚪ UNKNOWN (pending ChatGPT), 1 internal (IoT) 🟢**.
No source has been verified yet, so nothing is marked GREEN/YELLOW/RED on evidence.

---

## Master table

For each source: **What · Why · Source · Access · API · Authentication ·
Update · Resolution · Latency · Coverage · Data format · How our backend
consumes it · Fallback · Status** (master prompt section 50).

### 1. NASA GPM IMERG
- **What:** Satellite precipitation product.
- **Why:** Rainfall intensity, cumulative rainfall, trends, short-term & near-real-time precipitation features.
- **Source / Official URL:** EXTERNAL VERIFICATION REQUIRED
- **Access / API URL:** EXTERNAL VERIFICATION REQUIRED
- **Authentication:** EXTERNAL VERIFICATION REQUIRED (env: `NASA_EARTHDATA_TOKEN`)
- **Update frequency:** EXTERNAL VERIFICATION REQUIRED
- **Spatial / temporal resolution:** EXTERNAL VERIFICATION REQUIRED
- **Latency:** EXTERNAL VERIFICATION REQUIRED (structurally: near-real-time)
- **Coverage:** EXTERNAL VERIFICATION REQUIRED
- **Data format:** EXTERNAL VERIFICATION REQUIRED
- **How our backend consumes it:** `gpm_collector` → `fetch/validate/normalize/store` → `rainfall_observations` (mm, UTC, WGS84). ML never reads GPM directly.
- **Fallback:** IMD rainfall (if verified) else terrain+other signals with reduced confidence.
- **Status:** ⚪ UNKNOWN — pending verified spec.

### 2. India Meteorological Department (IMD)
- **What:** National met agency data/warnings.
- **Why:** Current weather, district rainfall, AWS/station obs, nowcast, forecasts, severe-weather warnings.
- **Source / API / Auth / Update / Resolution / Latency / Coverage / Format:** EXTERNAL VERIFICATION REQUIRED (env: `IMD_API_KEY`)
- **How our backend consumes it:** `imd_collector` → `rainfall_observations` + `weather_forecasts`.
- **Fallback:** GPM rainfall.
- **Status:** ⚪ UNKNOWN.

### 3. NASA SMAP
- **What:** Satellite soil-moisture product.
- **Why:** Surface & root-zone soil moisture; soil-saturation features (a key flash-flood/landslide precursor).
- **All external fields:** EXTERNAL VERIFICATION REQUIRED (env: `NASA_EARTHDATA_TOKEN`). Must distinguish NRT vs delayed vs historical products; never claim second-by-second real-time.
- **How our backend consumes it:** `smap_collector` → `soil_moisture_observations`.
- **Fallback:** none direct; feature marked missing, confidence reduced.
- **Status:** ⚪ UNKNOWN.

### 4. ISRO MOSDAC
- **What:** ISRO meteorological/oceanographic data centre (INSAT products).
- **Why:** INSAT met products, rainfall/cloud products, satellite-derived weather.
- **All external fields:** EXTERNAL VERIFICATION REQUIRED (env: `MOSDAC_API_KEY`).
- **How our backend consumes it:** `mosdac_collector` → `rainfall_observations`/`weather_forecasts`.
- **Fallback:** GPM.
- **Status:** ⚪ UNKNOWN.

### 5. Bhuvan / NRSC (DEM & terrain)
- **What:** Elevation / terrain layers (e.g. CartoDEM or other officially available DEM).
- **Why:** Derive slope, aspect, curvature, flow direction, flow accumulation, drainage density, watershed — the terrain half of hyper-local fusion. Static: preprocess once, store (section 14).
- **All external fields:** EXTERNAL VERIFICATION REQUIRED (env: `BHUVAN_API_KEY`).
- **How our backend consumes it:** `terrain_loader` (one-time) → `terrain_features`.
- **Fallback:** none; terrain is static and cached.
- **Status:** ⚪ UNKNOWN.

### 6. GSI / Bhusanket
- **What:** Geological Survey of India landslide resources.
- **Why:** Landslide inventory, susceptibility, forecast/impact probability, geo-hazard info.
- **All external fields:** EXTERNAL VERIFICATION REQUIRED (env: `GSI_API_KEY`).
- **How our backend consumes it:** `gsi_collector` → `landslide_data`.
- **Fallback:** static susceptibility layer if forecast unavailable.
- **Status:** ⚪ UNKNOWN.

### 7. CWC / NWIC
- **What:** Central Water Commission / National Water Informatics Centre hydrology.
- **Why:** River water level, station obs, inflow/outflow, flood forecasts, historical flood info.
- **All external fields:** EXTERNAL VERIFICATION REQUIRED (env: `CWC_API_KEY`).
- **How our backend consumes it:** `cwc_collector` → `river_observations` (+ `flood_events` historical).
- **Fallback:** continue on rainfall + terrain; river feature marked missing, confidence reduced.
- **Status:** ⚪ UNKNOWN.

### 8. NDEM / NRSC
- **What:** National Database for Emergency Management (disaster-data aggregation).
- **Why:** Aggregated disaster data, historical flood datasets, DM geospatial services.
- **All external fields:** EXTERNAL VERIFICATION REQUIRED (env: `NDEM_API_KEY`).
- **How our backend consumes it:** `ndem_collector` → `flood_events` / geospatial layers.
- **Fallback:** other historical sources.
- **Status:** ⚪ UNKNOWN.

### 9. Historical flood datasets
- **What:** India Flood Inventory / NDEM historical / satellite-derived flood maps / authoritative open datasets.
- **Why:** Supervised training labels (flood occurred / extent / event time / affected area).
- **All external fields:** EXTERNAL VERIFICATION REQUIRED.
- **How our backend consumes it:** `historical_loader` (manual-import adapter) → `flood_events`.
- **Fallback:** n/a (offline training data).
- **Status:** ⚪ UNKNOWN.

### 10. Historical landslide datasets
- **What:** GSI inventory / ISRO–NRSC Landslide Atlas / authoritative open datasets.
- **Why:** Supervised training labels (landslide occurred / date / location / severity).
- **All external fields:** EXTERNAL VERIFICATION REQUIRED.
- **How our backend consumes it:** `historical_loader` → `landslide_data`.
- **Fallback:** n/a.
- **Status:** ⚪ UNKNOWN.

### 11. Indian administrative boundaries
- **What:** India → state → district → subdistrict/block → village/ward polygons.
- **Why:** Spatial joins and drill-down; the polygon layer that turns coarse pixels into local estimates.
- **All external fields:** EXTERNAL VERIFICATION REQUIRED.
- **How our backend consumes it:** `boundary_loader` → `locations` (geometry).
- **Fallback:** n/a (static). Demo uses clearly-labelled synthetic polygons.
- **Status:** ⚪ UNKNOWN.

### 12. IoT sensors (ESP32) — our own component
- **What:** Optional hyper-local rain gauge / soil moisture / stream level / temperature.
- **Why:** Ground-truth, true real-time, enhancement layer. **Not** a national-coverage requirement (section 30).
- **Source:** internal. **API:** MQTT topic `sih26192/sensors/{sensor_id}` or HTTP POST. **Auth:** device shared secret (`IOT_DEVICE_SHARED_SECRET`).
- **Update:** continuous. **Resolution:** point. **Latency:** seconds. **Coverage:** wherever a device is deployed. **Format:** JSON.
- **How our backend consumes it:** `iot_consumer` → `iot_observations`; can trigger event-driven prediction (section 9).
- **Fallback:** satellite/government data continues if IoT offline.
- **Status:** 🟢 (internal). **Demo stream is clearly labelled SIMULATED.**

---

## Data-availability & honesty principles (enforced in code)

- A location works with **any** subset of sources; the system reports
  `data_completeness` (e.g. 4/6) and lowers `confidence` accordingly (sections 5, 21).
- Missing sources are marked MISSING, never silently replaced with fake values (section 5).
- Coarse satellite data is **never** presented as native village resolution;
  local estimates come from fusion of coarse + terrain + polygons + local obs (sections 3, 13).
- Every observation carries: source, timestamp, lat/lon, resolution, quality flag,
  ingestion time, missing flag, validation status (section 11).
- Data classes are badged LIVE / NEAR-REAL-TIME / STALE / SIMULATED / REPLAY (section 41).
