# =============================================================================
# Bhuvan/NRSC runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_bhuvan_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). Bhuvan/NRSC is CATALOG-ONLY - it is NOT discovery-only and NOT a
# measurement source. Bhuvan is a STATIC terrain/context source exposed as OGC
# WMS/WMTS layers (CartoDEM, LULC, geomorphology, lineament, historical flood-
# hazard/annual). The verified note is explicit: "Do not scrape rendered map
# pixels as a substitute for the DEM", and quantitative terrain must be derived
# from downloaded DEM tiles and preprocessed once (a stage NOT implemented). So
# this collector records verified layer ENDPOINTS in bhuvan_layers only.
#
# HONESTY GATE (different from GPM/SMAP/MOSDAC discovery gate): the catalog must
# never populate terrain_features (which the ML feature pipeline reads). Every
# bhuvan_layers row is stage='CATALOG_ONLY' and carries NO numeric terrain value
# (the table has no measurement column at all). A layer endpoint / map pixel must
# never masquerade as an elevation/slope value.
#
# CONFIGURATION GATE (different again): the verified Bhuvan registry hard-codes
# the REAL public OGC endpoints, and cataloging needs no credentials, so
# verified=true alone is enough to build the catalog -> LIVE.
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

HDR "2. Alembic applied migrations (expect head = 0006_bhuvan_layers)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0006_bhuvan_layers") { OK "0006_bhuvan_layers is applied" }
else { BAD "0006_bhuvan_layers not at head" }

