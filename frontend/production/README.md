# FlashGuard — Track B production frontend

React + TypeScript + MapLibre GL dashboard for the pan-India flash-flood &
landslide early-warning platform (SIH 2026, PS 26192). It is the production
analogue of the proven Track A portable Leaflet dashboard and consumes the
**identical API contract** (see `src/api.ts`), so it works against either
backend without change.

> **STATUS: skeleton — pending local run.** The build sandbox has no network
> egress, so `npm install` / `vite` cannot run here. The code is written against
> pinned dependencies and mirrors the working Track A dashboard behaviour.

## What it shows

- Risk-coloured village polygons on an OpenStreetMap basemap (no API key).
- Click a village → detail panel: flood %, landslide %, confidence,
  data-completeness, estimated high-risk **window** (never an exact arrival
  time), and the top contributing factors.
- Live data-source health strip and elevated-village count.
- Prominent honesty banners: **REPLAY**, **SIMULATED**, and
  **DEMO MODEL — not validated**. These are not decoration; the models are
  transparent demo scorers trained on synthetic/replay data and are for
  decision support only. Official NDRF/SDRF/district instructions take
  precedence.

## Run locally

```bash
# from this directory
npm install
npm run dev          # http://localhost:5173
```

Point it at a running backend (Track A portable on :8000, or Track B FastAPI):

```bash
# optional; defaults to http://localhost:8000
echo "VITE_API_BASE=http://localhost:8000" > .env
```

Or run the whole Track B stack (PostGIS + Redis + FastAPI + this frontend) with
Docker from the repo root:

```bash
docker compose -f docker/docker-compose.yml up --build
```

## Contract

`src/api.ts` is the single source of truth for the endpoints and types this
dashboard uses. It matches `GET /contract` on both backends:

```
GET  /health              GET  /risk               GET  /alerts
GET  /system/status       GET  /risk/{id}          POST /prediction/run
GET  /data-sources/status GET  /risk/map           POST /replay/run
GET  /locations           GET  /predictions/history POST /iot/observations
GET  /locations/{id}      GET  /rainfall  /river-level
```
