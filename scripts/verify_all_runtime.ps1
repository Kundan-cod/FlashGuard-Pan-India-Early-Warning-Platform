# =============================================================================
# COMBINED runtime verification for ALL 10 verified sources (PowerShell).
# SIH 2026 PS 26192 - Track B (Docker + PostGIS). Native PowerShell (no WSL).
#
#   Run from the repo ROOT in PowerShell (Docker Desktop running):
#     powershell -ExecutionPolicy Bypass -File scripts\verify_all_runtime.ps1
#
#   Flags:
#     -Build      : `docker compose up -d --build` before verifying (rebuild the
#                   backend image so backend/ edits are baked in). Use this after
#                   you change any backend file.
#     -NoStack    : do NOT touch the stack; assume it is already up. (Default
#                   behaviour brings the stack up with `up -d` if it is not
#                   already running, but never rebuilds unless -Build is given.)
#     -SkipTests  : skip the in-container Track-A slice tests (TESTS column shows
#                   'skip'). The runtime/PostGIS evidence is unaffected.
#
# WHAT THIS DOES (and does NOT do)
#   * It ORCHESTRATES the ten existing verify_<src>_runtime.ps1 scripts - it does
#     NOT re-implement or weaken any of their checks. Each child script is run
#     verbatim; its pass/fail counts and exit code are captured as evidence.
#   * It then queries PostGIS directly to build an HONEST summary: the real
#     source_health.status per source, whether numeric data actually landed in a
#     measurement table, whether the source's own table has a PostGIS geometry,
#     and (unless -SkipTests) the Track-A slice-test result run INSIDE the backend
#     container.
#   * A successful adapter IMPORT or a CATALOG/DISCOVERY row is reported in its
#     own column and is NEVER presented as proof of live numeric measurements
#     (requirement 8). DATA TYPE makes the distinction explicit.
#   * It invents NO credentials and NO external responses (requirement 9). A
#     source that is legitimately NOT_CONFIGURED (no token/endpoint) or is
#     CATALOG-ONLY is reported as such and does NOT cause a non-zero exit
#     (requirement 13). Only genuine verification failures do:
#       - backend container not running / not answering
#       - Alembic not at head 0011_ndem_capabilities
#       - the Phase-1 replay pipeline missing (no replay predictions / alerts)
#       - a source in ERROR while it is marked verified:true (a real defect)
#       - any child verify_<src>_runtime.ps1 reporting a failed check
#       - a catalog/discovery table contaminated with a measurement/risk value
#
# NOTE on quoting: every SQL string is a PowerShell SINGLE-quoted literal so
# PowerShell never parses '|', '||', '::' or '(*)' as operators; a literal single
# quote inside SQL is doubled ('').
# =============================================================================

[CmdletBinding()]
param(
  [switch]$Build,
  [switch]$NoStack,
  [switch]$SkipTests
)

$ErrorActionPreference = "Continue"

# --- container / connection settings (fixed by docker-compose.yml) ---
$DB   = "flashguard_db"
$BE   = "flashguard_backend"
$PGU  = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { "flashguard" }
$PGDB = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { "flashguard" }
$API  = "http://localhost:8000"
$COMPOSE = "docker/docker-compose.yml"

# --- resolve paths so the script works no matter the caller's CWD ---
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

$script:gateFail = 0     # genuine verification failures (drive the exit code)
function GATEBAD($m) { Write-Host "  [FAIL] $m" -ForegroundColor Red; $script:gateFail++ }
function GATEOK($m)  { Write-Host "  [PASS] $m" -ForegroundColor Green }
function HDR($m)     { Write-Host ""; Write-Host "==================== $m ====================" -ForegroundColor Cyan }
function SUB($m)     { Write-Host ""; Write-Host "--- $m ---" -ForegroundColor DarkCyan }

# Pick a docker binary that works from PowerShell (WSL integration may be off).
$DOCKER = "docker"
try { docker version *> $null; if ($LASTEXITCODE -ne 0) { $DOCKER = "docker.exe" } }
catch { $DOCKER = "docker.exe" }
Write-Host "[info] using docker binary: $DOCKER"
Write-Host "[info] repo root: $RepoRoot"

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

