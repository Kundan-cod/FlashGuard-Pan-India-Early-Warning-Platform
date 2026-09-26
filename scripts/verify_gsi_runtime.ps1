# =============================================================================
# GSI / Bhusanket runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_gsi_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). GSI/Bhusanket is CATALOG-ONLY - it is NOT discovery-only and NOT
# a numeric landslide feed. GSI's National Landslide Forecasting Centre (Bhusanket
# portal) exposes a forecast bulletin, LSM 10K susceptibility maps, an impact-
# probability map and a field-validated landslide inventory. The verified note is
# explicit: "This adapter intentionally does not hard-code an undocumented JSON
# API", and GSI forecasting is REGIONAL (Darjeeling/Kalimpong/Nilgiris
# operational, others experimental), NOT a nationwide live API. So this collector
# records verified portal layer ENDPOINTS + roles + COVERAGE notes in gsi_layers
# only, and never produces a numeric susceptibility/probability.
#
# HONESTY GATE (different from GPM/SMAP/MOSDAC discovery gate): the catalog must
# never populate landslide_data (which the ML landslide pipeline reads). Every
# gsi_layers row is stage='CATALOG_ONLY' and carries NO numeric landslide value
# (the table has no measurement column at all). A portal layer / bulletin link
# must never masquerade as a susceptibility/probability value.
#
# CONFIGURATION GATE (like Bhuvan): the verified GSI registry hard-codes the REAL
# public portal (https://bhusanket.gsi.gov.in), and cataloging needs no
# credentials, so verified=true alone is enough to build the catalog -> LIVE.
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

HDR "2. Alembic applied migrations (expect head = 0007_gsi_layers)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0007_gsi_layers") { OK "0007_gsi_layers is applied" }
else { BAD "0007_gsi_layers not at head" }

