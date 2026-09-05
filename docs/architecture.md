# Architecture — SIH 2026 PS 26192 Flash Flood Prediction System

## 1. Pipeline (master prompt section 2 — non-negotiable)

```
External sources
      ↓
Independent collectors        (one per source; isolate external change)
      ↓
Ingestion layer               (idempotent, dedup, status)
      ↓
Validation / Quality Control  (GOOD/WARNING/BAD/MISSING/STALE flags)
      ↓
Normalization                 (mm, °C, m, UTC, EPSG:4326)
      ↓
PostgreSQL + PostGIS          (time-series + geometry + rasters-derived)
      ↓
Feature engineering           (rainfall windows, soil, river trend, terrain, history)
      ↓
ML engine  (flood model  +  landslide model)   — reads ONLY internal tables
      ↓
Risk fusion (ML prob + physical rules + data quality + susceptibility)
      ↓
Risk + Confidence + Lead-time  (prediction DB)
      ↓
Backend API
      ↓
GIS dashboard  /  Alerts  /  Response support
```

**The rule that makes this defensible:** the ML/risk engine reads **only
normalized internal tables**. External APIs never feed the model directly. If
NASA changes IMERG, only `gpm_collector` changes.

## 2. Collector contract

Every collector — real or replay/mock — implements the same interface so the
rest of the system cannot tell them apart:

```
class BaseCollector:
    source_key: str
    def fetch(self, window) -> RawBatch          # network / file / replay
    def validate(self, raw) -> list[Issue]       # QC before it enters the DB
    def normalize(self, raw) -> list[Observation]# units, CRS, time -> canonical
    def store(self, observations) -> StoreResult # idempotent upsert
    def report_status(self) -> SourceHealth      # for /data-sources/status
```

Idempotency: each observation has a natural key `(source, variable, ts, lat,
lon[, station_id])`; re-ingesting the same batch updates in place, never
duplicates (section 7).

## 3. Two-track implementation (same architecture, swappable adapters)

The build environment cannot run Docker/PostGIS/FastAPI/React, so we ship two
tracks that share module boundaries and function signatures. Moving A→B is an
adapter swap, documented per section 70 — not a redesign.

| Concern | Track A — Portable core (RUNS in-env, proven) | Track B — Production (run locally on Windows+Docker) |
|---|---|---|
| API | stdlib `http.server` | FastAPI + Uvicorn |
| DB | SQLite + JSON geometry + pure-Python spatial ops | PostgreSQL + PostGIS |
| ML | from-scratch numpy models | XGBoost / LightGBM |
| GIS | pure-Python point-in-polygon / bbox index | GeoPandas / Shapely / Rasterio / GDAL |
| Frontend | single-file Leaflet (CDN) | React + TS + Tailwind + MapLibre |
| Scheduler | in-process loop | APScheduler → Celery+Redis |
| Deploy | `python3` only | Docker Compose |

The **repository/DAL layer** is the seam: `backend/app/database/` exposes the
same repository methods; Track A implements them on SQLite, Track B on
PostGIS. Everything above the DAL (features, models, risk, alerts, API shapes)
is shared logic.

## 4. Modes (section 41, 64)

`APP_MODE ∈ {live, near_real_time, replay, simulation}`. The dashboard badges
every layer LIVE / NEAR-REAL-TIME / STALE / SIMULATED / REPLAY. Replay uses the
**same** collector→validation→…→risk path as live data; only the collector's
`fetch()` source differs. This guarantees the SIH demo does not depend on a
government API being up at judging time — and never mislabels replayed data as
real.

## 5. Flows

**Scheduled:** each source polled at its real cadence (from the registry, once
verified). **Event-driven:** an IoT spike / rapid river rise / new severe
warning triggers immediate feature-rebuild → prediction → risk-change check →
alert (section 9). **Failure:** a down source is marked missing, source_health
records it, confidence drops, valid fallback used if any, degradation logged —
never silent fake data (section 32). **Replay:** historical event streamed
through the real pipeline for demonstration.

## 6. Confidence vs risk (kept strictly separate — section 21)

`risk_level` comes from ML + rules; `confidence` comes from data availability +
freshness + quality + source agreement + model uncertainty. **HIGH RISK + LOW
CONFIDENCE is a valid, expected state** and is shown as such.

## 7. Disaster-safety posture (sections 48, 69)

Decision-support only. Language is always "estimated risk" / "estimated
high-risk window", never "flood will happen" or an exact arrival time. Official
emergency instructions override the prototype. Prototype thresholds are labelled
as prototype thresholds, never as official government rules.

## 8. Hyper-local without over-claiming (sections 3, 13)

```
coarse satellite pixel  ⨯  fine terrain (slope/flow)  ⨯  admin polygon
                        ⨯  local obs (station/IoT)  ⨯  hydrology
                                     ↓  spatial fusion
                        local risk estimate  +  explicit resolution/confidence
```

We store and display the spatial resolution and data confidence of every
contribution, so a village-level number always carries its provenance.