# ---------------------------------------------------------------------------
# The ten sources, in ingestion order. Each row carries:
#   key      : source_health.source value
#   script   : the existing per-source verify script (REUSED verbatim)
#   adapter  : the collector module (adapter-import probe)
#   type     : honest DATA TYPE label (never implies live numeric unless it is)
#   table    : the source's OWN table in PostGIS
#   geom     : does that table legitimately carry a PostGIS geometry? (y/n)
#   measure  : the measurement table this source must NEVER contaminate ("" if
#              the source has no such downstream table)
#   slice    : the Track-A slice test module (in-container)
# ---------------------------------------------------------------------------
$SOURCES = @(
  @{ key="gpm";        script="verify_gpm_runtime.ps1";        adapter="app.collectors.gpm_collector";        type="Discovery (satellite)";      table="gpm_discovery";      geom="y"; measure="rainfall_observations";      slice="test_gpm_slice" },
  @{ key="smap";       script="verify_smap_runtime.ps1";       adapter="app.collectors.smap_collector";       type="Discovery (satellite)";      table="smap_discovery";     geom="y"; measure="soil_moisture_observations"; slice="test_smap_slice" },
  @{ key="imd";        script="verify_imd_runtime.ps1";        adapter="app.collectors.imd_collector";        type="Live numeric (district)";    table="imd_observations";   geom="n"; measure="rainfall_observations";      slice="test_imd_slice" },
  @{ key="mosdac";     script="verify_mosdac_runtime.ps1";     adapter="app.collectors.mosdac_collector";     type="Discovery (satellite)";      table="mosdac_discovery";   geom="y"; measure="rainfall_observations";      slice="test_mosdac_slice" },
  @{ key="bhuvan";     script="verify_bhuvan_runtime.ps1";     adapter="app.collectors.bhuvan_collector";     type="Catalog (OGC layers)";       table="bhuvan_layers";      geom="n"; measure="terrain_features";          slice="test_bhuvan_slice" },
  @{ key="gsi";        script="verify_gsi_runtime.ps1";        adapter="app.collectors.gsi_collector";        type="Catalog (portal layers)";    table="gsi_layers";         geom="n"; measure="landslide_data";            slice="test_gsi_slice" },
  @{ key="cwc";        script="verify_cwc_runtime.ps1";        adapter="app.collectors.cwc_collector";        type="Catalog (dataset pages)";    table="cwc_resources";      geom="n"; measure="river_observations";        slice="test_cwc_slice" },
  @{ key="lgd";        script="verify_lgd_runtime.ps1";        adapter="app.collectors.lgd_collector";        type="Catalog (directories)";      table="lgd_directory";      geom="n"; measure="";                          slice="test_lgd_slice" },
  @{ key="historical"; script="verify_historical_runtime.ps1"; adapter="app.collectors.historical_collector"; type="Catalog (event sources)";    table="historical_sources"; geom="n"; measure="";                          slice="test_historical_slice" },
  @{ key="ndem";       script="verify_ndem_runtime.ps1";       adapter="app.collectors.ndem_collector";       type="Catalog (capabilities)";     table="ndem_capabilities";  geom="n"; measure="";                          slice="test_ndem_slice" }
)

# =====================================================================
HDR "STEP 0 - Docker PostGIS backend up (start/verify as needed)"
if ($NoStack) {
  Write-Host "  -NoStack: not touching the stack (assuming it is already up)."
} else {
  if ($Build) {
    Write-Host "  -Build: rebuilding + starting the stack (`up -d --build`)..."
    & $DOCKER compose -f $COMPOSE up -d --build 2>&1 | ForEach-Object { "    $_" }
  } else {
    $beStateNow = (& $DOCKER inspect -f '{{.State.Status}}' $BE 2>$null | Out-String).Trim()
    if ($beStateNow -ne "running") {
      Write-Host "  backend not running (state='$beStateNow') -> `up -d`..."
      & $DOCKER compose -f $COMPOSE up -d 2>&1 | ForEach-Object { "    $_" }
    } else {
      Write-Host "  backend already running; not rebuilding (pass -Build to rebuild)."
    }
  }
}

# Wait for the backend to answer /health (migrations + seed_prod run on boot).
Write-Host "  waiting for backend /health (up to ~90s)..."
$hb = 0
for ($i = 0; $i -lt 30; $i++) {
  $hb = (HttpGet "/health").code
  if ($hb -eq 200) { break }
  Start-Sleep -Seconds 3
}
$beState = (& $DOCKER inspect -f '{{.State.Status}}' $BE 2>$null | Out-String).Trim()
Write-Host "  backend container state: $beState ; GET /health -> HTTP $hb"
if ($beState -eq "running") { GATEOK "backend container is running" } else { GATEBAD "backend container not running (state='$beState')" }
if ($hb -eq 200) { GATEOK "backend answering on :8000" } else { GATEBAD "backend NOT answering on :8000 (cannot verify further)" }