HDR "3. bhuvan_layers table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.bhuvan_layers'') IS NOT NULL;'
if ($exists -eq "t") { OK "table bhuvan_layers exists" } else { BAD "table bhuvan_layers missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''bhuvan_layers'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# A catalog entry describes a service endpoint, NOT a point observation, so
# (unlike gpm/smap/mosdac discovery tables) there is deliberately NO geometry.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''bhuvan_layers'';'
Write-Host "  geometry columns on bhuvan_layers: $hasGeom"
if ($hasGeom -eq "0") { OK "bhuvan_layers has NO geometry column (a catalog entry is an endpoint, not a point)" }
else { BAD "unexpected geometry column on bhuvan_layers (catalog rows are not observations)" }

HDR "4. Bhuvan source status is honest (LIVE - verified public OGC, no creds)"
$bStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''bhuvan'';'
Write-Host "  source_health.bhuvan status: $bStatus"
# Cataloging the verified registry is an offline op over verified static
# metadata; a fully reachable/verified catalog reports LIVE. If an optional OGC
# probe found an endpoint unreachable it would honestly be STALE (still valid).
if ($bStatus -eq "LIVE") { OK "Bhuvan=LIVE (verified OGC layer catalog built, no credentials needed)" }
elseif ($bStatus -eq "STALE") { OK "Bhuvan=STALE (catalog written; an OGC endpoint probe was unreachable - honest)" }
elseif ($bStatus -eq "ERROR") { BAD "Bhuvan=ERROR (verified=false? it must be verified:true to catalog)" }
else { BAD "unexpected Bhuvan status '$bStatus' (expected LIVE or STALE)" }

HDR "5. HONESTY GATE: catalog rows never become terrain values"
# The ML feature pipeline reads terrain_features. Bhuvan is catalog-only, so it
# must contribute ZERO rows there (no DEM-tile processing stage is implemented).
$terrRows = PsqlQ 'SELECT COUNT(*) FROM terrain_features WHERE source=''bhuvan'';'
Write-Host "  terrain_features rows with source=bhuvan: $terrRows"
if ($terrRows -eq "0") { OK "no Bhuvan rows in terrain_features (a layer endpoint never masquerades as terrain)" }
else { BAD "found Bhuvan rows in terrain_features (must be 0 - no DEM processor implemented)" }
$catRows = PsqlQ 'SELECT COUNT(*) FROM bhuvan_layers;'
Write-Host "  bhuvan_layers rows: $catRows"
if (($catRows -as [int]) -gt 0) { OK "verified layer endpoints cataloged" } else { BAD "no bhuvan_layers rows (catalog probe did not run?)" }
# Every catalog record MUST be stage=CATALOG_ONLY.
$badStage = PsqlQ 'SELECT COUNT(*) FROM bhuvan_layers WHERE stage <> ''CATALOG_ONLY'';'
if ($badStage -eq "0") { OK "all catalog records are stage=CATALOG_ONLY" }
else { BAD "a catalog record has a non-CATALOG_ONLY stage without a DEM-processing stage" }

HDR "6. Cataloged endpoints come from the verified registry (never invented)"
Write-Host "  cataloged layers (layer_key | service_type | role | service_url):"
$rows = PsqlQ 'SELECT COALESCE(layer_key,''?'') || '' | '' || COALESCE(service_type,''-'') || '' | '' || COALESCE(role,''-'') || '' | '' || COALESCE(service_url,''-'') FROM bhuvan_layers ORDER BY layer_key LIMIT 20;'
($rows -split "`n") | ForEach-Object { "    $_" }
# Every service_url should be an nrsc.gov.in host (the verified public endpoints).
$badHost = PsqlQ 'SELECT COUNT(*) FROM bhuvan_layers WHERE service_url IS NOT NULL AND service_url NOT LIKE ''%nrsc.gov.in%'';'
Write-Host "  catalog rows whose service_url is NOT an nrsc.gov.in host: $badHost"
if ($badHost -eq "0") { OK "all cataloged endpoints are verified nrsc.gov.in OGC services (none invented)" }
else { BAD "a cataloged endpoint is not an nrsc.gov.in host (possible invented URL)" }

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
Write-Host "  data-sources status (should list bhuvan):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'bhuvan','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Re-run the Bhuvan catalog probe (idempotent - no duplicate rows)"
$before = PsqlQ 'SELECT COUNT(*) FROM bhuvan_layers;'
Write-Host "  bhuvan_layers rows before re-probe: $before"
& $DOCKER exec -i $BE python -m app.services.bhuvan_boot 2>&1 | ForEach-Object { "    $_" }
$after = PsqlQ 'SELECT COUNT(*) FROM bhuvan_layers;'
Write-Host "  bhuvan_layers rows after re-probe: $after"
if ($before -eq $after -and ($after -as [int]) -gt 0) {
  OK "re-cataloging is idempotent (row count unchanged on the natural key)"
} else {
  BAD "row count changed on re-probe ($before -> $after) - upsert not idempotent"
}
# Re-assert the honesty gate AFTER a re-catalog.
$terrRows2 = PsqlQ 'SELECT COUNT(*) FROM terrain_features WHERE source=''bhuvan'';'
Write-Host "  post-probe terrain_features rows with source=bhuvan: $terrRows2"
if ($terrRows2 -eq "0") { OK "after a re-catalog, still NO Bhuvan rows in terrain_features" }
else { BAD "a re-catalog leaked rows into terrain_features" }

HDR "14. Terrain-value honesty verdict"
$terrRowsF = PsqlQ 'SELECT COUNT(*) FROM terrain_features WHERE source=''bhuvan'';'
Write-Host "  terrain contamination check - Bhuvan rows in terrain_features: $terrRowsF"
if ($terrRowsF -eq "0") {
  Write-Host "  VERDICT: Bhuvan/NRSC layer endpoints are stored ONLY in bhuvan_layers."
  Write-Host "           No WMS/WMTS layer or rendered map pixel is treated as a numeric"
  Write-Host "           terrain value. Quantitative terrain (elevation/slope/aspect/...) would"
  Write-Host "           require a separate, gated DEM-tile processing stage first, and that"
  Write-Host "           stage is deliberately NOT performed at ingestion."
  OK "no catalog-as-measurement contamination"
} else {
  Write-Host "  VERDICT: $terrRowsF Bhuvan row(s) reached terrain_features - this VIOLATES"
  Write-Host "           the catalog-only contract (terrain values require a gated DEM stage)."
  BAD "Bhuvan contaminated the terrain table"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser)."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
