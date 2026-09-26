# =============================================================================
# CWC / NWIC runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_cwc_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). CWC/NWIC is CATALOG-ONLY - it is NOT discovery-only and NOT a
# numeric hydro feed. The Central Water Commission's National Water Data Portal
# (https://www.nwdp.nwic.gov.in) advertises hourly river-water-level telemetry,
# CWC rainfall telemetry and manual daily reservoir storage as CSV/API datasets.
# The verified note is explicit: "This package intentionally does not invent an
# undocumented API URL" and "the exact API endpoint/auth contract was not
# verified". So this collector records verified DATASET-PAGE URLs (base_url +
# registry path) + roles + formats + frequencies in cwc_resources only, and never
# produces a numeric water-level or rainfall value.
#
# HONESTY GATE (different from GPM/SMAP/MOSDAC discovery gate): the catalog must
# never populate river_observations OR rainfall_observations (which the ML feature
# pipeline reads). Every cwc_resources row is stage='CATALOG_ONLY' and carries NO
# numeric hydro value (the table has no measurement column at all). A dataset-page
# link must never masquerade as a water-level/rainfall value.
#
# CONFIGURATION GATE (like Bhuvan/GSI): the verified CWC config hard-codes the REAL
# public portal (https://www.nwdp.nwic.gov.in), and cataloging needs no
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

HDR "2. Alembic applied migrations (expect head = 0008_cwc_resources)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0008_cwc_resources") { OK "0008_cwc_resources is applied" }
else { BAD "0008_cwc_resources not at head" }