# If the backend is unreachable there is nothing left to check honestly.
if ($hb -ne 200) {
  Write-Host ""
  Write-Host "ABORT: backend is not answering; bring the stack up and re-run." -ForegroundColor Red
  Write-Host "  Try:  $DOCKER compose -f $COMPOSE up -d --build" -ForegroundColor Yellow
  exit 1
}

# =====================================================================
HDR "STEP 1 - Alembic reaches head 0011_ndem_capabilities"
$head = (& $DOCKER exec -i $BE alembic -c alembic.ini current 2>$null | Out-String).Trim()
Write-Host "  alembic current: $head"
if ($head -match "0011_ndem_capabilities") { GATEOK "migrations at head 0011_ndem_capabilities (all 11 revisions applied)" }
else { GATEBAD "Alembic NOT at head 0011_ndem_capabilities (got: '$head')" }

# =====================================================================
HDR "STEP 2 - Phase-1 replay pipeline preserved (must NOT be disturbed)"
$preds  = PsqlQ 'SELECT COUNT(*) FROM predictions WHERE mode=''replay'';'
$alerts = PsqlQ 'SELECT COUNT(*) FROM alerts WHERE status=''active'';'
# The demo's SIMULATED marker lives on locations/flood polygons (is_synthetic),
# NOT on predictions. Count the synthetic demo locations that the replay risk
# polygons are built from - that is the honest "SIMULATED" evidence.
$synth  = PsqlQ 'SELECT COUNT(*) FROM locations WHERE is_synthetic=1;'
Write-Host "  replay predictions: $preds ; active alerts: $alerts ; synthetic demo locations: $synth"
if (($preds -as [int]) -gt 0)  { GATEOK "replay predictions present (Phase-1 pipeline intact)" } else { GATEBAD "no replay predictions - Phase-1 pipeline appears broken" }
if (($alerts -as [int]) -gt 0) { GATEOK "active alerts present" } else { GATEBAD "no active alerts - Phase-1 pipeline appears broken" }
$pipelineReplay = if (($preds -as [int]) -gt 0) { "REPLAY" } else { "MISSING" }
$pipelineSim    = if (($synth -as [int]) -gt 0) { "SIMULATED ($synth synthetic demo locations)" } else { "n/a" }

# =====================================================================
HDR "STEP 3 - API contract endpoints answer"
foreach ($ep in @(
    @{p="/health";        n='"status"'},
    @{p="/system/status"; n='"sources"'},
    @{p="/risk";          n='"risks"'},
    @{p="/risk/map";      n='FeatureCollection'},
    @{p="/alerts";        n='"alerts"'})) {
  $r = HttpGet $ep.p
  if ($r.code -eq 200 -and $r.body -match [regex]::Escape($ep.n)) { GATEOK "GET $($ep.p)" }
  else { GATEBAD "GET $($ep.p) (HTTP $($r.code) / needle '$($ep.n)' not found)" }
}
# Frontend is checked per-source by the child scripts (point 12b); probe it once
# here for the summary, but do NOT gate the data verification on it.
$feCode = 0
try { $fr = Invoke-WebRequest -Uri "http://localhost:5173" -UseBasicParsing -TimeoutSec 8; $feCode = [int]$fr.StatusCode } catch { $feCode = 0 }
Write-Host "  frontend http://localhost:5173 -> HTTP $feCode (informational; not a data gate)"