HDR "3. gsi_layers table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.gsi_layers'') IS NOT NULL;'
if ($exists -eq "t") { OK "table gsi_layers exists" } else { BAD "table gsi_layers missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''gsi_layers'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# A catalog entry describes a portal layer/endpoint, NOT a point observation, so
# (unlike gpm/smap/mosdac discovery tables) there is deliberately NO geometry.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''gsi_layers'';'
Write-Host "  geometry columns on gsi_layers: $hasGeom"
if ($hasGeom -eq "0") { OK "gsi_layers has NO geometry column (a catalog entry is an endpoint, not a point)" }
else { BAD "unexpected geometry column on gsi_layers (catalog rows are not observations)" }

HDR "4. GSI source status is honest (LIVE - verified public portal, no creds)"
$gStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''gsi'';'
Write-Host "  source_health.gsi status: $gStatus"
# Cataloging the verified registry is an offline op over verified static
# metadata; a fully reachable/verified catalog reports LIVE. If an optional portal
# probe found the Bhusanket portal unreachable it would honestly be STALE.
if ($gStatus -eq "LIVE") { OK "GSI=LIVE (verified portal layer catalog built, no credentials needed)" }
elseif ($gStatus -eq "STALE") { OK "GSI=STALE (catalog written; a portal probe was unreachable - honest)" }
elseif ($gStatus -eq "ERROR") { BAD "GSI=ERROR (verified=false? it must be verified:true to catalog)" }
else { BAD "unexpected GSI status '$gStatus' (expected LIVE or STALE)" }

HDR "5. HONESTY GATE: catalog rows never become landslide values"
# The ML landslide pipeline reads landslide_data. GSI is catalog-only, so it must
# contribute ZERO rows there (no verified bulletin/inventory parser is implemented).
$lsRows = PsqlQ 'SELECT COUNT(*) FROM landslide_data WHERE source=''gsi'';'
Write-Host "  landslide_data rows with source=gsi: $lsRows"
if ($lsRows -eq "0") { OK "no GSI rows in landslide_data (a portal layer never masquerades as susceptibility)" }
else { BAD "found GSI rows in landslide_data (must be 0 - no verified parser implemented)" }
$catRows = PsqlQ 'SELECT COUNT(*) FROM gsi_layers;'
Write-Host "  gsi_layers rows: $catRows"
if (($catRows -as [int]) -gt 0) { OK "verified portal layers cataloged" } else { BAD "no gsi_layers rows (catalog probe did not run?)" }
# Every catalog record MUST be stage=CATALOG_ONLY.
$badStage = PsqlQ 'SELECT COUNT(*) FROM gsi_layers WHERE stage <> ''CATALOG_ONLY'';'
if ($badStage -eq "0") { OK "all catalog records are stage=CATALOG_ONLY" }
else { BAD "a catalog record has a non-CATALOG_ONLY stage without a verified parser" }

HDR "6. Cataloged layers come from the verified registry (never invented)"
Write-Host "  cataloged layers (layer_key | role | service_url | geographic_scope):"
$rows = PsqlQ 'SELECT COALESCE(layer_key,''?'') || '' | '' || COALESCE(role,''-'') || '' | '' || COALESCE(service_url,''-'') || '' | '' || COALESCE(geographic_scope,''-'') FROM gsi_layers ORDER BY layer_key LIMIT 20;'
($rows -split "`n") | ForEach-Object { "    $_" }
# Every service_url should be a bhusanket.gsi.gov.in host (the verified portal).
$badHost = PsqlQ 'SELECT COUNT(*) FROM gsi_layers WHERE service_url IS NOT NULL AND service_url NOT LIKE ''%bhusanket.gsi.gov.in%'';'
Write-Host "  catalog rows whose service_url is NOT a bhusanket.gsi.gov.in host: $badHost"
if ($badHost -eq "0") { OK "all cataloged layers point at the verified bhusanket.gsi.gov.in portal (none invented)" }
else { BAD "a cataloged layer is not a bhusanket.gsi.gov.in host (possible invented URL)" }
# The verified regional COVERAGE note must be preserved (not fabricated away).
$noScope = PsqlQ 'SELECT COUNT(*) FROM gsi_layers WHERE geographic_scope IS NULL OR geographic_scope = '''';'
Write-Host "  catalog rows missing a geographic_scope coverage note: $noScope"
if ($noScope -eq "0") { OK "every layer preserves its verified regional COVERAGE note (GSI is NOT nationwide)" }
else { BAD "a catalog row lost its coverage note (app could wrongly imply nationwide coverage)" }

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
Write-Host "  data-sources status (should list gsi):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'gsi','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Re-run the GSI catalog probe (idempotent - no duplicate rows)"
$before = PsqlQ 'SELECT COUNT(*) FROM gsi_layers;'
Write-Host "  gsi_layers rows before re-probe: $before"
& $DOCKER exec -i $BE python -m app.services.gsi_boot 2>&1 | ForEach-Object { "    $_" }
$after = PsqlQ 'SELECT COUNT(*) FROM gsi_layers;'
Write-Host "  gsi_layers rows after re-probe: $after"
if ($before -eq $after -and ($after -as [int]) -gt 0) {
  OK "re-cataloging is idempotent (row count unchanged on the natural key)"
} else {
  BAD "row count changed on re-probe ($before -> $after) - upsert not idempotent"
}
# Re-assert the honesty gate AFTER a re-catalog.
$lsRows2 = PsqlQ 'SELECT COUNT(*) FROM landslide_data WHERE source=''gsi'';'
Write-Host "  post-probe landslide_data rows with source=gsi: $lsRows2"
if ($lsRows2 -eq "0") { OK "after a re-catalog, still NO GSI rows in landslide_data" }
else { BAD "a re-catalog leaked rows into landslide_data" }

HDR "14. Landslide-value honesty verdict"
$lsRowsF = PsqlQ 'SELECT COUNT(*) FROM landslide_data WHERE source=''gsi'';'
Write-Host "  landslide contamination check - GSI rows in landslide_data: $lsRowsF"
if ($lsRowsF -eq "0") {
  Write-Host "  VERDICT: GSI/Bhusanket portal layers are stored ONLY in gsi_layers."
  Write-Host "           No forecast bulletin, susceptibility map or inventory link is treated"
  Write-Host "           as a numeric landslide value. Real GSI susceptibility/probability would"
  Write-Host "           require a separate, gated, verified parse of a specific documented public"
  Write-Host "           resource first, and that stage is deliberately NOT performed at ingestion."
  Write-Host "           Each layer preserves its regional COVERAGE note, so the app marks GSI"
  Write-Host "           unavailable outside its coverage rather than fabricating a forecast."
  OK "no catalog-as-measurement contamination"
} else {
  Write-Host "  VERDICT: $lsRowsF GSI row(s) reached landslide_data - this VIOLATES the"
  Write-Host "           catalog-only contract (landslide values require a gated verified parse)."
  BAD "GSI contaminated the landslide table"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser)."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
