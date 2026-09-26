# =============================================================================
# SMAP runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_smap_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). It does NOT claim numeric SMAP soil-moisture exists - it reports
# exactly what the DB and API return, and explicitly checks that discovery-only
# writes zero rows to soil_moisture_observations. SMAP has NO verified HDF5/
# NetCDF parse stage, so it is discovery-only by design: surface_sm/rootzone_sm
# stay NULL and no soil-moisture value is ever fabricated.
#
# NOTE on quoting: every SQL string is passed as a PowerShell SINGLE-quoted
# literal so PowerShell never tries to parse '|', '||', '::' or '(*)' as
# operators. A literal single quote inside SQL is written as '' (doubled).
# =============================================================================

$ErrorActionPreference = "Continue"

# --- container / connection settings (fixed by docker-compose.yml) ---
$DB   = "flashguard_db"
$BE   = "flashguard_backend"
$PGU  = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "flashguard" }
$PGDB = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { "flashguard" }
$API  = "http://localhost:8000"

# SMAP's verified package reads the EARTHDATA_TOKEN env var (see
# app/data_layer/sources/smap/sih_smap/config.py); the yaml auth_env_var was set
# to match, so this is the ONE variable that gates SMAP.
$SMAP_TOKEN_VAR = "EARTHDATA_TOKEN"

$script:pass = 0
$script:fail = 0
function OK($m)  { Write-Host "  [PASS] $m" -ForegroundColor Green; $script:pass++ }
function BAD($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red;   $script:fail++ }
function HDR($m) { Write-Host ""; Write-Host "=== $m ===" -ForegroundColor Cyan }

# Pick a docker binary that works from PowerShell.
$DOCKER = "docker"
try { docker version *> $null; if ($LASTEXITCODE -ne 0) { $DOCKER = "docker.exe" } }
catch { $DOCKER = "docker.exe" }
Write-Host "[info] using docker binary: $DOCKER"

# Run a SQL query inside the db container; returns trimmed stdout (tuples-only).
function PsqlQ($sql) {
  $out = & $DOCKER exec -i $DB psql -U $PGU -d $PGDB -tAc $sql 2>$null
  if ($null -eq $out) { return "" }
  return ($out | Out-String).Trim()
}

# HTTP GET; returns @{ code=<int>; body=<string> }.
function HttpGet($path) {
  try {
    $r = Invoke-WebRequest -Uri "$API$path" -UseBasicParsing -TimeoutSec 10
    return @{ code = [int]$r.StatusCode; body = $r.Content }
  } catch {
    $c = 0
    if ($_.Exception.Response) { $c = [int]$_.Exception.Response.StatusCode }
    return @{ code = $c; body = "" }
  }
}

function CheckJson($path, $needle, $label) {
  $r = HttpGet $path
  if ($r.code -eq 200 -and $r.body -match [regex]::Escape($needle)) {
    OK "$label ($path)"
    $snip = $r.body.Substring(0, [Math]::Min(160, $r.body.Length))
    Write-Host "    $snip..."
  } else {
    BAD "$label ($path) - HTTP $($r.code) / needle not found"
    if ($r.body) { Write-Host "    $($r.body.Substring(0,[Math]::Min(160,$r.body.Length)))" }
  }
}

# ---------------------------------------------------------------------------
HDR "1. Docker builds + stack is up"
& $DOCKER compose -f docker/docker-compose.yml ps -a 2>&1 | ForEach-Object { "    $_" }
$beState = (& $DOCKER inspect -f '{{.State.Status}}' $BE 2>$null | Out-String).Trim()
Write-Host "  backend container state: $beState"
if ($beState -eq "running") { OK "backend container is running" }
else { BAD "backend not running (state='$beState')" }
$hb = (HttpGet "/health").code
Write-Host "  GET /health -> HTTP $hb"
if ($hb -eq 200) { OK "backend answering on :8000" } else { BAD "backend NOT answering on :8000" }

HDR "2. Alembic applied migrations (expect head = 0003_smap_discovery)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0003_smap_discovery") { OK "0003_smap_discovery is applied" }
else { BAD "0003_smap_discovery not at head" }

