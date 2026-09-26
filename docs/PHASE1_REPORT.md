# FlashGuard — Phase 1 End Report

**Problem statement:** SIH 2026, PS 26192 — Flash Flood Prediction System for
Hilly Regions using Multi-Source Data (Ministry of Home Affairs / NDRF).
**Scope of Phase 1:** stand up the full architecture end-to-end on synthetic /
replay data, proven by tests and a real run, with a production stack scaffolded
for the user to run locally. **Report date:** 2026-09-06.

This report follows the section-71 checklist: files created, services, DB
tables, APIs, tests, tests passed/failed, run commands, known limitations, next
phase.

---

## 1. What was built — the two tracks

The architecture is fixed (External sources → independent collectors → ingestion
→ validation/QC → normalization → PostgreSQL+PostGIS → feature engineering →
ML/risk engine → prediction DB → backend API → GIS dashboard/alerts). ML reads
**only** normalized internal data.

It ships as **two tracks with identical module boundaries**, so moving from
prototype to production is an *adapter swap*, not a rewrite:

- **Track A — portable core (built, runs, and proven here).** Python **stdlib
  only** (`http.server` + `sqlite3`, numpy-free) + a single-file Leaflet
  dashboard. Runs in any constrained environment with no install step.
- **Track B — production stack (skeleton, pending local run).** FastAPI +
  PostgreSQL/PostGIS + SQLAlchemy/GeoAlchemy2 + Alembic + Redis + a React /
  TypeScript / MapLibre dashboard + Docker Compose. The build sandbox has no
  network egress, so `pip install` / `npm install` / Docker cannot run here;
  every Track B file is written against pinned deps and marked *pending local
  run*.

The seam that makes A→B an adapter swap: **all shared layers import the DAL as
`app.database.repositories`.** Track B provides `repositories_prod.py` with the
**same 20-function surface** over PostGIS and swaps it in at process start
(`sys.modules["app.database.repositories"] = repositories_prod`). Features,
models, risk engine, prediction service, replay driver and seed run **unchanged**
on either backend — verified by a surface-parity check (0 functions missing).

---

## 2. Files created

**Repo scaffold / docs:** `README.md`, `LICENSE`, `.gitignore`, `.env.example`,
`docs/architecture.md`, `docs/data_sources.md`, `docs/PHASE1_REPORT.md` (this
file). Registry dirs: `gis/`, `iot/`, `ml/`, `scripts/`, `data/replay/`.

**Backend application — 39 Python modules, ~3,331 LOC in `backend/app/`:**

| Layer | Files |
|---|---|
| Config | `config/settings.py` (pydantic-settings; env-only secrets) |
| Database (Track A) | `database/db.py`, `database/repositories.py`, `database/schema_sqlite.sql` |
| Database (Track B) | `database/models_orm.py`, `database/session.py`, `database/repositories_prod.py` |
| Collectors | `collectors/base.py`, `collectors/replay_collector.py`, `collectors/http_source_collector.py` |
| Processing | `processing/validate.py`, `processing/normalize.py` |
| Geospatial | `geospatial/spatial.py` (PIP, bbox, centroid, haversine, nearest) |
| Features | `features/engineer.py` (time-leakage-safe reads, completeness) |
| Models (demo) | `models/base_model.py`, `models/demo_models.py` |
| Risk | `risk/engine.py` (bands, rule floors, confidence, lead-time window) |
| Alerts | `alerts/engine.py` |
| Services | `services/seed.py`, `services/replay_driver.py`, `services/prediction_service.py`, `services/seed_prod.py` |
| API (Track A) | `portable/api.py`, `portable/run.py` |
| API (Track B) | `main.py` (FastAPI) |

**Migrations (Track B):** `backend/alembic.ini`, `backend/migrations/env.py`,
`backend/migrations/script.py.mako`, `backend/migrations/versions/0001_initial.py`.

**Dependencies / containers:** `backend/requirements.txt` (pinned),
`docker/docker-compose.yml`, `docker/backend.Dockerfile`.

**Frontend — Track A:** `frontend/portable/index.html` (single-file Leaflet
dashboard).
**Frontend — Track B:** `frontend/production/` — `package.json`, `Dockerfile`,
`.dockerignore`, `README.md`, `index.html`, `vite.config.ts`, `tsconfig.json`,
`src/main.tsx`, `src/api.ts`, `src/App.tsx` (React + MapLibre dashboard).

**Tests:** `backend/tests/_util.py` + 7 test modules + `run_all.py`.

**Replay dataset:** `data/replay/uttarakhand_flash_flood_event.json` (synthetic,
labelled) + `data/replay/README.md`.

---

## 3. Services

- **Track A portable API** — `python backend/app/portable/run.py` seeds →
  replays → serves a threaded stdlib HTTP API on `:8000`. **Runs today.**
