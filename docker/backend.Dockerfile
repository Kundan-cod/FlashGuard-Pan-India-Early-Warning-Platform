# Track B backend image — SIH 2026 PS 26192
# The runtime deps (requirements.txt) are all pure-Python / manylinux wheels
# (FastAPI, SQLAlchemy, GeoAlchemy2, psycopg2-binary, alembic), so NO system
# build toolchain is needed and the image stays small and quick to build.
# `curl` is kept only for the container HEALTHCHECK.
#
# Phase 2 note: when you add the heavy stack (requirements-ml.txt: rasterio,
# geopandas, ...), reintroduce the GDAL/GEOS/PROJ system libs below, e.g.:
#   RUN apt-get update && apt-get install -y --no-install-recommends \
#       build-essential libgdal-dev libgeos-dev libproj-dev && \
#       rm -rf /var/lib/apt/lists/*
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH="/app:/app/tests:/app/app/data_layer/sources/bhuvan_nrsc:/app/app/data_layer/sources/cwc_nwic:/app/app/data_layer/sources/gsi_bhusanket:/app/app/data_layer/sources/historical:/app/app/data_layer/sources/imd:/app/app/data_layer/sources/lgd:/app/app/data_layer/sources/mosdac:/app/app/data_layer/sources/ndem:/app/app/data_layer/sources/smap"

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/ /app/

# The replay dataset lives at the repo root (build context is `..`), so it must
# be copied in explicitly — the app resolves it via REPLAY_DATASET (see compose).
# Without this, seed_prod's replay step would FileNotFoundError on boot.
COPY data/ /app/data/
COPY ml/ /app/ml/

ENV ML_ARTIFACT_DIR=/app/ml/artifacts

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