# =====================================================================
HDR "STEP 4 - Run each source's existing verify_<src>_runtime.ps1 (reused verbatim)"
# We invoke the child scripts EXACTLY as-is (requirement 2/3). Each already runs
# its own honesty gate and exits non-zero on any failed check. We capture the
# tail "RESULT: P passed, F failed." plus the exit code for the summary and to
# aggregate genuine failures.
$childResults = @{}
foreach ($s in $SOURCES) {
  $path = Join-Path $ScriptDir $s.script
  SUB "$($s.key)  ($($s.script))"
  if (-not (Test-Path $path)) {
    Write-Host "  [FAIL] child script missing: $path" -ForegroundColor Red
    $childResults[$s.key] = @{ pass=0; fail=1; exit=127; ran=$false }
    $script:gateFail++
    continue
  }
  $out = & powershell -ExecutionPolicy Bypass -NoProfile -File $path 2>&1
  $childExit = $LASTEXITCODE
  $out | ForEach-Object { "      $_" }
  $p = 0; $f = 0
  $m = ($out | Select-String -Pattern 'RESULT:\s+(\d+)\s+passed,\s+(\d+)\s+failed' | Select-Object -Last 1)
  if ($m) { $p = [int]$m.Matches[0].Groups[1].Value; $f = [int]$m.Matches[0].Groups[2].Value }

  # Each child asserts that ITS OWN migration is the current Alembic head (e.g.
  # gpm expects head=0002_gpm_discovery). That assertion is only true when the
  # child is run standalone at that revision. In the FULL stack every migration
  # is applied, so the head is 0011_ndem_capabilities and every OTHER child's
  # point-2 reports "<rev> not at head". That is EXPECTED here, not a defect:
  # STEP 1 of THIS script is the authoritative head gate, and each child's own
  # table is confirmed to exist by its own point-3. We do NOT modify or weaken
  # the child check (requirement 3); we simply recognise this one line for what
  # it is. A child is only discounted when its ONLY failing line is a
  # "<rev> not at head" line - ANY other [FAIL] still counts as a genuine defect.
  $failLines   = @($out | Select-String -Pattern '\[FAIL\]' | ForEach-Object { $_.Line })
  $nonMigFails = @($failLines | Where-Object { $_ -notmatch 'not at head' })
  $migHeadOnly = ($failLines.Count -gt 0) -and ($nonMigFails.Count -eq 0)

  $childResults[$s.key] = @{ pass=$p; fail=$f; exit=$childExit; ran=$true; migHeadOnly=$migHeadOnly }
  if ($childExit -eq 0 -and $f -eq 0) {
    Write-Host "  [child PASS] $($s.key): $p passed, $f failed (exit $childExit)" -ForegroundColor Green
  } elseif ($migHeadOnly) {
    Write-Host "  [child PASS*] $($s.key): $p passed, $f failed - the ONLY failure is the standalone '<rev> not at head' check, which is EXPECTED in the combined stack (all 11 migrations applied; STEP 1 confirms head=0011). NOT a genuine failure." -ForegroundColor Yellow
  } else {
    Write-Host "  [child FAIL] $($s.key): $p passed, $f failed (exit $childExit) - $($nonMigFails.Count) genuine failing check(s)" -ForegroundColor Red
    $script:gateFail++
  }
}

