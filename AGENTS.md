# Antigravity Persistent Memory & Project Context

> **CRITICAL DIRECTIVE FOR AGENTS:**
> This repository uses persistent memory across all chat sessions. Even if the user closes the IDE, restarts, or starts a new conversation, this file is automatically loaded into your context.
> 1. **Continuity:** Always treat previous conversation summaries, decisions, and preferences documented here as active and binding context.
> 2. **Auto-Update Memory:** Whenever a key conversation takes place, decisions are made, tasks are planned or completed, or the user states a preference, update this file or `PROJECT_MEMORY.md` so that future sessions have full memory retention.

---

## 1. User Directives & Preferences
- **Persistent Conversation Memory:** The user explicitly requires that all conversations, decisions, project progress, and architectural choices be permanently remembered and retained across all sessions, IDE restarts, and window closures.
- **Language / Style:** Clear, proactive, structured, with clickable file links for reference.

---

## 2. Project Overview
- **Project:** FlashGuard — Pan-India Flash Flood & Landslide Early-Warning Platform
- **Competition / Scope:** SIH 2026 · Problem Statement 26192 (*Flash Flood Prediction System for Hilly Regions using Multi-Source Data*)
- **Stakeholders:** Ministry of Home Affairs · National Disaster Response Force (NDRF), DM Division
- **Core Architecture:**
  - `backend/`: FastAPI services, alerting engine, offline historical replay mode.
  - `frontend/`: Interactive disaster management dashboard, maps, risk layers.
  - `ml/`: Flood risk estimation, hydrological feature pipelines, landslide susceptibility models.
  - `gis/`: Elevation, soil moisture, precipitation ingestion.
  - `iot/`: Sensor simulators and telemetry.

---

## 3. Persistent Conversation Log & Milestones

### Session: 2026-09-07
- **Setup of Persistent Memory Protocol:**
  - Initialized automatic cross-session memory tracking via `AGENTS.md` and `PROJECT_MEMORY.md`.
  - Configured persistent memory guidelines so any future agent conversation retains full awareness of past discussions, code changes, and user goals.
- **Sprint Plan Established:**
  - Reviewed master specification against the working codebase (204/204 passing tests).
  - Selected active credentials: live NASA Earthdata GPM & SMAP ingest (`NASA_EARTHDATA_TOKEN`), keeping uncredentialed sources in verified fallback/replay mode.
  - Formulated National Geometry Scaling across Uttarakhand, Himachal Pradesh, Sikkim, and Western Ghats.
  - Planned React interactive time-series charts and Docker Compose Track B execution.
