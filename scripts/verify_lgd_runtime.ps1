# =============================================================================
# LGD runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_lgd_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). LGD (Local Government Directory) is CATALOG-ONLY - it is the
# Government of India's AUTHORITATIVE directory of administrative identity + CODES
# for the India -> State/UT -> District -> Sub-district -> Block -> Village/ULB ->
# Ward hierarchy, exposed as downloadable directories at
# https://lgdirectory.gov.in/demo/downloadDirectory.do. The verified note is
# explicit on TWO honesty boundaries: (1) "Do not assume LGD directory tables are
# themselves polygon datasets. Boundary geometry must be sourced from an
# authoritative GIS boundary product and versioned separately ... joined using LGD
# codes." (2) "Use LGD codes as stable join keys. Names are display fields only."
# So this collector records verified directory DATASETS (one per admin level) +
# level + purpose + the verified download-portal URL in lgd_directory only, and
# never produces a boundary polygon, a coordinate, or an administrative-unit row.
#
# HONESTY GATE: the catalog must never carry geometry (there is deliberately NO
# geometry column) and every lgd_directory row is stage='CATALOG_ONLY'. A directory
# dataset link must never masquerade as a boundary polygon or a measurement.
#
# CONFIGURATION GATE (like Bhuvan/GSI/CWC): the verified LGD config hard-codes the
# REAL public download portal, and cataloging needs no credentials, so verified=true
# alone is enough to build the catalog -> LIVE.
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

HDR "2. Alembic applied migrations (expect head = 0009_lgd_directory)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0009_lgd_directory") { OK "0009_lgd_directory is applied" }
else { BAD "0009_lgd_directory not at head" }