# =====================================================================
HDR "STEP 5 - Authoritative per-source runtime evidence (direct PostGIS query)"
# This is the honest layer that feeds the summary table. It re-reads
# source_health.status, the actual row count in the source's OWN table, whether
# that table carries a PostGIS geometry, and (critically) whether any downstream
# MEASUREMENT table has been contaminated by this source. Adapter import and
# catalog/discovery rows are NOT treated as live numeric data (requirement 8).
$rows = @()
foreach ($s in $SOURCES) {
  # 5a. adapter import probe (evidence only; never proof of live data).
  $imp = (& $DOCKER exec -i $BE python -c "import $($s.adapter); print('OK')" 2>$null | Out-String).Trim()
  $adapter = if ($imp -match "OK") { "import OK" } else { "IMPORT FAIL" }
  if ($adapter -eq "IMPORT FAIL") { GATEBAD "$($s.key): adapter $($s.adapter) failed to import" }

  # 5b. honest runtime status from source_health.
  $status = PsqlQ "SELECT status FROM source_health WHERE source='$($s.key)';"
  if (-not $status) { $status = "ABSENT" }

  # 5c. rows in the source's OWN table (catalog/discovery/observation).
  $ownRows = PsqlQ "SELECT COUNT(*) FROM $($s.table);"

  # 5d. does the own table carry a PostGIS geometry, and is that legitimate?
  $geomCols = PsqlQ "SELECT COUNT(*) FROM geometry_columns WHERE f_table_name='$($s.table)';"
  $geomOk = $true
  if ($s.geom -eq "y" -and ($geomCols -as [int]) -lt 1) { $geomOk = $false; GATEBAD "$($s.key): $($s.table) expected a PostGIS geometry but has none" }
  if ($s.geom -eq "n" -and ($geomCols -as [int]) -gt 0) { $geomOk = $false; GATEBAD "$($s.key): $($s.table) must NOT carry a geometry (catalog/observation), found one" }
  $postgis = "$($s.table)=$ownRows rows; geom=$geomCols"

  # 5e. HONESTY GATE: this source must not have leaked into a measurement table.
  $leak = ""
  if ($s.measure -ne "") {
    $leak = PsqlQ "SELECT COUNT(*) FROM $($s.measure) WHERE source='$($s.key)';"
    # A leak is only a genuine failure for DISCOVERY/CATALOG sources, which have
    # no verified numeric-parse stage. IMD is a live-numeric source but writes to
    # its OWN imd_observations table, so ANY imd row in rainfall_observations is a
    # leak too (district figure masquerading as a village value).
    if (($leak -as [int]) -gt 0) {
      GATEBAD "$($s.key): $leak row(s) leaked into measurement table $($s.measure) - no verified numeric-parse stage exists"
    }
  }

  # 5f. classify the runtime result honestly.
  $cls = switch -Regex ($status) {
    "^LIVE$"           { "live/reachable (catalog built)"; break }
    "^NRT$"            { "live/reachable (discovery)";     break }
    "^STALE$"          { "reachable-probe-failed (rows written)"; break }
    "^NOT_CONFIGURED$" { "not configured (no creds/endpoint)"; break }
    "^ERROR$"          { "configured but FAILED";          break }
    "^ABSENT$"         { "no health row (probe did not run)"; break }
    default            { $status }
  }
  # An ERROR while verified:true is a genuine defect; ERROR checks live in the
  # child scripts, but reflect it in the gate too.
  if ($status -eq "ERROR")  { GATEBAD "$($s.key): source_health=ERROR (verified source should not be in ERROR)" }
  if ($status -eq "ABSENT") { GATEBAD "$($s.key): no source_health row (boot probe did not run)" }

  # 5g. in-container Track-A slice test (isolated temp SQLite; proves adapter
  #     logic, NOT live data). Uses the same _util bootstrap the suite uses.
  $tests = "skip"
  if (-not $SkipTests) {
    $tout = (& $DOCKER exec -i $BE sh -c "cd /app && python tests/$($s.slice).py 2>&1 | tail -3" 2>$null | Out-String)
    if ($tout -match "\bOK\b") { $tests = "pass" }
    elseif ($tout -match "FAILED|Error|Traceback") { $tests = "FAIL"; GATEBAD "$($s.key): slice test $($s.slice) failed in container" }
    else { $tests = "?" }
  }

  $rows += [pscustomobject]@{
    Source  = $s.key
    Adapter = $adapter
    Runtime = $status
    DataType= $s.type
    PostGIS = $postgis
    Leak    = $(if ($s.measure -eq "") { "-" } else { "$($s.measure):$leak" })
    Tests   = $tests
    Class   = $cls
  }
}

# =====================================================================
HDR "STEP 6 - SUMMARY TABLE"
$fmt = "{0,-11} | {1,-11} | {2,-15} | {3,-24} | {4,-34} | {5,-6} | {6}"
Write-Host ($fmt -f "SOURCE","ADAPTER","RUNTIME RESULT","DATA TYPE","POSTGIS","TESTS","STATUS")
Write-Host ("-" * 130)
foreach ($r in $rows) {
  $verdict = "OK"
  $cr = $childResults[$r.Source]
  # A child whose ONLY failing line is the standalone "<rev> not at head" check is
  # OK in the combined stack (see STEP 4 note); only genuine failing checks flip it.
  if ($cr -and ($cr.fail -gt 0 -or $cr.exit -ne 0) -and -not $cr.migHeadOnly) { $verdict = "CHECK-FAILED" }
  if ($r.Adapter -eq "IMPORT FAIL") { $verdict = "ADAPTER-FAIL" }
  if ($r.Runtime -eq "ERROR")   { $verdict = "SOURCE-ERROR" }
  if ($r.Runtime -eq "ABSENT")  { $verdict = "NO-PROBE" }
  if ($r.Tests   -eq "FAIL")    { $verdict = "TEST-FAIL" }
  $line = ($fmt -f $r.Source, $r.Adapter, $r.Runtime, $r.DataType, $r.PostGIS, $r.Tests, $verdict)
  if ($verdict -eq "OK") { Write-Host $line } else { Write-Host $line -ForegroundColor Red }
}
Write-Host ("-" * 130)
Write-Host "PIPELINE  | replay=$pipelineReplay ; simulated=$pipelineSim ; frontend HTTP=$feCode"
Write-Host ""
Write-Host "Legend - RUNTIME RESULT is the honest source_health.status:" -ForegroundColor DarkGray
Write-Host "  LIVE  = catalog built from a verified public portal (no creds needed)"       -ForegroundColor DarkGray
Write-Host "  NRT   = near-real-time discovery ran (metadata only, NO numeric value)"      -ForegroundColor DarkGray
Write-Host "  STALE = catalog written but an optional reachability probe failed"           -ForegroundColor DarkGray
Write-Host "  NOT_CONFIGURED = no token/endpoint supplied (legitimate; not a failure)"     -ForegroundColor DarkGray
Write-Host "  ERROR = marked verified but the run failed (a genuine defect)"               -ForegroundColor DarkGray
Write-Host "  REPLAY / SIMULATED = Phase-1 pipeline state (see PIPELINE row), not a source" -ForegroundColor DarkGray

