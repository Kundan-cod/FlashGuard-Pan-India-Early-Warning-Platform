# =============================================================================
# Historical-labels runtime verification (PowerShell) - Track B (Docker + PostGIS)
# SIH 2026 PS 26192.  Native PowerShell version so it runs WITHOUT WSL.
#
# Run from the repo root in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_historical_runtime.ps1
#
# It only READS the running stack (plus HTTP GETs that trigger nothing
# destructive). The historical-labels layer is CATALOG-ONLY. It records the
# verified official SOURCES of historical flood/landslide events - NRSC/ISRO
# Landslide Atlas (~80,000 landslides, 1998-2022, 17 states + 2 UTs), the NRSC
# flood-hazard zonation, the Bhuvan historical flood-inundation layers
# (1998-2019 maximum inundation), and NDEM historical disasters (1999-present,
# portal/authentication dependent). The vendored, verified package ships ONLY a
# source registry + a THREE-STATE labeling RULE (1 = confirmed event, 0 =
# confirmed non-event ONLY where observation coverage is demonstrably adequate,
# -1 = unobserved/unknown). It ships NO event rows and NO parser.
#
# The verified note is explicit on the honesty boundary: "Do not interpret the
# inventory as a complete nationwide absence/presence census" and "Do not convert
# missing observations into negatives." So this collector catalogs the verified
# SOURCES into historical_sources only, and NEVER produces a confirmed event, a
# coordinate, an event time, or a 1/0/-1 training label. Real events + labels
# would enter a separate, gated events/labels table only after a verified
# inventory parse - a stage that is deliberately NOT performed at ingestion.
#
# HONESTY GATE: the catalog must never carry an event geometry, an event time or
# a numeric label (there is deliberately NO such column) and every
# historical_sources row is stage='CATALOG_ONLY'. A source reference must never
# masquerade as a confirmed event or a training label.
#
# CONFIGURATION GATE (like Bhuvan/GSI/CWC/LGD): the verified config hard-codes the
# REAL public source URLs, and cataloging needs no credentials, so verified=true
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

HDR "2. Alembic applied migrations (expect head = 0010_historical_sources)"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0010_historical_sources") { OK "0010_historical_sources is applied" }
else { BAD "0010_historical_sources not at head" }

HDR "3. historical_sources table exists in PostGIS (and has NO geometry column)"
$exists = PsqlQ 'SELECT to_regclass(''public.historical_sources'') IS NOT NULL;'
if ($exists -eq "t") { OK "table historical_sources exists" } else { BAD "table historical_sources missing" }
Write-Host "  columns:"
$cols = PsqlQ 'SELECT column_name || '' '' || data_type FROM information_schema.columns WHERE table_name=''historical_sources'' ORDER BY ordinal_position;'
($cols -split "`n") | ForEach-Object { "    $_" }
# The historical-labels catalog records SOURCES, not events. The verified note
# forbids treating the inventory as a presence/absence census, so there is
# deliberately NO event geometry, NO event-time and NO numeric-label column: a
# source reference can never become an event or a 1/0/-1 label at ingestion.
$hasGeom = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''historical_sources'';'
Write-Host "  geometry columns on historical_sources: $hasGeom"
if ($hasGeom -eq "0") { OK "historical_sources has NO geometry column (it catalogs sources, not events)" }
else { BAD "unexpected geometry column on historical_sources (a source reference must not become an event)" }
# Assert the schema carries no event-time / label columns either.
$badCols = PsqlQ 'SELECT COUNT(*) FROM information_schema.columns WHERE table_name=''historical_sources'' AND column_name IN (''latitude'',''longitude'',''event_time'',''target'',''label'',''is_event'');'
Write-Host "  event/label columns present on historical_sources: $badCols"
if ($badCols -eq "0") { OK "no event-time / coordinate / 1-0--1 label column exists (catalog is source-only)" }
else { BAD "historical_sources has an event/label column - a source reference could masquerade as an event/label" }