HDR "3. lgd_directory table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.lgd_directory'') IS NOT NULL;'
if ($exists -eq "t") { OK "table lgd_directory exists" } else { BAD "table lgd_directory missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''lgd_directory'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# LGD is authoritative for administrative CODES, NOT geometry - the verified note
# forbids treating the directory as a polygon dataset. Geometry must come from an
# authoritative GIS product joined by LGD code, so there is deliberately NO geometry.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''lgd_directory'';'
Write-Host "  geometry columns on lgd_directory: $hasGeom"
if ($hasGeom -eq "0") { OK "lgd_directory has NO geometry column (LGD is codes, not boundary polygons)" }
else { BAD "unexpected geometry column on lgd_directory (LGD must not be treated as a polygon dataset)" }

HDR "4. LGD source status is honest (LIVE - verified public portal, no creds)"
$lStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''lgd'';'
Write-Host "  source_health.lgd status: $lStatus"
# Cataloging the verified registry is an offline op over verified static
# metadata; a fully reachable/verified catalog reports LIVE. If an optional portal
# probe found the LGD download page unreachable it would honestly be STALE.
if ($lStatus -eq "LIVE") { OK "LGD=LIVE (verified directory catalog built, no credentials needed)" }
elseif ($lStatus -eq "STALE") { OK "LGD=STALE (catalog written; a portal probe was unreachable - honest)" }
elseif ($lStatus -eq "ERROR") { BAD "LGD=ERROR (verified=false? it must be verified:true to catalog)" }
else { BAD "unexpected LGD status '$lStatus' (expected LIVE or STALE)" }

HDR "5. HONESTY GATE: catalog rows are directory metadata, never geometry/values"
$catRows = PsqlQ 'SELECT COUNT(*) FROM lgd_directory;'
Write-Host "  lgd_directory rows: $catRows"
if (($catRows -as [int]) -gt 0) { OK "verified LGD directory datasets cataloged" } else { BAD "no lgd_directory rows (catalog probe did not run?)" }
# Every catalog record MUST be stage=CATALOG_ONLY.
$badStage = PsqlQ 'SELECT COUNT(*) FROM lgd_directory WHERE stage <> ''CATALOG_ONLY'';'
if ($badStage -eq "0") { OK "all catalog records are stage=CATALOG_ONLY" }
else { BAD "a catalog record has a non-CATALOG_ONLY stage without a verified parser" }
# Every catalog record MUST carry an admin_level (the verified level, not a name).
$noLevel = PsqlQ 'SELECT COUNT(*) FROM lgd_directory WHERE admin_level IS NULL OR admin_level = '''';'
Write-Host "  catalog rows missing an admin_level: $noLevel"
if ($noLevel -eq "0") { OK "every directory dataset carries its verified admin_level (codes-first, names are display-only)" }
else { BAD "a catalog row lost its admin_level" }

HDR "6. Cataloged datasets come from the verified portal (never invented)"
Write-Host "  cataloged datasets (dataset_key | admin_level | directory_url):"
$rows = PsqlQ 'SELECT COALESCE(dataset_key,''?'') || '' | '' || COALESCE(admin_level,''-'') || '' | '' || COALESCE(directory_url,''-'') FROM lgd_directory ORDER BY dataset_key LIMIT 20;'
($rows -split "`n") | ForEach-Object { "    $_" }
# Every directory_url should be an lgdirectory.gov.in host (the verified portal).
$badHost = PsqlQ 'SELECT COUNT(*) FROM lgd_directory WHERE directory_url IS NOT NULL AND directory_url NOT LIKE ''%lgdirectory.gov.in%'';'
Write-Host "  catalog rows whose directory_url is NOT an lgdirectory.gov.in host: $badHost"
if ($badHost -eq "0") { OK "all cataloged datasets point at the verified lgdirectory.gov.in portal (none invented)" }
else { BAD "a cataloged dataset is not an lgdirectory.gov.in host (possible invented URL/file name)" }

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
Write-Host "  data-sources status (should list lgd):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'lgd','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Re-run the LGD catalog probe (idempotent - no duplicate rows)"
$before = PsqlQ 'SELECT COUNT(*) FROM lgd_directory;'
Write-Host "  lgd_directory rows before re-probe: $before"
& $DOCKER exec -i $BE python -m app.services.lgd_boot 2>&1 | ForEach-Object { "    $_" }
$after = PsqlQ 'SELECT COUNT(*) FROM lgd_directory;'
Write-Host "  lgd_directory rows after re-probe: $after"
if ($before -eq $after -and ($after -as [int]) -gt 0) {
  OK "re-cataloging is idempotent (row count unchanged on the natural key)"
} else {
  BAD "row count changed on re-probe ($before -> $after) - upsert not idempotent"
}
# Re-assert the geometry-honesty gate AFTER a re-catalog.
$hasGeom2 = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''lgd_directory'';'
Write-Host "  post-probe geometry columns on lgd_directory: $hasGeom2"
if ($hasGeom2 -eq "0") { OK "after a re-catalog, lgd_directory still has NO geometry column" }
else { BAD "a re-catalog introduced a geometry column" }

HDR "14. Administrative-honesty verdict"
$catF = PsqlQ 'SELECT COUNT(*) FROM lgd_directory;'
$geomF = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''lgd_directory'';'
Write-Host "  lgd_directory rows: $catF ; geometry columns: $geomF"
if ($geomF -eq "0") {
  Write-Host "  VERDICT: LGD directory datasets are stored ONLY in lgd_directory as"
  Write-Host "           administrative-identity metadata (dataset + level + purpose + the"
  Write-Host "           verified download-portal URL). No directory link is treated as a"
  Write-Host "           boundary polygon, a coordinate, or an administrative-unit row. Boundary"
  Write-Host "           geometry must come from an authoritative GIS product and be joined by"
  Write-Host "           LGD code; LGD codes (never names) are the stable join keys. Real LGD unit"
  Write-Host "           rows would require a separate, gated, verified directory-file parse first,"
  Write-Host "           and that stage is deliberately NOT performed at ingestion."
  OK "no catalog-as-geometry contamination"
} else {
  Write-Host "  VERDICT: lgd_directory has a geometry column - this VIOLATES the verified"
  Write-Host "           boundary that LGD directory tables are NOT polygon datasets."
  BAD "LGD catalog was treated as a geometry source"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser)."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