- **Track B FastAPI app** — `uvicorn app.main:app`, same route surface, PostGIS
  backing. *Pending local run.*
- **Track B Docker Compose** — four services: `db` (postgis/postgis:16-3.4),
  `redis` (7-alpine), `backend` (migrate → `seed_prod` → uvicorn), `frontend`
  (Vite on :5173). Secrets are env-driven; no credentials committed. *Pending
  local run.*

---

## 4. Database tables

Track A `schema_sqlite.sql` and the Track B ORM/migration define the same core
entities. Tables: `locations`, `terrain_features`, `rainfall_observations`,
`soil_moisture_observations`, `river_observations`, `landslide_data`,
`iot_observations`, `weather_forecasts`, `flood_events`, `predictions`,
`alerts`, `source_health`, `ingestion_log`, `data_quality_flags`.

Track B `0001_initial.py` migrates the 10 load-bearing tables with real PostGIS
`geometry(...,4326)` columns and GiST spatial indexes (Track A stores GeoJSON
text + a bbox instead). Idempotent ingestion is enforced by natural-key UNIQUE
constraints (`uq_rain_natural`, `uq_soil_natural`, `uq_river_natural`,
`uq_iot_natural`, `locations.ext_code`).

---

## 5. APIs (identical contract on both tracks — `GET /contract`)

```
GET  /health                 GET  /risk                 GET  /alerts
GET  /system/status          GET  /risk/{id}            POST /prediction/run
GET  /data-sources/status    GET  /risk/map (GeoJSON)   POST /replay/run
GET  /locations              GET  /predictions/history  POST /iot/observations
GET  /locations/{id}         GET  /rainfall  /river-level
```

Each risk payload separates **risk** from **confidence**, reports
**data_completeness** (have ÷ expected sources), and gives an estimated
**high-risk window** (`lead_time_min_lo`–`hi`) — never an exact arrival time.
All responses carry the `DEMO MODEL — not validated` disclaimer.

---

## 6. Tests — written, run, and passing

**62 tests across 7 modules, all passing (0 failed).** Command:
`cd backend && python tests/run_all.py` (stdlib `unittest`, isolated temp DB via
`PORTABLE_DB_PATH`).

| Module | Tests | Covers |
|---|---|---|
| `test_validate.py` | 11 | QC: negatives=BAD, extremes=WARNING (not dropped), missing ts/coords, out-of-India, staleness |
| `test_normalize.py` | 6 | ts→UTC-Z (incl. +05:30), unit conversions, key aliasing, none-handling |
| `test_spatial.py` | 9 | bbox, point-in-polygon (incl. holes/multipolygon), centroid, haversine, nearest, join |
| `test_models.py` | 9 | flood monotonicity, missing feature omitted (not zero-faked), sorted contributions, landslide trigger-gating |
| `test_risk_engine.py` | 8 | bands, rule floors (≥2 extremes ⇒ not LOW; 3 ⇒ CRITICAL), confidence independent of risk, disclaimers |
| `test_pipeline.py` | 6 | end-to-end seed→replay→features→risk, replay idempotency, time-leakage prevention, persist/readback |
| `test_api.py` | 13 | live server on ephemeral port: health, status, villages, risk levels, GeoJSON map, history, alerts, 404, POST run, POST iot 201/400 |

**Full vertical-slice run (re-verified for this report):** 9 timesteps × 4
villages = **36 predictions**, **36 active alerts**. Devgaon rose
MODERATE (flood 0.26, window 180–360 min) → **CRITICAL** (flood 0.99, window
15–45 min) as the event peaked; all 4 villages CRITICAL at peak. Confidence held
at 0.85 independent of risk. Re-ingesting a mid-event timestep left rainfall
rows unchanged (27 → 27), confirming **idempotent** ingestion.

---

## 7. Run commands

```bash
# --- Track A: portable core (runs today, no install) ---
cd backend
python app/portable/run.py                      # seed + replay + serve :8000
#   then open frontend/portable/index.html in a browser
python tests/run_all.py                         # 62 tests

# --- Track B: production stack (local, needs Docker) ---
cp .env.example .env                            # fill secrets as sources are verified
docker compose -f docker/docker-compose.yml up --build
#   backend  -> http://localhost:8000   (migrate -> seed_prod -> uvicorn)
#   frontend -> http://localhost:5173

# --- Track B backend without Docker (needs Python deps + a PostGIS) ---
cd backend && pip install -r requirements.txt   # minimal runtime deps (fast)
alembic -c alembic.ini upgrade head
python -m app.services.seed_prod
uvicorn app.main:app --host 0.0.0.0 --port 8000
# Phase 2 heavy stack (ML + raster/vector IO), install only when needed:
# pip install -r requirements-ml.txt
```

### Verify a running Track B instance (smoke test)

