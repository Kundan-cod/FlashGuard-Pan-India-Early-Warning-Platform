# =============================================================================
# GPM runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_gpm_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). It does NOT claim numeric GPM rainfall exists - it reports
# exactly what the DB and API return, and explicitly checks that discovery-only
# writes zero rows to rainfall_observations.
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

HDR "2. Alembic applied migrations (expect head = 0002_gpm_discovery)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0002_gpm_discovery") { OK "0002_gpm_discovery is applied" }
else { BAD "0002_gpm_discovery not at head" }

HDR "3. gpm_discovery table exists in PostGIS"
$exists = PsqlQ 'SELECT to_regclass(''public.gpm_discovery'') IS NOT NULL;'
if ($exists -eq "t") { OK "table gpm_discovery exists" } else { BAD "table gpm_discovery missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''gpm_discovery'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
Write-Host "  geom is PostGIS geometry:"
$geom = PsqlQ 'SELECT f_geometry_column || '' '' || type || '' srid='' || srid FROM geometry_columns WHERE f_table_name=''gpm_discovery'';'
($geom -split "`n") | ForEach-Object { "    $_" }

HDR "4. GPM source status is NOT_CONFIGURED when no Earthdata token"
$gpmStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''gpm'';'
$tokenRaw = (& $DOCKER exec -i $BE sh -c 'if [ -n "$NASA_EARTHDATA_TOKEN" ]; then echo __TOKEN_YES__; else echo __TOKEN_NO__; fi' 2>$null | Out-String).Trim()
if ($tokenRaw -match "__TOKEN_YES__")     { $tokenSet = "yes" }
elseif ($tokenRaw -match "__TOKEN_NO__")  { $tokenSet = "no" }
else                                      { $tokenSet = "unknown" }
Write-Host "  token present in backend container: $tokenSet"
Write-Host "  source_health.gpm status: $gpmStatus"
if ($tokenSet -eq "no") {
  if ($gpmStatus -eq "NOT_CONFIGURED") { OK "GPM=NOT_CONFIGURED with no token" }
  else { BAD "expected NOT_CONFIGURED, got '$gpmStatus'" }
} elseif ($tokenSet -eq "yes") {
  Write-Host "  [INFO] token IS set -> see point 13; NOT_CONFIGURED check is N/A"
} else {
  Write-Host "  [WARN] could not read token state from container"
}

HDR "5. Discovery-only run inserted NOTHING into rainfall_observations from gpm"
$gpmRain = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''gpm'';'
Write-Host "  rainfall_observations rows with source=gpm: $gpmRain"
if ($gpmRain -eq "0") { OK "no gpm rows in rainfall_observations (discovery-only honoured)" }
else { BAD "found gpm rows in rainfall_observations (should be 0 unless raster stage ran)" }
$disc = PsqlQ 'SELECT COUNT(*) FROM gpm_discovery;'
$nullval = PsqlQ 'SELECT COUNT(*) FROM gpm_discovery WHERE numeric_value IS NOT NULL;'
Write-Host "  gpm_discovery rows: $disc ; rows with non-NULL numeric_value: $nullval"

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
Write-Host "  data-sources status (should list gpm):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'gpm','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Real GPM discovery request (only if token present)"
if ($tokenSet -eq "yes") {
  Write-Host "  Token present. Re-running the GPM boot probe against the live API..."
  & $DOCKER exec -i $BE python -m app.services.gpm_boot 2>&1 | ForEach-Object { "    $_" }
  Write-Host "  Post-probe DB state:"
  $s1 = PsqlQ 'SELECT status FROM source_health WHERE source=''gpm'';'
  Write-Host "    gpm status : $s1"
  $s2 = PsqlQ 'SELECT COUNT(*) FROM gpm_discovery;'
  Write-Host "    discovery  : $s2 record(s)"
  Write-Host "    sample rows:"
  $rows = PsqlQ 'SELECT product || '' | '' || COALESCE(observed_date,''?'') || '' | url='' || COALESCE(left(download_url,60),''NULL'') || '' | numeric_value='' || COALESCE(numeric_value::text,''NULL'') FROM gpm_discovery ORDER BY id DESC LIMIT 5;'
  ($rows -split "`n") | ForEach-Object { "      $_" }
} else {
  Write-Host "  [SKIP] No NASA_EARTHDATA_TOKEN in the backend container."
  Write-Host "         To run the real discovery request: put a token in .env"
  Write-Host "         (NASA_EARTHDATA_TOKEN=...), then re-create the backend container."
}

HDR "14. Numeric-rainfall honesty gate"
$raster = PsqlQ 'SELECT COUNT(*) FROM gpm_discovery WHERE stage=''RASTER_SAMPLED'';'
$gpmRain2 = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''gpm'';'
Write-Host "  gpm_discovery rows marked RASTER_SAMPLED: $raster"
Write-Host "  rainfall_observations rows with source=gpm: $gpmRain2"
if ($gpmRain2 -eq "0") {
  Write-Host "  VERDICT: No numeric GPM rainfall exists. GPM is DISCOVERY-ONLY here."
  OK "no unearned numeric-rainfall claim"
} else {
  Write-Host "  VERDICT: $gpmRain2 gpm rainfall row(s) exist - ONLY trust these if the"
  Write-Host "           raster was actually downloaded, parsed, sampled and stored."
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12 (map renders in browser),"
Write-Host "and 13 if you supplied a token."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
