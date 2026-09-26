# =============================================================================
# MOSDAC runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_mosdac_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). Like GPM/SMAP, MOSDAC is DISCOVERY-ONLY: the verified mdapi
# workflow returns granule metadata + a download URL, NOT a numeric rainfall
# value. So this script's honesty gate is that MOSDAC discovery records live in
# mosdac_discovery with numeric_value NULL, and that NONE of them leaked into
# rainfall_observations (which the ML feature pipeline reads as village-level
# rainfall). A granule filename must never masquerade as a measurement.
#
# CONFIGURATION GATE (different from GPM/SMAP token gate): the verified MOSDAC
# package hard-codes NO public endpoint (verified note: "Do not invent a public
# REST endpoint"), so MOSDAC is "configured" only when the operator supplies
# MOSDAC_API_BASE_URL. Granule SEARCH is anonymous; USERNAME/PASSWORD are for
# the (unimplemented) download stage only.
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

# MOSDAC's configuration gate is the service base URL, not a key. The vendored
# package (sih_mosdac/config.py) reads MOSDAC_API_BASE_URL; the yaml auth_env_var
# was set to match, so this is the ONE variable that decides configured vs not.
$MOSDAC_URL_VAR = "MOSDAC_API_BASE_URL"

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

function PsqlQ($sql) {
  $out = & $DOCKER exec -i $DB psql -U $PGU -d $PGDB -tAc $sql 2>$null
  if ($null -eq $out) { return "" }
  return ($out | Out-String).Trim()
}

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

HDR "2. Alembic applied migrations (expect head = 0005_mosdac_discovery)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0005_mosdac_discovery") { OK "0005_mosdac_discovery is applied" }
else { BAD "0005_mosdac_discovery not at head" }

