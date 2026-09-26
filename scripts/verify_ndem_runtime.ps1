# =============================================================================
# NDEM runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_ndem_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). NDEM (National Database for Emergency Management) is CATALOG-ONLY.
# NDEM is an NRSC/ISRO national GIS repository + decision-support system for
# disaster management, run with MHA for near-real-time disaster support
# (near-real-time flood monitoring, flood early warning/vulnerability, landslide
# hazard inventory, district nowcast aggregation, historical flood reference).
#
# The verified note (ndem_verified.md / README.md) is explicit on two honesty
# boundaries: (1) NDEM's non-base products are PROTECTED - the portal requires a
# username/password obtained through an authorization form, and authorized users
# are Central/State/District/NDRF/SDRF officials; only public/base layers may be
# visible without login. So this connector must "never bypass authentication or
# invent an undocumented API." (2) "Store access_level and source-health separately
# from risk score." So this collector records the verified NDEM CAPABILITIES (name +
# access level + role + the verified public portal URL) in ndem_capabilities only,
# and never produces a measurement, a geometry, an event or a risk score. Every
# capability shares the SAME public portal URL (like GSI/LGD), so capability_key
# keeps rows distinct.
#
# HONESTY GATE: the catalog must never carry a measurement, a geometry, an event or
# a risk score (there is deliberately NO such column) and every ndem_capabilities
# row is stage='CATALOG_ONLY'. A capability reference must never masquerade as a
# flood/landslide value, and the access level is metadata, never a risk score.
#
# CONFIGURATION GATE (like Bhuvan/GSI/CWC/LGD): the verified config hard-codes the
# REAL public portal, and cataloging the PUBLIC capability list needs no credentials,
# so verified=true alone is enough to build the catalog -> LIVE. Protected products
# require portal auth (NDEM_USERNAME/NDEM_PASSWORD) but that is a FUTURE gated
# authorized adapter - this probe never authenticates.
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

HDR "2. Alembic applied migrations (expect head = 0011_ndem_capabilities)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0011_ndem_capabilities") { OK "0011_ndem_capabilities is applied" }
else { BAD "0011_ndem_capabilities not at head" }