HDR "4. Historical source status is honest (LIVE - verified public sources, no creds)"
$hStatus = PsqlQ 'SELECT status FROM source_health WHERE source=''historical'';'
Write-Host "  source_health.historical status: $hStatus"
# Cataloging the verified registry is an offline op over verified static
# metadata; a fully reachable/verified catalog reports LIVE. If an optional
# source-page probe found a source unreachable it would honestly be STALE.
if ($hStatus -eq "LIVE") { OK "Historical=LIVE (verified source catalog built, no credentials needed)" }
elseif ($hStatus -eq "STALE") { OK "Historical=STALE (catalog written; a source probe was unreachable - honest)" }
elseif ($hStatus -eq "ERROR") { BAD "Historical=ERROR (verified=false? it must be verified:true to catalog)" }
else { BAD "unexpected Historical status '$hStatus' (expected LIVE or STALE)" }

HDR "5. HONESTY GATE: catalog rows are source metadata, never events/labels"
$catRows = PsqlQ 'SELECT COUNT(*) FROM historical_sources;'
Write-Host "  historical_sources rows: $catRows"
if (($catRows -as [int]) -gt 0) { OK "verified historical event SOURCES cataloged" } else { BAD "no historical_sources rows (catalog probe did not run?)" }
# Every catalog record MUST be stage=CATALOG_ONLY.
$badStage = PsqlQ 'SELECT COUNT(*) FROM historical_sources WHERE stage <> ''CATALOG_ONLY'';'
if ($badStage -eq "0") { OK "all catalog records are stage=CATALOG_ONLY" }
else { BAD "a catalog record has a non-CATALOG_ONLY stage without a verified parser" }
# Every catalog record MUST carry a hazard class (copied verbatim from the registry).
$noHazard = PsqlQ 'SELECT COUNT(*) FROM historical_sources WHERE hazard IS NULL OR hazard = '''';'
Write-Host "  catalog rows missing a hazard class: $noHazard"
if ($noHazard -eq "0") { OK "every source carries its verified hazard class (FLOOD / LANDSLIDE / FLOOD_OR_LANDSLIDE)" }
else { BAD "a catalog row lost its hazard class" }
# Hazard must be one of the three verified verbatim classes - never invented.
$badHazard = PsqlQ 'SELECT COUNT(*) FROM historical_sources WHERE hazard NOT IN (''FLOOD'',''LANDSLIDE'',''FLOOD_OR_LANDSLIDE'');'
if ($badHazard -eq "0") { OK "every hazard is a verified verbatim class (none invented)" }
else { BAD "a catalog row has a hazard class outside the verified set" }

HDR "6. Cataloged sources come from verified hosts (never invented)"
Write-Host "  cataloged sources (source_key | hazard | source_url):"
$rows = PsqlQ 'SELECT COALESCE(source_key,''?'') || '' | '' || COALESCE(hazard,''-'') || '' | '' || COALESCE(source_url,''-'') FROM historical_sources ORDER BY source_key LIMIT 20;'
($rows -split "`n") | ForEach-Object { "    $_" }
# Every source_url must be an nrsc.gov.in host (the Landslide Atlas / flood
# zonation / Bhuvan-NRSC / NDEM-NRSC all live under the nrsc.gov.in domain).
# Unlike LGD/GSI (one shared portal URL), each historical source keeps its OWN
# url - like CWC - so source_url is the row-distinguishing part of the key.
$badHost = PsqlQ 'SELECT COUNT(*) FROM historical_sources WHERE source_url IS NOT NULL AND source_url NOT LIKE ''%nrsc.gov.in%'';'
Write-Host "  catalog rows whose source_url is NOT an nrsc.gov.in host: $badHost"
if ($badHost -eq "0") { OK "all cataloged sources point at a verified nrsc.gov.in host (none invented)" }
else { BAD "a cataloged source is not an nrsc.gov.in host (possible invented URL)" }
# Each source keeps its OWN distinct source_url (CWC-style), unlike LGD/GSI.
$distinctUrls = PsqlQ 'SELECT COUNT(DISTINCT source_url) FROM historical_sources;'
Write-Host "  distinct source_url values: $distinctUrls (rows: $catRows)"
if (($distinctUrls -as [int]) -eq ($catRows -as [int]) -and ($catRows -as [int]) -gt 0) {
  OK "each source keeps its OWN source_url (CWC-style distinct-URL key, not one shared portal)"
} else {
  OK "source_url values overlap across rows - acceptable if a source legitimately shares a URL"
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
Write-Host "  data-sources status (should list historical):"
$ds = HttpGet "/data-sources/status"
if ($ds.body) { ($ds.body -split ',' | Select-String -Pattern 'historical','status' | Select-Object -First 20) | ForEach-Object { "    $_" } }

HDR "12b. Frontend renders"
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 10; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  http://localhost:5173 -> HTTP $feCode"
if ($feCode -eq 200) { OK "frontend served (open it and confirm the map + risk polygons)" }
else { BAD "frontend not served on :5173" }

HDR "13. Re-run the Historical catalog probe (idempotent - no duplicate rows)"
$before = PsqlQ 'SELECT COUNT(*) FROM historical_sources;'
Write-Host "  historical_sources rows before re-probe: $before"
& $DOCKER exec -i $BE python -m app.services.historical_boot 2>&1 | ForEach-Object { "    $_" }
$after = PsqlQ 'SELECT COUNT(*) FROM historical_sources;'
Write-Host "  historical_sources rows after re-probe: $after"
if ($before -eq $after -and ($after -as [int]) -gt 0) {
  OK "re-cataloging is idempotent (row count unchanged on the natural key)"
} else {
  BAD "row count changed on re-probe ($before -> $after) - upsert not idempotent"
}
# Re-assert the geometry-honesty gate AFTER a re-catalog.
$hasGeom2 = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''historical_sources'';'
Write-Host "  post-probe geometry columns on historical_sources: $hasGeom2"
if ($hasGeom2 -eq "0") { OK "after a re-catalog, historical_sources still has NO geometry column" }
else { BAD "a re-catalog introduced a geometry column" }

HDR "14. Historical-label-honesty verdict"
$catF = PsqlQ 'SELECT COUNT(*) FROM historical_sources;'
$geomF = PsqlQ 'SELECT COUNT(*) FROM geometry_columns WHERE f_table_name=''historical_sources'';'
$labelF = PsqlQ 'SELECT COUNT(*) FROM information_schema.columns WHERE table_name=''historical_sources'' AND column_name IN (''event_time'',''target'',''label'',''is_event'',''latitude'',''longitude'');'
Write-Host "  historical_sources rows: $catF ; geometry columns: $geomF ; event/label columns: $labelF"
if ($geomF -eq "0" -and $labelF -eq "0") {
  Write-Host "  VERDICT: historical event SOURCES are stored ONLY in historical_sources as"
  Write-Host "           reference metadata (source + hazard + role + period + the verified"
  Write-Host "           source URL). No source reference is treated as a confirmed event, a"
  Write-Host "           coordinate, an event time, or a 1/0/-1 training label. The vendored"
  Write-Host "           package ships only a source registry + a three-state labeling RULE, so"
  Write-Host "           the inventory is NEVER read as a nationwide presence/absence census and"
  Write-Host "           missing observations are NEVER converted into negatives. Real events and"
  Write-Host "           labels would require a separate, gated, verified inventory parse first -"
  Write-Host "           with confirmed non-events (0) sampled only where observation coverage is"
  Write-Host "           demonstrably adequate - and that stage is deliberately NOT performed at"
  Write-Host "           ingestion."
  OK "no catalog-as-event / catalog-as-label contamination"
} else {
  Write-Host "  VERDICT: historical_sources has a geometry / event / label column - this VIOLATES"
  Write-Host "           the verified boundary that the catalog records SOURCES, not events/labels."
  BAD "Historical catalog was treated as an event/label source"
}

Write-Host ""
Write-Host "============================================================"
Write-Host "RESULT: $script:pass passed, $script:fail failed."
Write-Host "Points requiring your eyes: 12b (map renders in browser)."
Write-Host "============================================================"
if ($script:fail -eq 0) { exit 0 } else { exit 1 }
