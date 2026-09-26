#!/usr/bin/env bash
# =============================================================================
# GPM runtime verification — Track B (Docker + PostGIS)   SIH 2026 PS 26192
#
# Runs the 14-point verification the user asked for against the ACTUAL stack.
# Run from the repo root on your Windows+Docker machine (Git Bash / WSL):
#
#     bash scripts/verify_gpm_runtime.sh
#
# It only READS the running stack (plus one curl to trigger nothing destructive).
# It does NOT claim numeric GPM rainfall exists — it reports exactly what the DB
# and API return, and explicitly checks that discovery-only writes zero rows to
# rainfall_observations.
#
# Exit code 0 = all automated checks passed; non-zero = something needs a look.
# =============================================================================
set -uo pipefail

# Find a working docker binary. Under WSL with Docker Desktop's WSL integration
# OFF, the bare `docker` alias is missing but `docker.exe` on the Windows PATH is
# still callable. Fall back to it so DB-level checks work from Git Bash / WSL.
if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
  DOCKER=docker
elif command -v docker.exe >/dev/null 2>&1; then
  DOCKER=docker.exe
else
  DOCKER=docker  # will error visibly; message handled in step 1
fi
echo "[info] using docker binary: $DOCKER"

COMPOSE="$DOCKER compose -f docker/docker-compose.yml"
DB_SVC=db
BE_SVC=backend
PGUSER="${POSTGRES_USER:-flashguard}"
PGDB="${POSTGRES_DB:-flashguard}"
API="http://localhost:8000"

pass=0; fail=0
ok()   { echo "  [PASS] $1"; pass=$((pass+1)); }
bad()  { echo "  [FAIL] $1"; fail=$((fail+1)); }
hdr()  { echo; echo "=== $1 ==="; }

psql_q() { $COMPOSE exec -T $DB_SVC psql -U "$PGUSER" -d "$PGDB" -tAc "$1" 2>/dev/null; }

# ----------------------------------------------------------------------------
hdr "1. Docker builds + stack is up"
echo "  docker compose ps -a:"
$COMPOSE ps -a 2>&1 | sed 's/^/    /'
# Is the backend container actually RUNNING (not exited)?
BE_STATE=$($COMPOSE ps -a --format '{{.Service}} {{.State}}' 2>/dev/null | awk -v s="$BE_SVC" '$1==s {print $2}')
echo "  backend state: ${BE_STATE:-<not found>}"
if [ "$BE_STATE" != "running" ]; then
  bad "backend is not running (state='${BE_STATE:-none}') — it likely crashed on boot"
  echo "  ---- last 60 lines of backend logs (crash reason) ----"
  $COMPOSE logs --tail=60 $BE_SVC 2>&1 | sed 's/^/    /'
  echo "  ------------------------------------------------------"
  echo "  Fix the boot error above, then: $COMPOSE up -d --force-recreate backend"
  echo "  Continuing with DB-only checks where possible..."
else
  ok "backend container is running"
fi
# Independent liveness probe regardless of ps parsing quirks.
HB=$(curl -fsS -o /dev/null -w "%{http_code}" "$API/health" 2>/dev/null)
echo "  GET /health -> HTTP ${HB:-000}"
[ "$HB" = "200" ] && ok "backend answering on :8000" || bad "backend NOT answering on :8000"

hdr "2. Alembic applied migrations (expect head = 0002_gpm_discovery)"
HEAD=$($COMPOSE exec -T $BE_SVC alembic -c alembic.ini current 2>/dev/null | tr -d '\r')
echo "  alembic current: $HEAD"
echo "$HEAD" | grep -q "0002_gpm_discovery" && ok "0002_gpm_discovery is applied" \
  || bad "0002_gpm_discovery not at head"

hdr "3. gpm_discovery table exists in PostGIS"
EXISTS=$(psql_q "SELECT to_regclass('public.gpm_discovery') IS NOT NULL;")
[ "$EXISTS" = "t" ] && ok "table gpm_discovery exists" || bad "table gpm_discovery missing"
echo "  columns:"; psql_q "SELECT column_name||' '||data_type FROM information_schema.columns WHERE table_name='gpm_discovery' ORDER BY ordinal_position;" | sed 's/^/    /'
echo "  geom is PostGIS geometry:"; psql_q "SELECT f_geometry_column||' '||type||' srid='||srid FROM geometry_columns WHERE f_table_name='gpm_discovery';" | sed 's/^/    /'

hdr "4. GPM source status is NOT_CONFIGURED when no Earthdata token"
GPM_STATUS=$(psql_q "SELECT status FROM source_health WHERE source='gpm';")
TOKEN_RAW=$($COMPOSE exec -T $BE_SVC sh -c 'if [ -n "$NASA_EARTHDATA_TOKEN" ]; then echo __TOKEN_YES__; else echo __TOKEN_NO__; fi' 2>/dev/null | tr -d '\r')
if echo "$TOKEN_RAW" | grep -q "__TOKEN_YES__"; then TOKEN_SET=yes
elif echo "$TOKEN_RAW" | grep -q "__TOKEN_NO__"; then TOKEN_SET=no
else TOKEN_SET=unknown; fi
echo "  token present in backend container: $TOKEN_SET"
echo "  source_health.gpm status: ${GPM_STATUS:-<absent>}"
if [ "$TOKEN_SET" = "no" ]; then
  [ "$GPM_STATUS" = "NOT_CONFIGURED" ] && ok "GPM=NOT_CONFIGURED with no token" \
    || bad "expected NOT_CONFIGURED, got '${GPM_STATUS:-<absent>}'"
elif [ "$TOKEN_SET" = "yes" ]; then
  echo "  [INFO] token IS set -> see point 13; NOT_CONFIGURED check is N/A"