HDR "3. cwc_resources table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.cwc_resources'') IS NOT NULL;'
if ($exists -eq "t") { OK "table cwc_resources exists" } else { BAD "table cwc_resources missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''cwc_resources'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# A catalog entry describes a dataset PAGE/endpoint, NOT a point observation, so
# (unlike gpm/smap/mosdac discovery tables) there is deliberately NO geometry.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''cwc_resources'';'
Write-Host "  geometry columns on cwc_resources: $hasGeom"
if ($hasGeom -eq "0") { OK "cwc_resources has NO geometry column (a catalog entry is a dataset page, not a point)" }
else { BAD "unexpected geometry column on cwc_resources (catalog rows are not observations)" }

HDR "4. CWC source status is honest (LIVE - verified public portal, no creds)"
$cStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''cwc'';'
Write-Host "  source_health.cwc status: $cStatus"
# Cataloging the verified registry is an offline op over verified static
# metadata; a fully reachable/verified catalog reports LIVE. If an optional portal
# probe found the NWDP portal unreachable it would honestly be STALE.
if ($cStatus -eq "LIVE") { OK "CWC=LIVE (verified NWDP dataset catalog built, no credentials needed)" }
elseif ($cStatus -eq "STALE") { OK "CWC=STALE (catalog written; a portal probe was unreachable - honest)" }
elseif ($cStatus -eq "ERROR") { BAD "CWC=ERROR (verified=false? it must be verified:true to catalog)" }
else { BAD "unexpected CWC status '$cStatus' (expected LIVE or STALE)" }

HDR "5. HONESTY GATE: catalog rows never become hydro values"
# The ML feature pipeline reads river_observations + rainfall_observations. CWC is
# catalog-only, so it must contribute ZERO rows to EITHER (no verified CSV/API
# parser is implemented).
$rivRows = PsqlQ 'SELECT COUNT(*) FROM river_observations WHERE source=''cwc'';'
Write-Host "  river_observations rows with source=cwc: $rivRows"
if ($rivRows -eq "0") { OK "no CWC rows in river_observations (a dataset page never masquerades as a water level)" }
else { BAD "found CWC rows in river_observations (must be 0 - no verified parser implemented)" }
$rainRows = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''cwc'';'
Write-Host "  rainfall_observations rows with source=cwc: $rainRows"
if ($rainRows -eq "0") { OK "no CWC rows in rainfall_observations (a dataset page never masquerades as rainfall)" }
else { BAD "found CWC rows in rainfall_observations (must be 0 - no verified parser implemented)" }
$catRows = PsqlQ 'SELECT COUNT(*) FROM cwc_resources;'
Write-Host "  cwc_resources rows: $catRows"
if (($catRows -as [int]) -gt 0) { OK "verified NWDP datasets cataloged" } else { BAD "no cwc_resources rows (catalog probe did not run?)" }
# Every catalog record MUST be stage=CATALOG_ONLY.
$badStage = PsqlQ 'SELECT COUNT(*) FROM cwc_resources WHERE stage <> ''CATALOG_ONLY'';'
if ($badStage -eq "0") { OK "all catalog records are stage=CATALOG_ONLY" }
else { BAD "a catalog record has a non-CATALOG_ONLY stage without a verified parser" }

HDR "6. Cataloged datasets come from the verified portal (never invented)"
Write-Host "  cataloged datasets (dataset_key | role | dataset_url | frequency):"
$rows = PsqlQ 'SELECT COALESCE(dataset_key,''?'') || '' | '' || COALESCE(role,''-'') || '' | '' || COALESCE(dataset_url,''-'') || '' | '' || COALESCE(frequency,''-'') FROM cwc_resources ORDER BY dataset_key LIMIT 20;'
($rows -split "`n") | ForEach-Object { "    $_" }
# Every dataset_url should be an nwdp.nwic.gov.in host (the verified portal).
$badHost = PsqlQ 'SELECT COUNT(*) FROM cwc_resources WHERE dataset_url IS NOT NULL AND dataset_url NOT LIKE ''%nwdp.nwic.gov.in%'';'
Write-Host "  catalog rows whose dataset_url is NOT an nwdp.nwic.gov.in host: $badHost"
if ($badHost -eq "0") { OK "all cataloged datasets point at the verified nwdp.nwic.gov.in portal (none invented)" }
else { BAD "a cataloged dataset is not an nwdp.nwic.gov.in host (possible invented URL)" }
# The portal advertises API as a format, but the exact endpoint was NOT verified -
# so no row may claim a bare API endpoint as its dataset_url; every URL is a
# documented dataset PAGE under /en/dataset/.
$badPath = PsqlQ 'SELECT COUNT(*) FROM cwc_resources WHERE dataset_url IS NOT NULL AND dataset_url NOT LIKE ''%/dataset/%'';'
Write-Host "  catalog rows whose dataset_url is not a documented /dataset/ page: $badPath"
if ($badPath -eq "0") { OK "every dataset_url is a documented dataset PAGE (no invented API endpoint)" }
else { BAD "a dataset_url is not a documented /dataset/ page (possible invented API endpoint)" }

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
Write-Host "  data-sources status (should list cwc):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'cwc','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Re-run the CWC catalog probe (idempotent - no duplicate rows)"
$before = PsqlQ 'SELECT COUNT(*) FROM cwc_resources;'
Write-Host "  cwc_resources rows before re-probe: $before"
& $DOCKER exec -i $BE python -m app.services.cwc_boot 2>&1 | ForEach-Object { "    $_" }
$after = PsqlQ 'SELECT COUNT(*) FROM cwc_resources;'
Write-Host "  cwc_resources rows after re-probe: $after"
if ($before -eq $after -and ($after -as [int]) -gt 0) {
  OK "re-cataloging is idempotent (row count unchanged on the natural key)"
} else {
  BAD "row count changed on re-probe ($before -> $after) - upsert not idempotent"
}
# Re-assert the honesty gate AFTER a re-catalog.
$rivRows2 = PsqlQ 'SELECT COUNT(*) FROM river_observations WHERE source=''cwc'';'
$rainRows2 = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''cwc'';'
Write-Host "  post-probe river_observations rows with source=cwc: $rivRows2"
Write-Host "  post-probe rainfall_observations rows with source=cwc: $rainRows2"
if ($rivRows2 -eq "0" -and $rainRows2 -eq "0") { OK "after a re-catalog, still NO CWC rows in river/rainfall observations" }
else { BAD "a re-catalog leaked rows into an observation table" }

HDR "14. Hydro-value honesty verdict"
$rivF  = PsqlQ 'SELECT COUNT(*) FROM river_observations WHERE source=''cwc'';'
$rainF = PsqlQ 'SELECT COUNT(*) FROM rainfall_observations WHERE source=''cwc'';'
Write-Host "  hydro contamination check - CWC rows in river_observations: $rivF ; rainfall_observations: $rainF"
if ($rivF -eq "0" -and $rainF -eq "0") {
  Write-Host "  VERDICT: CWC/NWIC dataset pages are stored ONLY in cwc_resources."
  Write-Host "           No river-level, rainfall or reservoir CSV/API link is treated as a"
  Write-Host "           numeric hydrological value. Real CWC telemetry would require a separate,"
  Write-Host "           gated, verified parse of a specific documented CSV/API resource first,"
  Write-Host "           and that stage is deliberately NOT performed at ingestion. The verified"
  Write-Host "           note says the exact API endpoint/auth contract was NOT verified, so the"
  Write-Host "           collector never invents one - it catalogs the documented dataset pages only."
  OK "no catalog-as-measurement contamination"
} else {
  Write-Host "  VERDICT: CWC row(s) reached an observation table - this VIOLATES the"
  Write-Host "           catalog-only contract (hydro values require a gated verified parse)."
  BAD "CWC contaminated an observation table"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser)."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