HDR "3. mosdac_discovery table exists in PostGIS (with a POINT geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.mosdac_discovery'') IS NOT NULL;'
if ($exists -eq "t") { OK "table mosdac_discovery exists" } else { BAD "table mosdac_discovery missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''mosdac_discovery'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# MOSDAC granules can carry a footprint centroid, so (unlike IMD) a geometry
# column is expected here - mirrors gpm_discovery / smap_discovery.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''mosdac_discovery'';'
Write-Host "  geometry columns on mosdac_discovery: $hasGeom"
if ($hasGeom -eq "1") { OK "mosdac_discovery has a POINT geometry column" }
else { BAD "expected exactly one geometry column on mosdac_discovery" }

HDR "4. MOSDAC source status is honest (NOT_CONFIGURED without an endpoint)"
$mStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''mosdac'';'
# Print the base-URL var's byte-length from inside the container (0 = unset).
$urlLen = (& $DOCKER exec -i $BE sh -c 'printf %s "$MOSDAC_API_BASE_URL" | wc -c' 2>$null | Out-String).Trim()
if ($urlLen -match '^\d+$') {
  if ([int]$urlLen -gt 0) { $urlSet = "yes" } else { $urlSet = "no" }
} else { $urlSet = "unknown" }
Write-Host "  $MOSDAC_URL_VAR present in backend container: $urlSet"
Write-Host "  source_health.mosdac status: $mStatus"
if ($urlSet -eq "no") {
  if ($mStatus -eq "NOT_CONFIGURED") { OK "MOSDAC=NOT_CONFIGURED with no endpoint (honest - no invented URL)" }
  else { BAD "expected NOT_CONFIGURED with no endpoint, got '$mStatus'" }
} elseif ($urlSet -eq "yes") {
  Write-Host "  [INFO] endpoint IS set -> see point 13; NOT_CONFIGURED check is N/A"
} else {
  Write-Host "  [WARN] could not read endpoint state from container"
}

HDR "5. HONESTY GATE: discovery records carry NO rainfall value, and NONE leak into rainfall_observations"
$mosdacInRain = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''mosdac'';'
Write-Host "  rainfall_observations rows with source=mosdac: $mosdacInRain"
if ($mosdacInRain -eq "0") { OK "no MOSDAC rows in rainfall_observations (a granule filename never masquerades as rainfall)" }
else { BAD "found MOSDAC rows in rainfall_observations (must be 0 at discovery stage)" }
$discRows = PsqlQ 'SELECT COUNT(*) FROM mosdac_discovery;'
Write-Host "  mosdac_discovery rows: $discRows"
# Every discovery record MUST have numeric_value NULL and stage DISCOVERY_ONLY.
$badVal = PsqlQ 'SELECT COUNT(*) FROM mosdac_discovery WHERE numeric_value IS NOT NULL;'
Write-Host "  mosdac_discovery rows with a non-NULL numeric_value: $badVal"
if ($badVal -eq "0") { OK "all discovery records have numeric_value NULL (discovery-only)" }
else { BAD "a discovery record has a numeric_value (must be NULL until a gated parse stage)" }
$badStage = PsqlQ 'SELECT COUNT(*) FROM mosdac_discovery WHERE stage <> ''DISCOVERY_ONLY'';'
if ($badStage -eq "0") { OK "all discovery records are stage=DISCOVERY_ONLY" }
else { BAD "a discovery record has a non-DISCOVERY_ONLY stage without a parse stage" }

HDR "6. Satellite/resolution come from the verified registry (never invented)"
# For rows that name a known dataset_id, satellite should be populated from the
# vendored MOSDAC_DATASETS registry, not left arbitrary. Informational count.
$sat = PsqlQ 'SELECT COUNT(*) FROM mosdac_discovery WHERE satellite IS NOT NULL;'
Write-Host "  discovery rows with a satellite label (from verified registry): $sat"
Write-Host "  (reminder) MOSDAC product/resolution strings are copied from the verified registry, never guessed."

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
Write-Host "  data-sources status (should list mosdac):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'mosdac','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Real MOSDAC discovery (only if configured - endpoint present)"
if ($urlSet -eq "yes") {
  Write-Host "  Endpoint present. Re-running the MOSDAC boot probe against the live mdapi..."
  & $DOCKER exec -i $BE python -m app.services.mosdac_boot 2>&1 | ForEach-Object { "    $_" }
  Write-Host "  Post-probe DB state:"
  $s1 = PsqlQ 'SELECT status FROM source_health WHERE source=''mosdac'';'
  Write-Host "    mosdac status : $s1"
  $s2 = PsqlQ 'SELECT COUNT(*) FROM mosdac_discovery;'
  Write-Host "    mosdac discovery rows : $s2 record(s)"
  Write-Host "    sample rows (metadata only - numeric_value MUST be NULL):"
  $rows = PsqlQ 'SELECT COALESCE(dataset_id,''?'') || '' | '' || COALESCE(satellite,''?'') || '' | gid='' || COALESCE(granule_id,''-'') || '' | val='' || COALESCE(numeric_value::text,''NULL'') || '' | stage='' || stage FROM mosdac_discovery ORDER BY id DESC LIMIT 8;'
  ($rows -split "`n") | ForEach-Object { "      $_" }
  # Re-assert the honesty gate AFTER a real discovery.
  $mosdacInRain2 = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''mosdac'';'
  Write-Host "    post-discovery rainfall_observations rows with source=mosdac: $mosdacInRain2"
  if ($mosdacInRain2 -eq "0") { OK "after a real discovery, still NO MOSDAC rows in rainfall_observations" }
  else { BAD "a real MOSDAC discovery leaked rows into rainfall_observations" }
} else {
  Write-Host "  [SKIP] No $MOSDAC_URL_VAR in the backend container."
  Write-Host "         To run a real discovery: put the mdapi service URL in .env"
  Write-Host "         ($MOSDAC_URL_VAR=...), set mosdac.enabled: true in"
  Write-Host "         data_sources.yml, then re-create the backend. (Downloads also"
  Write-Host "         need MOSDAC_USERNAME/MOSDAC_PASSWORD, but search is anonymous.)"
}

HDR "14. Village-value honesty verdict"
$mosdacInRainF = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''mosdac'';'
Write-Host "  rainfall contamination check - MOSDAC rows in rainfall_observations: $mosdacInRainF"
if ($mosdacInRainF -eq "0") {
  Write-Host "  VERDICT: MOSDAC granule metadata is stored ONLY in mosdac_discovery."
  Write-Host "           No granule filename/URL is treated as a numeric rainfall value; a"
  Write-Host "           separate verified raster/HDF parser would be required first, and it"
  Write-Host "           is deliberately NOT performed at ingestion."
  OK "no discovery-as-measurement contamination"
} else {
  Write-Host "  VERDICT: $mosdacInRainF MOSDAC row(s) reached rainfall_observations - this VIOLATES"
  Write-Host "           the discovery-only contract (numeric values require a gated parse stage)."
  BAD "MOSDAC contaminated the rainfall table"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser),"
Write-Host "and 13 if you supplied an endpoint."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
