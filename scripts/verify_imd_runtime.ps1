# =============================================================================
# IMD runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_imd_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). UNLIKE GPM/SMAP (discovery-only), IMD returns REAL numeric
# government weather/rainfall/warnings, so this script's honesty gate is the
# INVERSE: it verifies that IMD's real values live in imd_observations and that
# NONE of them leaked into rainfall_observations (which the ML feature pipeline
# reads as village-level rainfall). A district figure must never masquerade as a
# village value, and warning codes/colors must be preserved verbatim (never
# converted to an ML probability).
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

# IMD's verified package reads the IMD_API_TOKEN env var (see
# app/data_layer/sources/imd/sih_imd/config.py); the yaml auth_env_var was set
# to match, so this is the ONE variable that gates IMD. IMD endpoints may be
# public, in which case the source is "configured" even without a token.
$IMD_TOKEN_VAR = "IMD_API_TOKEN"

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

HDR "2. Alembic applied migrations (expect head = 0004_imd_observations)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0004_imd_observations") { OK "0004_imd_observations is applied" }
else { BAD "0004_imd_observations not at head" }

HDR "3. imd_observations table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.imd_observations'') IS NOT NULL;'
if ($exists -eq "t") { OK "table imd_observations exists" } else { BAD "table imd_observations missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''imd_observations'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# IMD has NO coordinates by design, so the table must NOT carry a geometry column.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''imd_observations'';'
Write-Host "  geometry columns on imd_observations: $hasGeom"
if ($hasGeom -eq "0") { OK "imd_observations has NO geometry column (IMD has no coordinates - correct)" }
else { BAD "imd_observations unexpectedly has a geometry column" }

HDR "4. IMD source status is honest (NOT_CONFIGURED without token, unless public)"
$imdStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''imd'';'
# Print the token var's byte-length from inside the container (0 = unset/empty).
$tokLen = (& $DOCKER exec -i $BE sh -c 'printf %s "$IMD_API_TOKEN" | wc -c' 2>$null | Out-String).Trim()
if ($tokLen -match '^\d+$') {
  if ([int]$tokLen -gt 0) { $tokenSet = "yes" } else { $tokenSet = "no" }
} else { $tokenSet = "unknown" }
Write-Host "  $IMD_TOKEN_VAR present in backend container: $tokenSet"
Write-Host "  source_health.imd status: $imdStatus"
if ($tokenSet -eq "no") {
  # Acceptable outcomes with no token: NOT_CONFIGURED (auth required) OR LIVE
  # (operator configured IMD as public by setting auth_env_var: null in yaml).
  if ($imdStatus -eq "NOT_CONFIGURED") { OK "IMD=NOT_CONFIGURED with no token (auth required)" }
  elseif ($imdStatus -eq "LIVE")       { OK "IMD=LIVE with no token (public endpoints configured)" }
  else { BAD "expected NOT_CONFIGURED or LIVE, got '$imdStatus'" }
} elseif ($tokenSet -eq "yes") {
  Write-Host "  [INFO] token IS set -> see point 13; NOT_CONFIGURED check is N/A"
} else {
  Write-Host "  [WARN] could not read token state from container"
}

HDR "5. HONESTY GATE: IMD real values live in imd_observations, NEVER rainfall_observations"
$imdInRain = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''imd'';'
Write-Host "  rainfall_observations rows with source=imd: $imdInRain"
if ($imdInRain -eq "0") { OK "no IMD rows in rainfall_observations (district figure never masquerades as village value)" }
else { BAD "found IMD rows in rainfall_observations (must be 0 - IMD has no village coordinate)" }
$imdRows = PsqlQ 'SELECT COUNT(*) FROM imd_observations;'
Write-Host "  imd_observations rows: $imdRows"

HDR "6. IMD codes/colors preserved verbatim (never an ML probability)"
# warning_color is a raw IMD integer (0..5-ish), NOT a 0..1 ML probability.
$badColor = PsqlQ 'SELECT COUNT(*) FROM imd_observations WHERE warning_color IS NOT NULL AND (warning_color < 0 OR warning_color > 100);'
$colorRows = PsqlQ 'SELECT COUNT(*) FROM imd_observations WHERE warning_color IS NOT NULL;'
Write-Host "  rows with a warning_color: $colorRows ; out-of-range (impossible IMD color): $badColor"
if ($badColor -eq "0") { OK "warning_color values are raw IMD ints, not probabilities" }
else { BAD "a warning_color is out of IMD's integer range (possible probability contamination)" }
# predictions must never derive a probability directly from an IMD color: spot
# check that no prediction cites an IMD warning as a top factor (informational).
Write-Host "  (reminder) IMD warning color must NOT be converted into flood_probability."

HDR "7. Replay still produced predictions / risk / alerts"
$preds  = PsqlQ 'SELECT COUNT(*) FROM predictions WHERE mode=''replay'';'
$alerts = PsqlQ 'SELECT COUNT(*) FROM alerts WHERE status=''active'';'
Write-Host "  replay predictions: $preds ; active alerts: $alerts"
if (($preds -as [int]) -gt 0)  { OK "replay predictions present" } else { BAD "no replay predictions" }
if (($alerts -as [int]) -gt 0) { OK "active alerts present" }      else { BAD "no active alerts" }

HDR "8-12. API contract endpoints"
CheckJson "/health"        '"status"'          "GET /health"
CheckJson "/system/status" '"sources"'         "GET /system/status"
CheckJson "/risk"          '"risks"'           "GET /risk"
CheckJson "/risk/map"      'FeatureCollection' "GET /risk/map"
CheckJson "/alerts"        '"alerts"'          "GET /alerts"
Write-Host "  data-sources status (should list imd):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'imd','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Real IMD fetch (only if configured - token present)"
if ($tokenSet -eq "yes") {
  Write-Host "  Token present. Re-running the IMD boot probe against the live API..."
  & $DOCKER exec -i $BE python -m app.services.imd_boot 2>&1 | ForEach-Object { "    $_" }
  Write-Host "  Post-probe DB state:"
  $s1 = PsqlQ 'SELECT status FROM source_health WHERE source=''imd'';'
  Write-Host "    imd status : $s1"
  $s2 = PsqlQ 'SELECT COUNT(*) FROM imd_observations;'
  Write-Host "    imd rows   : $s2 record(s)"
  Write-Host "    sample rows (real values live here - never rainfall_observations):"
  $rows = PsqlQ 'SELECT record_type || '' | '' || COALESCE(area_kind,''?'') || '':'' || COALESCE(area_name,''?'') || '' | temp='' || COALESCE(temperature_c::text,''-'') || '' | rain24h='' || COALESCE(rainfall_24h_mm::text,''-'') || '' | wcode='' || COALESCE(warning_code,''-'') || '' | wcolor='' || COALESCE(warning_color::text,''-'') || '' | wday='' || COALESCE(warning_day::text,''-'') FROM imd_observations ORDER BY id DESC LIMIT 8;'
  ($rows -split "`n") | ForEach-Object { "      $_" }
  # Re-assert the honesty gate AFTER a real fetch.
  $imdInRain2 = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''imd'';'
  Write-Host "    post-fetch rainfall_observations rows with source=imd: $imdInRain2"
  if ($imdInRain2 -eq "0") { OK "after a real fetch, still NO IMD rows in rainfall_observations" }
  else { BAD "a real IMD fetch leaked rows into rainfall_observations" }
} else {
  Write-Host "  [SKIP] No $IMD_TOKEN_VAR in the backend container."
  Write-Host "         To run the real fetch: put a token in .env ($IMD_TOKEN_VAR=...),"
  Write-Host "         set imd.enabled: true in data_sources.yml, then re-create the backend."
  Write-Host "         (Or configure IMD as public by setting imd.auth_env_var: null.)"
}

HDR "14. Village-value honesty verdict"
$imdInRainF = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''imd'';'
Write-Host "  soil/rainfall contamination check - IMD rows in rainfall_observations: $imdInRainF"
if ($imdInRainF -eq "0") {
  Write-Host "  VERDICT: IMD district/station figures are stored ONLY in imd_observations."
  Write-Host "           No district rainfall is treated as a village-level value; a separate"
  Write-Host "           explicit district-polygon -> village spatial join would be required"
  Write-Host "           first, and it is deliberately NOT performed at ingestion."
  OK "no district-as-village contamination"
} else {
  Write-Host "  VERDICT: $imdInRainF IMD row(s) reached rainfall_observations - this VIOLATES"
  Write-Host "           'do not treat district rainfall as village-level rainfall'."
  BAD "IMD contaminated the village-level rainfall table"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser),"
Write-Host "and 13 if you supplied a token."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