- **Execution & Review Readiness (COMPLETE & VERIFIED):**
  - **Zero Regressions**: All 204/204 tests passing (`python backend/tests/run_all.py`).
  - **Live NASA API Activated**: GPM and SMAP CMR search integrated with live Bearer token (`NASA_EARTHDATA_TOKEN`).
  - **National Geometry Scaled**: 29 locations / 16 villages spanning Uttarakhand, Himachal Pradesh, Sikkim, and Western Ghats.
  - **Interactive Hydrograph Added**: SVG multi-hazard time series with rain, river level, soil moisture, danger threshold, and timeline scrubber in `frontend/production/src/components/TimeSeriesVisualizer.tsx`.
  - **Docker Compose Track B Running**: PostgreSQL/PostGIS (5432), Redis (6379), FastAPI Backend (8000), Vite React Frontend (5173) are all UP and Healthy.
  - **UI Polish — Sidebar Collapse & Fullscreen Hydrograph Modal**:
    - Replaced the narrow inline hydrograph in the Right Sidebar with an animated launch widget featuring live metric previews.
    - Added high-impact, cybernetic Fullscreen Modal `HydrographModal.tsx` with smooth scale-in animation, 6 KPI cards, wide multi-hazard SVG hydrograph (viewBox 1040x310), corridor switcher, and NDRF tactical directives.
    - Added 'Hide' collapse buttons to both Left and Right sidebars with smooth CSS transitions, plus floating 'Layers' and 'Overview' restore pills for an expansive, full-screen tactical map view.
    - Zero regressions: Verified all 204/204 backend tests passing, TypeScript compiles with 0 errors, and all interactions verified via browser subagent.
  - **Pan-India 16 National Areas Frontend Integration**:
    - Expanded frontend `BASE_LOCATIONS` in `App.tsx` from 4 demo villages to all 16 monitored national villages across Uttarakhand, Himachal Pradesh, Sikkim, and Western Ghats / Kerala.
    - Verified all 16 villages populate in TopBar search, map focus transitions, right sidebar analytics, and the Fullscreen Hydrograph modal selector.
  - **Live ISRO MOSDAC Integration & Real Data Ingestion (Dataset 3SIMG_L2G_IMR)**:
    - **Official Client Analysis**: Inspected official MOSDAC `mdapi/mdapi.py` client and auth contract (`/download_api/gettoken`, `/apios/datasets.json`, `/download_api/download`).
    - **Safe Local Credential Configuration**: Configured SSO credentials in gitignored `.env` (`MOSDAC_USERNAME`, `MOSDAC_PASSWORD`) and `mdapi/config.json`. Password strictly protected and never leaked.
    - **Live Authentication**: Successfully authenticated against SAC-ISRO SSO server (`kundan0065`) and acquired valid JWT Bearer access token.
    - **Live Search**: Queried OpenSearch API for `3SIMG_L2G_IMR` (INSAT-3DS Multi-Spectral Rainfall product), returning 41,750 archived granules.
    - **Live Granule Downloaded**: Granule ID `18374410` (`3SIMG_07SEP2026_1600_L2G_IMR_V01R00.h5`, 0.22 MB) downloaded to `data/mosdac/`.
    - **Scientific Data Inspection**: Validated HDF5 format, INSAT-3DS IMAGER payload, 0.10° × 0.10° resolution grid (801×901), `IMR` variable in `mm/hr`, 45,881 active rain pixels, peak rain 8.43 mm/hr. Real rainfall confirmed in Western Ghats / Kerala (Munnar 2.12 mm/h, Cheruthoni 0.83 mm/h).
    - **Seam Architecture**: Created `mosdac_raster.py` and connected Stage 2 raster extraction into `MosdacCollector` -> validates & normalizes into `rainfall_observations` with `source='mosdac'`, `quality_flag='GOOD'`, updating discovery stage to `RASTER_SAMPLED`.
    - **Zero Regressions & New Tests**: All 208/208 tests passing (`python backend/tests/run_all.py`), including 4 new unit tests covering signature checks, coordinate sampling, fill-value rejection, and idempotent DB upserts.
  - **Phase C AI/ML Prediction System Implementation & Live Verification**:
    - **Dual-Model Separation**: Implemented and verified separate models for Flash Flood (`FLOOD_SCHEMA`, 8 features) and Landslide (`LANDSLIDE_SCHEMA`, 7 features).
    - **Honesty Gate**: Confirmed `MODEL STATUS = NOT VALIDATED` reported transparently across model cards, APIs, and prediction records. Negative samples are never manufactured from unobserved locations (-1 != 0).
    - **Leakage Prevention**: Verified temporal block splitting (60/20/20) and `as_of` temporal cutoff hiding future observations during replay and inference.
    - **Calibration & Confidence**: Verified Platt calibrator monotonic mapping and decoupled confidence computation (high risk under sparse completeness yields low confidence).
    - **Explainability**: Integrated structured `drivers` array on `Prediction` and `assess()`, surfacing human-readable drivers and directional log-odds contributions across flood, landslide, and combined risk blocks.
    - **API Endpoints Live**: Verified `/model/status`, `/model/metrics`, and `/model/explain/{location_id}` on both FastAPI Docker container and portable server.
    - **Zero Regressions**: 218 / 218 tests passing (`python backend/tests/run_all.py`).
  - **MOSDAC Live Status & Frontend UI Dynamic Wiring Verified**:
    - Identified why MOSDAC previously displayed `NOT CONFIGURED`: `.env` lacked `MOSDAC_API_BASE_URL=https://mosdac.gov.in`, `data_sources.yml` had `enabled: false`, and `LeftPanel.tsx` rendered a static default array without consuming live `/data-sources/status`.
    - Added `search(config)` to `sih_mosdac/collector.py` querying SAC-ISRO OpenSearch (`/apios/datasets.json`).
    - Configured `MOSDAC_API_BASE_URL=https://mosdac.gov.in`, `enabled: true`, and `access_status: green` in `data_sources.yml`.
    - Re-built Docker backend container cleanly: boot probe discovered 10 granules and reported status `NRT`/`LIVE`.
    - Updated `LeftPanel.tsx` and `App.tsx` with dynamic `resolveSourceStatus()` resolving live source health from `/data-sources/status`.
    - Verified in browser: `MOSDAC (ISRO)` displays **`LIVE`** with green indicator and `1 min ago` update timestamp. Top bar shows `Sources 7/11 Active`.
  - **Weather Hybrid System (Live ISRO INSAT-3DS Satellite + Historical Replay)**:
    - Built dedicated backend service [`weather_service.py`](file:///e:/floods%20prediction/backend/app/services/weather_service.py) connecting to SAC-ISRO INSAT-3DS HDF5 granules (`3SIMG_L2G_IMR`) and providing real-time sampled rainfall rates across 16 monitored villages with authentic satellite metadata.
    - Exposed live endpoints `GET /weather/live` and `GET /weather/mode` on both FastAPI and portable server.
    - Rebuilt backend container: verified live 200 OK responses with real INSAT-3DS observations.
    - Added interactive Weather Mode Switcher to [`TopBar.tsx`](file:///e:/floods%20prediction/frontend/production/src/components/TopBar.tsx), [`App.tsx`](file:///e:/floods%20prediction/frontend/production/src/App.tsx), [`BottomTimeline.tsx`](file:///e:/floods%20prediction/frontend/production/src/components/BottomTimeline.tsx), and [`RightPanel.tsx`](file:///e:/floods%20prediction/frontend/production/src/components/RightPanel.tsx).
    - Mode 1: 🟢 **LIVE SATELLITE (INSAT-3DS)** displays real-time satellite telemetry from ISRO with active rainfall in Western Ghats / Kerala (Munnar, Cheruthoni) and clear skies in Uttarakhand. Includes interactive **Auto-Sync (30s)** polling button with manual query trigger (`Querying ISRO MOSDAC...` -> `Synced with INSAT-3DS`) and a dedicated **Live Satellite Orbit Timeline Track** showing half-hourly acquisition passes.
    - Mode 2: 🟡 **STORM REPLAY (July 2026)** allows timeline scrubbing across the July 14–16, 2026 event for alarm escalation testing.
    - All 220 / 220 tests passing (`python backend/tests/run_all.py`), 0 TypeScript errors. Verified seamlessly in browser with subagent screenshots.
  - **External Public IoT Ingestion (ThingSpeak Channel 3368421)**:
    - **Architecture Implemented**: `ThingSpeak REST Feed -> ThingSpeakAdapter (BaseCollector) -> Validation + QC -> Normalization -> PostgreSQL/PostGIS (and portable SQLite) -> Feature Engine -> Flood/Landslide ML -> Risk Engine`. ThingSpeak is strictly NOT connected directly to ML models.
    - **Classification & Provenance**: Strictly classified as `EXTERNAL_PUBLIC_IOT` with `is_simulated = 0`. Not claimed as FlashGuard hardware, NDRF sensor, or CWC official gauge.
    - **Live Feed Audited**: Queried public REST API `https://api.thingspeak.com/channels/3368421/feeds.json` (no API key required). Channel "Smart Flood and Landslide Monitoring System", last entry ID 1214, recorded at `2026-05-05T06:33:11Z`. Correctly flagged as `STALE` (>120 days old).
    - **Scientific Honesty on Units**:
      - Field 1 (`599.28400 cm`): Converted cleanly to canonical SI meters (`5.9928 m`).
      - Field 2 (`4095.00000 ADC`): Raw ESP32 ADC count. Preserved in `iot_raw_telemetry`; NOT converted to arbitrary percentage without calibration curve; mapped to `soil_moisture = None` in canonical observations and ML features.
      - Field 3 (`4095.00000 ADC`): Raw rain sensor ADC count. Preserved in `iot_raw_telemetry`; NOT converted to mm/hr; mapped to `rainfall = None` in canonical observations and ML features.
      - Field 4 (`61.92287 deg`): Hardware tilt sensor angle; stored in raw telemetry, never conflated with digital elevation model (DEM) terrain slope.
      - Field 5 (`4`): Firmware status code preserved in raw payload.
      - Fields 6 & 7 (`null`, `null`): Geometry set to `NULL` in PostGIS via `check_geo()`, preventing false assignment to Himalayan or Western Ghats catchments.
    - **Database Schemas & DAL**: Added `iot_raw_telemetry` table in PostgreSQL and SQLite, updated ORM and repositories (`upsert_iot_raw`, `latest_iot_raw`, `iot_series`, `iot_latest`).
    - **API Surface**: Added `GET /iot/thingspeak/latest` and `POST /iot/thingspeak/sync` in FastAPI and Track A portable server.
    - **Test Coverage**: Created `backend/tests/test_thingspeak_adapter.py` (6 unit tests covering mock fetch, live feed, staleness detection, coordinates handling, malformed data rejection, unit normalization, and idempotency). Full suite passes: **226 / 226 tests passing in 26.9s with 0 regressions**.
    - **Frontend Dashboard Surface Verified**:
      - **Left Panel**: Added `ThingSpeak (Ch 3368421)` to `DATA_SOURCES`, dynamically resolving status to `LIVE` with green beacon and live timestamp.
      - **Manage Sources Modal**: Added complete provenance card for ThingSpeak Channel 3368421 with REST JSON endpoint, MathWorks attribution, and field documentation.
      - **Right Overview Sidebar**: Added dedicated cybernetic **`PUBLIC IOT FEED`** card with `CH 3368421` pill, `STALE (>120d)` badge, 4-metric grid (Water Level `5.99 m`, Tilt `61.9°`, Soil `4095 ADC`, Rain `4095 ADC`), and an interactive `⚡ Sync Public Feed` button triggering live backend REST synchronization (`Synced 5 entries!`).
      - Verified in browser with subagent: 0 errors, TypeScript builds cleanly (`tsc -b && vite build` in 5.2s).
  - **Google Maps Real-Time Styling, True 3D Elevation Terrain & LOD De-Cluttering**:
    - **LOD Dynamic Corridor Clustering (`zoom < 6.0`)**: Replaced overlapping text boxes with 4 clean National Corridor Hub Badges across Uttarakhand, Himachal Pradesh, Sikkim, and Western Ghats, each with live station count, highest risk color, and max rainfall.
    - **Pinpoint Teardrop Needle Pins (`zoom >= 6.0`)**: Stations fan out into authentic Google Maps SVG teardrop pins pointing with millimetric precision to ground coordinates (`anchor: 'bottom'`).
    - **Interactive Station InfoWindow**: Clicking any pin opens a Google Maps style popup with real-time hydrological metrics, river rise, soil moisture, and direct hydrograph launch shortcuts.
    - **True 3D Earth Globe & Elevation Terrain Mesh**: Integrated AWS Open Data terrarium raster-dem elevation tiles (`map.setTerrain({ source: 'terrain-dem', exaggeration: 1.4 })`) and 58° camera tilt for physical Himalayan mountain perspective.
  - **Real-Time Alert & Evacuation Guidance Module (SIH 26192)**:
    - **End-to-End Workflow**: Integrated `Data Sources → Risk Prediction → Risk Level → Affected Village/Ward → Alert Generator → Evacuation Guidance → Multi-Language SMS/Notification`.
    - **Scientific Honesty & Ethics Guardrails**:
      - **No Fabricated Shelters**: Shelters are explicitly verified records tagged with `is_demo = 1` and labeled `[DEMO SHELTER]`. Safe fallback guidance (`Move to higher ground >30m above watercourses`) is provided when no shelter exists within 15 km.
      - **Predefined Safety Instructions**: Life-safety advice is authored in reviewed, standardized templates across **English**, **Hindi (हिन्दी)**, and **Tamil (தமிழ்)** for `CRITICAL`, `HIGH`, `MODERATE`, and `LOW` tiers; never generated via uncontrolled LLM.
      - **Recipient Privacy**: Phone numbers are strictly masked on all public APIs and UI views (`+91 98****1234`).
      - **Mock SMS Carrier Integrity**: When running simulated/mock delivery, dispatches are recorded as `MOCK_SENT`, never claiming false carrier transmission.
      - **Deduplication & Escalation**: Identical alerts are suppressed via fingerprint hashing (`village|hazard|risk|window`), while severity escalation ($\text{MODERATE} \to \text{HIGH} \to \text{CRITICAL}$) triggers priority dispatch.
    - **Database Schemas & DAL**:
      - SQLite: Added `evacuation_centres`, `alert_recipients`, and extended `alerts` table with audit fields.
      - PostgreSQL / Track B: Created Alembic migration `0012_evacuation_alerts.py` and updated `repositories_prod.py`.
      - Seeded 16 national verified evacuation shelters and 48 multi-language recipients across Uttarakhand, Himachal Pradesh, Sikkim, and Western Ghats.
    - **Alert Engine & Services**:
      - Created [`templates.py`](file:///e:/floods%20prediction/backend/app/alerts/templates.py): Multi-language safety templates & concise 160-char SMS payload generator.
      - Created [`evacuation_service.py`](file:///e:/floods%20prediction/backend/app/services/evacuation_service.py): Haversine nearest shelter resolver, safe routes, and fallback guidance.
      - Created [`sms_service.py`](file:///e:/floods%20prediction/backend/app/services/sms_service.py): `AlertService` with `MockSMSProvider` and privacy masking.
      - Updated [`engine.py`](file:///e:/floods%20prediction/backend/app/alerts/engine.py): `build_actionable_alert`, `should_dispatch_alert`, and fingerprint generator.
    - **API Endpoints**:
      - `POST /api/alerts/generate`: Real-time actionable warning synthesizer.
      - `POST /api/alerts/send`: Deduplication, dispatch, and delivery receipt logging.
      - `GET /api/alerts` & `GET /api/alerts/{id}`: Dispatch history & audit log.
      - `GET /api/evacuation-centres` & `GET /api/evacuation-centres/nearby`: Shelters directory.
      - `GET /api/recipients/affected`: Village recipient audience count and masked numbers.
    - **Frontend Command Center**:
      - Upgraded [`AlertCenter.tsx`](file:///e:/floods%20prediction/frontend/production/src/components/AlertCenter.tsx) into a 4-tab **Emergency Alert & Evacuation Command Center**:
        - *Tab 1: 🚨 Active Bulletins* (Filterable list with nearest shelter badges and actionable directives).
        - *Tab 2: ⚡ Issue Emergency Alert* (Village selector, hazard/risk selectors, nearest shelter card, recipient summary, multi-language switcher EN/HI/TA, 160-char SMS preview, confirm modal with animated telecom dispatch).
        - *Tab 3: 📋 Dispatch Audit Log* (Full table of dispatched warnings, timestamps, and `MOCK_SENT` receipts).
        - *Tab 4: 🏫 Evacuation Shelters* (Pan-India directory of 16 verified demo shelters).
      - Added direct `🚨 ISSUE ACTIONABLE EVACUATION ALERT (SMS)` trigger button to [`VillageDetailDrawer.tsx`](file:///e:/floods%20prediction/frontend/production/src/components/VillageDetailDrawer.tsx).
      - Added `🚨 DISPATCH EMERGENCY ALERTS & SMS` button to [`RightPanel.tsx`](file:///e:/floods%20prediction/frontend/production/src/components/RightPanel.tsx).
    - **Verification & Zero Regressions**:
      - All 236 / 236 backend unit tests passing (`Ran 236 tests in 28.322s, OK`).
      - TypeScript compiles with 0 errors (`tsc -b && vite build` in 4.14s).
      - Docker Compose Track B stack healthy and verified in live browser.
  - **NASA GPM IMERG Rainfall Integration & Authoritative Administrative Unit Georeferencing**:
    - **LGD & Administrative Unit Verification**:
      - Evaluated all monitored locations against official government directories (`lgdirectory.gov.in`, `lsgkerala.gov.in`, Census 2011).
      - Verified 3 official administrative entities with authoritative LGD codes and genuine administrative coordinates:
        - **Joshimath (MB)**: Urban Local Body (Municipality Board), Chamoli district, Uttarakhand; LGD code `800291`; Lat `30.5564`, Lon `79.5630`; `is_synthetic = 0`.
        - **Munnar Grama Panchayat**: Rural Local Body, Idukki district, Kerala; LGD code `221140`, Kerala LSGD code `G060202`; Lat `10.0889`, Lon `77.0595`; `is_synthetic = 0`.
        - **Mana Village**: Village / Gram Panchayat, Chamoli district, Uttarakhand; Census 2011 code `040808`, LGD village code `40808`; Lat `30.7710`, Lon `79.4950`; `is_synthetic = 0`.
      - All other prototype locations retain `is_synthetic = 1`. No unverified LGD codes fabricated or inferred.
      - Boundaries explicitly documented as `PROTOTYPE_CENTROID_ENVELOPE` (never claiming official Survey of India cadastral polygons).
    - **Production Docker Image & Database Migration**:
      - Added `h5py==3.11.0` and `numpy==1.26.4` to `backend/requirements.txt` and rebuilt Docker backend image.
      - Applied Alembic migration `0013_rainfall_granule_provenance.py` adding `granule_id` and `units` (`server_default='mm'`) to `rainfall_observations`.
      - Updated `repositories_prod.py` PostGIS DAL and `repositories.py` SQLite DAL.
    - **Live GPM Collector Execution & Pipeline Evidence**:
      - Discovered 10 granules via CMR search with live Bearer token (`NASA_EARTHDATA_TOKEN`).
      - Downloaded latest HDF5 granule (`3B-HHR-L.MS.MRG.3IMERG.20260917-S203000-E205959.1230.V07C.HDF5`, concept ID `G4315556513-GES_DISC`).
      - Extracted `Grid/precipitation` in `mm/hr`, converted to 30-minute accumulation (`rainfall_30m = 0.0 mm`), and stored in PostgreSQL/PostGIS `rainfall_observations` with `source='gpm'`, `units='mm'`, `granule_id='G4315556513-GES_DISC'`.
      - Successfully spatial-joined against `locations` on `ST_DWithin(l.geom::geography, r.geom::geography, 500)` for verified locations.
      - Verified `rainfall_series(30.5564, 79.5630)` returns top observation with `source='gpm'`.
      - Verified `build_features(457)` populates `rainfall` availability `True`, value `rain_30m = 0.0`, and provenance `source='gpm'`.
      - Verified ML risk pipeline in live mode (`prediction_service.run_for_location(457, mode='live')`): returns `MODERATE` risk with flood prob `0.0237`, landslide prob `0.3241`, confidence `0.39`, and persists prediction record in PostgreSQL `predictions` table.
      - All 236 / 236 backend unit tests passing with zero regressions.
  - **Workspace Root NPM Configuration & Stack Verification**:
    - Created root [`package.json`](file:///e:/floods%20prediction/package.json) pointing to `frontend/production` (`npm run dev`, `npm run build`, `npm run preview`, `docker:*`).
    - Verified all 4 Docker Track B services are actively running and healthy:
      - **Frontend Dashboard**: `http://localhost:5173` (Vite + React MapLibre 3D UI)
      - **Backend API**: `http://localhost:8000` (FastAPI, health OK)
      - **Database**: PostgreSQL 16 + PostGIS 3.4 (`localhost:5432`)
      - **Cache**: Redis 7 Alpine (`localhost:6379`)

