# Track B backend image — ML / RASTER variant (SIH 2026 PS 26192)
# =============================================================================
# This is the OPTIONAL heavy image. It is IDENTICAL to backend.Dockerfile except
# it also installs requirements-ml.txt (rasterio, geopandas, scikit-learn, ...),
# which link against the system GDAL/GEOS/PROJ toolchain. Use this image ONLY
# when you want the gated GPM raster-sampling stage to actually run and produce
# REAL numeric rainfall (mm) in rainfall_observations.
#
# The DEFAULT image (backend.Dockerfile) stays small and is the known-good replay
# path. Nothing here changes that path — it is a separate build target selected
# via docker-compose.ml.yml.
#
# Honesty posture unchanged: installing rasterio only ENABLES the gated stage.
# The collector still refuses to fabricate — no token -> NOT_CONFIGURED; a browse
# PNG payload -> refused (is_scientific_raster); a NoData/out-of-bounds sample ->
# None, never 0. A real mm value exists ONLY if a scientific raster was actually
# downloaded, opened and sampled.
# =============================================================================
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH="/app:/app/tests:/app/app/data_layer/sources/bhuvan_nrsc:/app/app/data_layer/sources/cwc_nwic:/app/app/data_layer/sources/gsi_bhusanket:/app/app/data_layer/sources/historical:/app/app/data_layer/sources/imd:/app/app/data_layer/sources/lgd:/app/app/data_layer/sources/mosdac:/app/app/data_layer/sources/ndem:/app/app/data_layer/sources/smap"

# curl -> HEALTHCHECK; the -dev libs are the GDAL/GEOS/PROJ toolchain rasterio +
# geopandas build/link against. build-essential compiles any sdist wheels.
RUN apt-get update && apt-get install -y --no-install-recommends \
      curl \
      build-essential \
      libgdal-dev \
      libgeos-dev \
      libproj-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install the base runtime first (same as the default image), then the heavy ML
# stack on top. Two layers so a change to one does not always rebuild the other.
COPY backend/requirements.txt ./requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY backend/requirements-ml.txt ./requirements-ml.txt
RUN pip install -r requirements-ml.txt

COPY backend/ /app/

# Replay dataset lives at the repo root (build context is `..`); copy explicitly
# so seed_prod's replay step does not FileNotFoundError on boot.
COPY data/ /app/data/
COPY ml/ /app/ml/

ENV ML_ARTIFACT_DIR=/app/ml/artifacts

EXPOSE 8000

HEALTHCHECK --interval=15s --timeout=5s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