HDR "3. smap_discovery table exists in PostGIS"
$exists = PsqlQ 'SELECT to_regclass(''public.smap_discovery'') IS NOT NULL;'
if ($exists -eq "t") { OK "table smap_discovery exists" } else { BAD "table smap_discovery missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''smap_discovery'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
Write-Host "  geom is PostGIS geometry:"
$geom = PsqlQ 'SELECT f_geometry_column || '' '' || type || '' srid='' || srid FROM geometry_columns WHERE f_table_name=''smap_discovery'';'
($geom -split "`n") | ForEach-Object { "    $_" }

HDR "4. SMAP source status is NOT_CONFIGURED when no Earthdata token"
$smapStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''smap'';'
# Print the token var's byte-length from inside the container (0 = unset/empty).
# The env var name is fixed (EARTHDATA_TOKEN), passed as a single-quoted sh script
# so PowerShell does not interpolate the $ and the shell reads the real env var.
$tokLen = (& $DOCKER exec -i $BE sh -c 'printf %s "$EARTHDATA_TOKEN" | wc -c' 2>$null | Out-String).Trim()
if ($tokLen -match '^\d+$') {
  if ([int]$tokLen -gt 0) { $tokenSet = "yes" } else { $tokenSet = "no" }
} else { $tokenSet = "unknown" }
Write-Host "  $SMAP_TOKEN_VAR present in backend container: $tokenSet"
Write-Host "  source_health.smap status: $smapStatus"
if ($tokenSet -eq "no") {
  if ($smapStatus -eq "NOT_CONFIGURED") { OK "SMAP=NOT_CONFIGURED with no token" }
  else { BAD "expected NOT_CONFIGURED, got '$smapStatus'" }
} elseif ($tokenSet -eq "yes") {
  Write-Host "  [INFO] token IS set -> see point 13; NOT_CONFIGURED check is N/A"
} else {
  Write-Host "  [WARN] could not read token state from container"
}

HDR "5. Discovery-only run inserted NOTHING into soil_moisture_observations from smap"
$smapSoil = PsqlQ 'SELECT COUNT(*) FROM soil_moisture_observations WHERE source=''smap'';'
Write-Host "  soil_moisture_observations rows with source=smap: $smapSoil"
if ($smapSoil -eq "0") { OK "no smap rows in soil_moisture_observations (discovery-only honoured)" }
else { BAD "found smap rows in soil_moisture_observations (should be 0 - no verified parser exists)" }
$disc = PsqlQ 'SELECT COUNT(*) FROM smap_discovery;'
$nullval = PsqlQ 'SELECT COUNT(*) FROM smap_discovery WHERE surface_sm IS NOT NULL OR rootzone_sm IS NOT NULL;'
Write-Host "  smap_discovery rows: $disc ; rows with a non-NULL soil-moisture value: $nullval"
if ($nullval -eq "0") { OK "every smap_discovery row has NULL surface_sm/rootzone_sm" }
else { BAD "a smap_discovery row carries a soil-moisture value (must be NULL at discovery)" }

HDR "6. Replay still produced predictions / risk / alerts"
$preds  = PsqlQ 'SELECT COUNT(*) FROM predictions WHERE mode=''replay'';'
$alerts = PsqlQ 'SELECT COUNT(*) FROM alerts WHERE status=''active'';'
Write-Host "  replay predictions: $preds ; active alerts: $alerts"
if (($preds -as [int]) -gt 0)  { OK "replay predictions present" } else { BAD "no replay predictions" }
if (($alerts -as [int]) -gt 0) { OK "active alerts present" }      else { BAD "no active alerts" }

HDR "7-11. API contract endpoints"
CheckJson "/health"        '"status"'          "GET /health"
CheckJson "/system/status" '"sources"'         "GET /system/status"
CheckJson "/risk"          '"risks"'           "GET /risk"
CheckJson "/risk/map"      'FeatureCollection' "GET /risk/map"
CheckJson "/alerts"        '"alerts"'          "GET /alerts"
Write-Host "  data-sources status (should list smap):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'smap','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Real SMAP CMR discovery request (only if token present)"
if ($tokenSet -eq "yes") {
  Write-Host "  Token present. Re-running the SMAP boot probe against the live API..."
  & $DOCKER exec -i $BE python -m app.services.smap_boot 2>&1 | ForEach-Object { "    $_" }
  Write-Host "  Post-probe DB state:"
  $s1 = PsqlQ 'SELECT status FROM source_health WHERE source=''smap'';'
  Write-Host "    smap status : $s1"
  $s2 = PsqlQ 'SELECT COUNT(*) FROM smap_discovery;'
  Write-Host "    discovery   : $s2 record(s)"
  Write-Host "    sample rows:"
  $rows = PsqlQ 'SELECT product || '' | '' || COALESCE(observed_date,''?'') || '' | url='' || COALESCE(left(download_url,55),''NULL'') || '' | surface_sm='' || COALESCE(surface_sm::text,''NULL'') || '' | rootzone_sm='' || COALESCE(rootzone_sm::text,''NULL'') FROM smap_discovery ORDER BY id DESC LIMIT 5;'
  ($rows -split "`n") | ForEach-Object { "      $_" }
} else {
  Write-Host "  [SKIP] No $SMAP_TOKEN_VAR in the backend container."
  Write-Host "         To run the real discovery request: put a token in .env"
  Write-Host "         ($SMAP_TOKEN_VAR=...), then re-create the backend container."
}

HDR "14. Numeric soil-moisture honesty gate"
$parsed = PsqlQ 'SELECT COUNT(*) FROM smap_discovery WHERE stage=''RASTER_SAMPLED'';'
$smapSoil2 = PsqlQ 'SELECT COUNT(*) FROM soil_moisture_observations WHERE source=''smap'';'
Write-Host "  smap_discovery rows marked RASTER_SAMPLED: $parsed"
Write-Host "  soil_moisture_observations rows with source=smap: $smapSoil2"
if ($smapSoil2 -eq "0") {
  Write-Host "  VERDICT: No numeric SMAP soil-moisture exists. SMAP is DISCOVERY-ONLY here"
  Write-Host "           (no verified HDF5/NetCDF parser is part of the package)."
  OK "no unearned numeric soil-moisture claim"
} else {
  Write-Host "  VERDICT: $smapSoil2 smap soil-moisture row(s) exist - ONLY trust these if a"
  Write-Host "           verified product parser actually read and mapped the HDF5 values."
  BAD "smap soil-moisture rows exist without a verified parser in this package"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12 (map renders in browser),"
Write-Host "and 13 if you supplied a token."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