```bash
curl -s localhost:8000/health                    # {"status":"ok",...,"mode":"replay"}
curl -s localhost:8000/system/status             # villages=4, model_disclaimer present
curl -s localhost:8000/risk | jq '.risks|length'  # 4
curl -s localhost:8000/risk/map | jq '.features|length'   # 4 GeoJSON features
curl -s "localhost:8000/alerts" | jq '.alerts|length'     # >0 during replay peak
# open http://localhost:5173 → risk-coloured villages + detail panel + banners
```

---

## 8. Known limitations (stated honestly)

1. **Models are demo scorers, not validated.** Transparent logistic scoring with
   explicit weights; landslide = static predisposition gated by a rainfall/soil
   trigger. Trained on **synthetic/replay** data. Every payload and both
   dashboards say so. **Not** for operational use; official NDRF/SDRF/district
   instructions take precedence.
2. **All data is synthetic and labelled** (`is_synthetic=1`, `mode='replay'`,
   `realtime_class='replay'`). **No real external source is wired.**
   `http_source_collector.py` deliberately *raises* rather than inventing data
   until a verified endpoint + credentials are supplied — no invented APIs,
   schemas, or keys anywhere.
3. **Track B has not been executed end-to-end** in this environment. The build
   sandbox has **no Docker, no PostgreSQL, and no network egress** (pip/apt/npm
   downloads return 403) — all four verified — so `docker compose up` genuinely
   cannot run here. Instead a **static integrity audit** was performed and fixed
   several bugs that would have broken the first real boot (see the changelog in
   section 8a). What remains unverifiable until you run it locally: the actual
   PostGIS DDL execution, live psycopg2 connectivity, the real HTTP responses,
   the React/MapLibre render, and Docker image builds. A first local
   `docker compose up` is still the real proof and may surface further fixes.
4. **Demo geography is a 4-village synthetic cluster** in Uttarakhand — enough to
   demonstrate drill-down and spatial joins, not a national dataset.
5. **Prototype thresholds** (risk bands, extreme-precursor floors, lead-time
   windows) are engineering choices for the demo, **not** official criteria.

---

## 8a. Static-audit changelog (fixes made so the first real boot has the best chance)

Because `docker compose up` cannot run in this sandbox (no Docker/PostgreSQL/egress),
a line-by-line cross-check of Track B against Track A was done instead. Bugs found
and fixed — each would have broken the first local run:

1. **Constraint-name mismatch (would break seed + every replay upsert).** The
   migration generated `uq_rainfall_observations_natural` / `uq_soil_..._natural`,
   but `repositories_prod.py` does `ON CONFLICT ON CONSTRAINT uq_rain_natural` /
   `uq_soil_natural`. Fixed the migration to emit the exact names the DAL expects.
2. **GeoAlchemy2 auto spatial-index collision.** Default `spatial_index=True`
   would have GeoAlchemy2's DDL listener create GiST indexes that the migration
   *also* creates — a duplicate-index failure. Set `spatial_index=False` on all
   Geometry columns (ORM + migration) and kept the explicit `CREATE INDEX ... gist`.
3. **Missing `data/` in the image (FileNotFoundError on boot).** The Dockerfile
   copied only `backend/`, but `seed_prod` replays `data/replay/...json`. Added
   `COPY data/ /app/data/` and an absolute `REPLAY_DATASET` env in compose.
4. **Brittle/slow Docker build.** `requirements.txt` pulled the heavy geo stack
   (rasterio/geopandas → GDAL source build) that nothing in `app/` imports yet.
   Split into a minimal wheels-only `requirements.txt` and a deferred
   `requirements-ml.txt`; slimmed the Dockerfile.
5. **Silent `sys.modules` swap no-op.** If any DAL consumer is imported before the
   PostGIS swap, it keeps the SQLite binding and writes to the wrong backend
   (reproduced empirically). Added a loud guard in both `main.py` and `seed_prod.py`
   that raises if a consumer imported first, plus `.env.example` var-name alignment
   (`POSTGRES_*` to match compose).

Track A stayed **62/62 green** after every one of these edits.

---

## 9. Next phase

1. **Run Track B locally** (`docker compose up`), fix anything the first real
   run surfaces, and confirm the production dashboard renders the same risk map
   as the proven Track A run.
2. **Wire the first verified real source** via `http_source_collector.py` (e.g.
   IMD/MOSDAC rainfall or CWC river level) once an endpoint + credentials exist —
   validation/QC and normalization already handle it.
3. **Replace demo scorers** with models trained on real historical events, and
   **validate** them (hindcast against known flash-flood events; report skill
   scores). In disaster ML, false negatives are more serious than false
   positives — tune and report accordingly.
4. **Backfill spatial rigor**: real admin boundaries, DEM-derived terrain, and
   GSI susceptibility layers in place of the synthetic seed.
5. **Harden the API** (authn on write endpoints such as `/iot/observations`,
   rate limits, alert de-duplication/lifecycle) before any non-demo exposure.