# =====================================================================
HDR "STEP 7 - Honest classification of the 10 sources"
function ListWhere($pred, $label, $color) {
  $hit = @($rows | Where-Object { & $pred $_ } | ForEach-Object { $_.Source })
  Write-Host ("  {0}: {1}" -f $label, ($(if ($hit.Count) { $hit -join ", " } else { "(none)" }))) -ForegroundColor $color
}
ListWhere { param($r) $r.Runtime -in @("LIVE","NRT") -and $r.Runtime -ne "STALE" } "Actually live / reachable        " "Green"
ListWhere { param($r) $r.Runtime -eq "STALE" }                                     "Reachable-probe FAILED (rows kept)" "Yellow"
ListWhere { param($r) $r.Runtime -eq "ERROR" }                                     "Configured but FAILED (defect)   " "Red"
ListWhere { param($r) $r.Runtime -eq "NOT_CONFIGURED" }                            "Not configured (no creds)        " "Gray"
ListWhere { param($r) $r.DataType -like "Catalog*" }                               "Catalog-only (no measurements)   " "Cyan"
ListWhere { param($r) $r.DataType -like "Discovery*" }                             "Discovery-only (metadata only)   " "Cyan"
ListWhere { param($r) $r.DataType -like "Live numeric*" }                          "Live numeric (own table only)    " "Cyan"
Write-Host "  Pipeline data: REPLAY + SIMULATED (is_synthetic) - see PIPELINE row." -ForegroundColor Cyan

# =====================================================================
HDR "FINAL VERDICT"
# Hashtable values are not PSObjects, so Measure-Object -Property can't see their
# keys in PS 5.1; sum explicitly. Count the standalone "<rev> not at head" line
# separately so the total is honest about what is (and isn't) a real failure.
$totalChildPass = 0; $totalChildFail = 0; $totalMigHeadOnly = 0
foreach ($cr in $childResults.Values) {
  $totalChildPass += [int]$cr.pass
  $totalChildFail += [int]$cr.fail
  if ($cr.migHeadOnly) { $totalMigHeadOnly += [int]$cr.fail }
}
$genuineChildFail = $totalChildFail - $totalMigHeadOnly
Write-Host "  child-script checks: $totalChildPass passed, $totalChildFail failed across 10 scripts"
Write-Host "  of those failures, $totalMigHeadOnly are the standalone '<rev> not at head' check (EXPECTED in the combined stack; STEP 1 is the authoritative head gate)"
Write-Host "  genuine child-check failures: $genuineChildFail"
Write-Host "  combined-gate genuine failures: $script:gateFail"
Write-Host ""
if ($script:gateFail -eq 0) {
  Write-Host "RESULT: PASS - all 10 sources verified honestly; Phase-1 replay preserved;" -ForegroundColor Green
  Write-Host "        Alembic at 0011_ndem_capabilities; no catalog/discovery contamination." -ForegroundColor Green
  Write-Host "        (NOT_CONFIGURED / catalog-only / discovery-only are expected, not failures.)" -ForegroundColor Green
  exit 0
} else {
  Write-Host "RESULT: FAIL - $script:gateFail genuine verification failure(s) above." -ForegroundColor Red
  Write-Host "        A source being NOT_CONFIGURED or catalog-only is NOT counted here;" -ForegroundColor Red
  Write-Host "        these are real defects (backend/migration/pipeline/leak/ERROR/test)." -ForegroundColor Red
  exit 1
}