else
  echo "  [WARN] could not read token state from container (docker exec failed)"
fi

hdr "5. Discovery-only run inserted NOTHING into rainfall_observations from gpm"
GPM_RAIN=$(psql_q "SELECT COUNT(*) FROM rainfall_observations WHERE source='gpm';")
echo "  rainfall_observations rows with source='gpm': ${GPM_RAIN:-?}"
[ "${GPM_RAIN:-1}" = "0" ] && ok "no gpm rows in rainfall_observations (discovery-only honoured)" \
  || bad "found gpm rows in rainfall_observations — investigate (should be 0 unless raster stage ran)"
DISC=$(psql_q "SELECT COUNT(*) FROM gpm_discovery;")
NULLVAL=$(psql_q "SELECT COUNT(*) FROM gpm_discovery WHERE numeric_value IS NOT NULL;")
echo "  gpm_discovery rows: ${DISC:-0} | rows with non-NULL numeric_value: ${NULLVAL:-0}"

hdr "6. Replay still produced predictions / risk / alerts"
PREDS=$(psql_q "SELECT COUNT(*) FROM predictions WHERE mode='replay';")
ALERTS=$(psql_q "SELECT COUNT(*) FROM alerts WHERE status='active';")
echo "  replay predictions: ${PREDS:-0} | active alerts: ${ALERTS:-0}"
[ "${PREDS:-0}" -gt 0 ] 2>/dev/null && ok "replay predictions present" || bad "no replay predictions"
[ "${ALERTS:-0}" -gt 0 ] 2>/dev/null && ok "active alerts present" || bad "no active alerts"

check_json() { # $1 = path, $2 = grep needle, $3 = label
  local body; body=$(curl -fsS "$API$1" 2>/dev/null)
  if [ $? -eq 0 ] && echo "$body" | grep -q "$2"; then
    ok "$3 ($1)"; echo "    $(echo "$body" | head -c 160)..."
  else
    bad "$3 ($1) — no/short response"; echo "    ${body:0:160}"
  fi
}

hdr "7-11. API contract endpoints"
check_json "/health"             '"status"'   "GET /health"
check_json "/system/status"      '"sources"'  "GET /system/status"
check_json "/risk"               '"risks"'    "GET /risk"
check_json "/risk/map"           'FeatureCollection' "GET /risk/map"
check_json "/alerts"             '"alerts"'   "GET /alerts"
echo "  data-sources status (should list gpm):"
curl -fsS "$API/data-sources/status" 2>/dev/null | tr ',' '\n' | grep -i -A0 "gpm\|status" | head -20 | sed 's/^/    /'

hdr "12. Frontend renders"
FE=$(curl -fsS -o /dev/null -w "%{http_code}" http://localhost:5173 2>/dev/null)
echo "  http://localhost:5173 -> HTTP $FE"
[ "$FE" = "200" ] && ok "frontend served (open it and confirm the map + risk polygons)" \
  || bad "frontend not served on :5173"

hdr "13. Real GPM discovery request (only if token present)"
if [ "$TOKEN_SET" = "yes" ]; then
  echo "  Token present. Re-running the GPM boot probe against the live API..."
  $COMPOSE exec -T $BE_SVC python -m app.services.gpm_boot 2>&1 | sed 's/^/    /'
  echo "  Post-probe DB state:"
  echo "    gpm status : $(psql_q "SELECT status FROM source_health WHERE source='gpm';")"
  echo "    discovery  : $(psql_q "SELECT COUNT(*) FROM gpm_discovery;") record(s)"
  echo "    sample rows:"; psql_q "SELECT product||' | '||COALESCE(observed_date,'?')||' | url='||COALESCE(left(download_url,60),'NULL')||' | numeric_value='||COALESCE(numeric_value::text,'NULL') FROM gpm_discovery ORDER BY id DESC LIMIT 5;" | sed 's/^/      /'
else
  echo "  [SKIP] No NASA_EARTHDATA_TOKEN in the backend container."
  echo "         To run the real discovery request: put a token in .env"
  echo "         (NASA_EARTHDATA_TOKEN=...), then: $COMPOSE up -d --force-recreate backend"
fi

hdr "14. Numeric-rainfall honesty gate"
RASTER=$(psql_q "SELECT COUNT(*) FROM gpm_discovery WHERE stage='RASTER_SAMPLED';")
GPM_RAIN2=$(psql_q "SELECT COUNT(*) FROM rainfall_observations WHERE source='gpm';")
echo "  gpm_discovery rows marked RASTER_SAMPLED: ${RASTER:-0}"
echo "  rainfall_observations rows with source='gpm': ${GPM_RAIN2:-0}"
if [ "${GPM_RAIN2:-0}" = "0" ]; then
  echo "  VERDICT: No numeric GPM rainfall exists. GPM is DISCOVERY-ONLY here."
  echo "           (This is correct unless rasterio + a downloadable product +"
  echo "            village coords all lined up and the raster stage ran.)"
  ok "no unearned numeric-rainfall claim"
else
  echo "  VERDICT: ${GPM_RAIN2} gpm rainfall row(s) exist — ONLY trust these if the"
  echo "           raster was actually downloaded, parsed, sampled and stored."
  echo "           Confirm the boot log shows 'raster: N url(s) processed, M real value(s) stored'."
fi

echo; echo "============================================================"
echo "RESULT: $pass passed, $fail failed."
echo "Points requiring your eyes: 12 (map renders in browser),"
echo "and 13 if you supplied a token (read the exact discovery output above)."
echo "============================================================"
[ "$fail" -eq 0 ] && exit 0 || exit 1