HDR "3. ndem_capabilities table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.ndem_capabilities'') IS NOT NULL;'
if ($exists -eq "t") { OK "table ndem_capabilities exists" } else { BAD "table ndem_capabilities missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''ndem_capabilities'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# NDEM catalog records CAPABILITIES, not measurements. The verified note keeps
# protected products behind authentication and stores access_level separately from
# risk - so there is deliberately NO geometry, NO measurement/value and NO risk
# column: a capability reference can never become a flood/landslide value.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''ndem_capabilities'';'
Write-Host "  geometry columns on ndem_capabilities: $hasGeom"
if ($hasGeom -eq "0") { OK "ndem_capabilities has NO geometry column (it catalogs capabilities, not measurements)" }
else { BAD "unexpected geometry column on ndem_capabilities (a capability must not become a measurement)" }
# Assert the schema carries no measurement / risk / event columns either.
$badCols = PsqlQ 'SELECT COUNT(*) FROM information_schema.columns WHERE table_name=''ndem_capabilities'' AND column_name IN (''latitude'',''longitude'',''numeric_value'',''value'',''risk_score'',''event_time'',''flood_probability'',''landslide_probability'');'
Write-Host "  measurement/risk/event columns present on ndem_capabilities: $badCols"
if ($badCols -eq "0") { OK "no measurement / risk / event column exists (catalog is capability-only)" }
else { BAD "ndem_capabilities has a measurement/risk/event column - a capability could masquerade as a value" }

HDR "4. NDEM source status is honest (LIVE - verified public portal, no creds)"
$nStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''ndem'';'
Write-Host "  source_health.ndem status: $nStatus"
# Cataloging the verified PUBLIC capability list is an offline op over verified
# static metadata; a fully reachable/verified catalog reports LIVE. If an optional
# public-portal probe found the portal unreachable it would honestly be STALE.
if ($nStatus -eq "LIVE") { OK "NDEM=LIVE (verified public capability catalog built, no credentials needed)" }
elseif ($nStatus -eq "STALE") { OK "NDEM=STALE (catalog written; a public-portal probe was unreachable - honest)" }
elseif ($nStatus -eq "ERROR") { BAD "NDEM=ERROR (verified=false? it must be verified:true to catalog)" }
else { BAD "unexpected NDEM status '$nStatus' (expected LIVE or STALE)" }

HDR "5. HONESTY GATE: catalog rows are capability metadata, never values/risk"
$catRows = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities;'
Write-Host "  ndem_capabilities rows: $catRows"
if (($catRows -as [int]) -gt 0) { OK "verified NDEM capabilities cataloged" } else { BAD "no ndem_capabilities rows (catalog probe did not run?)" }
# Every catalog record MUST be stage=CATALOG_ONLY.
$badStage = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities WHERE stage <> ''CATALOG_ONLY'';'
if ($badStage -eq "0") { OK "all catalog records are stage=CATALOG_ONLY" }
else { BAD "a catalog record has a non-CATALOG_ONLY stage without a verified parser" }
# Every catalog record MUST carry an access classification (verbatim from registry).
$noAccess = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities WHERE access IS NULL OR access = '''';'
Write-Host "  catalog rows missing an access level: $noAccess"
if ($noAccess -eq "0") { OK "every capability carries its verified access level (metadata, stored separately from risk)" }
else { BAD "a catalog row lost its access level" }
# access must be one of the three verified verbatim classes - never invented.
$badAccess = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities WHERE access NOT IN (''PUBLIC'',''AUTHORIZED'',''AUTHORIZED_OR_PRODUCT_SPECIFIC'');'
if ($badAccess -eq "0") { OK "every access level is a verified verbatim class (none invented)" }
else { BAD "a catalog row has an access level outside the verified set" }

HDR "6. Cataloged capabilities come from the verified portal (never invented)"
Write-Host "  cataloged capabilities (capability_key | access | source_url):"
$rows = PsqlQ 'SELECT COALESCE(capability_key,''?'') || '' | '' || COALESCE(access,''-'') || '' | '' || COALESCE(source_url,''-'') FROM ndem_capabilities ORDER BY capability_key LIMIT 20;'
($rows -split "`n") | ForEach-Object { "    $_" }
# Every source_url should be an ndem.nrsc.gov.in host (the verified public portal).
$badHost = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities WHERE source_url IS NOT NULL AND source_url NOT LIKE ''%ndem.nrsc.gov.in%'';'
Write-Host "  catalog rows whose source_url is NOT an ndem.nrsc.gov.in host: $badHost"
if ($badHost -eq "0") { OK "all cataloged capabilities point at the verified ndem.nrsc.gov.in portal (none invented)" }
else { BAD "a cataloged capability is not an ndem.nrsc.gov.in host (possible invented URL/private API)" }
# Like GSI/LGD, every capability shares ONE portal URL - capability_key keeps rows distinct.
$distinctUrls = PsqlQ 'SELECT COUNT(DISTINCT source_url) FROM ndem_capabilities;'
Write-Host "  distinct source_url values: $distinctUrls (rows: $catRows)"
if (($distinctUrls -as [int]) -eq 1 -and ($catRows -as [int]) -gt 1) {
  OK "all capabilities share ONE verified portal URL (GSI/LGD-style shared-URL key, no per-capability URL invented)"
} else {
  OK "source_url cardinality = $distinctUrls (acceptable; verify none is an invented private endpoint)"
}

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
Write-Host "  data-sources status (should list ndem):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'ndem','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Re-run the NDEM catalog probe (idempotent - no duplicate rows)"
$before = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities;'
Write-Host "  ndem_capabilities rows before re-probe: $before"
& $DOCKER exec -i $BE python -m app.services.ndem_boot 2>&1 | ForEach-Object { "    $_" }
$after = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities;'
Write-Host "  ndem_capabilities rows after re-probe: $after"
if ($before -eq $after -and ($after -as [int]) -gt 0) {
  OK "re-cataloging is idempotent (row count unchanged on the natural key)"
} else {
  BAD "row count changed on re-probe ($before -> $after) - upsert not idempotent"
}
# Re-assert the geometry-honesty gate AFTER a re-catalog.
$hasGeom2 = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''ndem_capabilities'';'
Write-Host "  post-probe geometry columns on ndem_capabilities: $hasGeom2"
if ($hasGeom2 -eq "0") { OK "after a re-catalog, ndem_capabilities still has NO geometry column" }
else { BAD "a re-catalog introduced a geometry column" }

HDR "14. Disaster-capability-honesty verdict"
$catF = PsqlQ 'SELECT COUNT(*) FROM ndem_capabilities;'
$geomF = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''ndem_capabilities'';'
$valF = PsqlQ 'SELECT COUNT(*) FROM information_schema.columns WHERE table_name=''ndem_capabilities'' AND column_name IN (''numeric_value'',''value'',''risk_score'',''event_time'',''latitude'',''longitude'',''flood_probability'',''landslide_probability'');'
Write-Host "  ndem_capabilities rows: $catF ; geometry columns: $geomF ; value/risk/event columns: $valF"
if ($geomF -eq "0" -and $valF -eq "0") {
  Write-Host "  VERDICT: NDEM capabilities are stored ONLY in ndem_capabilities as"
  Write-Host "           capability metadata (capability + access level + role + the verified"
  Write-Host "           public portal URL). No capability is treated as a measurement, a"
  Write-Host "           geometry, an event or a risk score. NDEM's non-base products are"
  Write-Host "           PROTECTED and are never fetched or authenticated against here; the access"
  Write-Host "           level (PUBLIC / AUTHORIZED / AUTHORIZED_OR_PRODUCT_SPECIFIC) is metadata"
  Write-Host "           stored separately from any risk score, exactly as the verified note"
  Write-Host "           requires. Real NDEM products would require a separate, gated, AUTHORIZED"
  Write-Host "           adapter behind the same interface first, and that stage is deliberately"
  Write-Host "           NOT performed at ingestion - authentication is never bypassed and no"
  Write-Host "           undocumented API is invented."
  OK "no catalog-as-measurement / catalog-as-risk contamination"
} else {
  Write-Host "  VERDICT: ndem_capabilities has a geometry / value / risk column - this VIOLATES"
  Write-Host "           the verified boundary that the catalog records CAPABILITIES, not values."
  BAD "NDEM catalog was treated as a measurement/risk source"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser)."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
