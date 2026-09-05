# FlashGuard — Pan-India Flash Flood & Landslide Early-Warning Platform

**SIH 2026 · Problem Statement 26192** — *Flash Flood Prediction System for
Hilly Regions using Multi-Source Data*
Ministry of Home Affairs · National Disaster Response Force (NDRF), DM Division
Category: Software · Theme: Disaster Management

> **Positioning:** not an "AI flood website" but a *pan-India, multi-source,
> hyper-local flash-flood **and** landslide early-warning and decision-support
> platform* with risk + confidence + lead-time, explainability, graceful
> degradation, and historical replay.

---

## What this is (and what it honestly is not)

This is a **decision-support prototype**. It estimates risk; it never claims a
flood *will* happen, never invents an exact arrival time, and never presents
prototype thresholds as official government rules. Official emergency
instructions always override it.

It is built to be **demonstrable offline**: judging does not depend on any
external government API being live at the right moment (replay mode runs the
real pipeline over historical data, clearly labelled).

External data-source specifics (endpoints, resolutions, auth) are **verified
separately** and are marked `EXTERNAL VERIFICATION REQUIRED` until confirmed —
see [`docs/data_sources.md`](docs/data_sources.md). We do not invent them.

---

## Two tracks, one architecture

| | Track A — Portable core | Track B — Production |
|---|---|---|
| Purpose | Runs anywhere with just Python; proves the full vertical slice | Local/cloud deployment target |
| Stack | stdlib `http.server`, SQLite, numpy, Leaflet (CDN) | FastAPI, PostgreSQL+PostGIS, XGBoost, React+MapLibre, Docker |
| Status | **Runnable now** | **Scaffold — run locally on Windows+Docker** |

Both share the same module boundaries and interfaces (see
[`docs/architecture.md`](docs/architecture.md)); moving A→B is an adapter swap.

---

## Quick start — Track A (portable, no install)

```bash
# Requires only Python 3.10+ and numpy (already common).
python3 backend/app/portable/run.py         # starts API on 127.0.0.1:8000
# then open the dashboard:
#   frontend/portable/index.html
```

*(Populated in Phase 1b/1c. This README is created in Phase 1a.)*

## Quick start — Track B (production, local)

```bash
cp .env.example .env        # fill values; NEVER commit .env
docker compose up --build   # postgis + redis + backend + frontend
```

*(docker-compose and services scaffolded in Phase 1e, marked "pending local run".)*

---

## Repository layout

```
frontend/           GIS dashboard (Track A: Leaflet single-file; Track B: React+MapLibre)
backend/
  app/
    api/            HTTP API (Track B FastAPI routers)
    collectors/     one adapter per data source (fetch/validate/normalize/store/status)
    ingestion/      idempotent ingestion + scheduler
    processing/     validation (QC) + normalization
    geospatial/     spatial joins, fusion, terrain derivation
    features/       feature engineering (rainfall windows, soil, river, terrain, history)
    models/         flood + landslide models (interfaces + demo models)
    risk/           risk fusion, confidence, lead-time, explainability
    alerts/         alert level engine
    iot/            MQTT/HTTP consumer + simulator
    database/       schema + repositories (SQLite + PostGIS implementations)
    services/       cross-cutting services
    config/         data_sources.yml registry
    portable/       Track A stdlib runtime (self-contained)
  tests/            unittest/pytest suites
ml/                 datasets / notebooks / training / evaluation / artifacts
gis/                raw / processed / scripts (DEM, boundaries)
data/               sample / replay (clearly-labelled demo data)
iot/                firmware (ESP32) / simulator
docker/             Dockerfiles
docs/               architecture, data sources, methodology, guides
```

---

## Documentation

- [`docs/architecture.md`](docs/architecture.md) — pipeline, collector contract, two-track design, modes, safety posture.
- [`docs/data_sources.md`](docs/data_sources.md) — master data-source table with verification status.
- Further docs (DB schema, ML/GIS methodology, deployment, IoT, demo, troubleshooting) added per phase.

## Safety & honesty rules baked in

- Decision support only — "estimated risk", never guarantees (prompt s.48/69).
- Risk ≠ confidence; HIGH RISK + LOW CONFIDENCE is valid and shown (s.21).
- No fake completion, no invented endpoints/credentials/schemas (s.40/57/62/67).
- Simulated/replay/demo data always labelled in the UI (s.64/67).
- False negatives treated as more serious than false positives in disaster ML (s.35).

## License

Prototype for SIH 2026. See [`LICENSE`](LICENSE).
