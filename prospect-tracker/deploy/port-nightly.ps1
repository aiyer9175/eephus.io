# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# eephus.io port (Strategy D, owner PORT-R1): the PC-side nightly.
#
# Our Python pipeline stays the single producer on this PC; the box only
# publishes. This script is what deploy/port-nightly-task.xml runs, and it
# keeps the order of deploy/nightly-build.sh on the box:
#   0. the 36-hour bundle heartbeat of the LAST night (report-only: it says
#      whether yesterday's bundle reached the box, it never stops tonight's)
#   1. one-writer guard: no other run_monthly.py or pytest may be running
#   2. the pipeline: run_monthly.py --daily, the FULL monthly on the 1st
#      (or with EEPHUS_FULL=1), skipped with -SkipPipeline
#   3. python build_site.py
#   4. the gate: EEPHUS_DEPLOY_RUN=1 python -m pytest -q; a red suite ships
#      nothing, as on the box (-SkipGate is for a hand run only)
#   5. the served bundle: tools\port_bundle.py --served-bundle <BundleRoot>
#      (verified as it is written; the older bundles beyond -Keep are pruned)
#   6. the ship: tools\port_ship.py --latest <BundleRoot> (verifies again,
#      rsync over the restricted SSH user, READY last), skipped with -NoShip
# Any failing step stops the run with exit 1 and ships nothing.
#
# Registering the scheduled task is the OWNER's act; nothing registers it.
#   Register (from prospect-tracker\, after filling the ship config):
#       Register-ScheduledTask -TaskName EephusPortNightly -Xml (Get-Content -Raw deploy\port-nightly-task.xml)
#   A hand run that builds a bundle but ships nothing:
#       powershell -ExecutionPolicy Bypass -File deploy\port-nightly.ps1 -SkipPipeline -NoShip
#   Remove it:
#       Unregister-ScheduledTask -TaskName EephusPortNightly -Confirm:$false

[CmdletBinding()]
param(
    [string]$BundleRoot = (Join-Path $env:USERPROFILE "eephus\bundles"),
    [string]$Origin = "https://eephus.io",
    [int]$Keep = 2,
    [switch]$SkipPipeline,
    [switch]$SkipGate,
    [switch]$NoShip,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot          # ...\prospect-tracker
Set-Location $Repo

$LogDir = Join-Path $Repo "logs"
New-Item -ItemType Directory -Force $LogDir | Out-Null
$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmssZ")
Start-Transcript -Path (Join-Path $LogDir "port-nightly-$Stamp.log") | Out-Null
Get-ChildItem $LogDir -Filter "port-nightly-*.log" | Sort-Object Name -Descending |
    Select-Object -Skip 30 | Remove-Item -ErrorAction SilentlyContinue

function Invoke-Step([string]$Name, [scriptblock]$Body) {
    Write-Host "--- $Name"
    & $Body
    if ($LASTEXITCODE -ne 0) { throw "$Name exited $LASTEXITCODE" }
}

$code = 0
try {
    Write-Host "=== $(Get-Date -Format o) port nightly start"

    # 0. Yesterday's bundle on the box (report-only).
    & $Python tools\port_live_check.py --heartbeat --origin $Origin
    if ($LASTEXITCODE -ne 0) {
        Write-Host "!!! BUNDLE HEARTBEAT: the box has not received a bundle within 36 hours"
    }

    # 1. One writer at a time.
    $others = Get-CimInstance Win32_Process -Filter "Name='python.exe' OR Name='pythonw.exe'" |
        Where-Object { $_.ProcessId -ne $PID -and $_.CommandLine -match 'run_monthly\.py|pytest' }
    if ($others) {
        throw "another writer is running (pid $($others.ProcessId -join ', ')); nothing built"
    }

    # 2. The pipeline.
    if (-not $SkipPipeline) {
        if ((Get-Date).Day -eq 1 -or $env:EEPHUS_FULL -eq "1") {
            Invoke-Step "FULL monthly pipeline" { & $Python run_monthly.py }
        } else {
            Invoke-Step "daily refresh" { & $Python run_monthly.py --daily }
        }
    } else {
        Write-Host "--- pipeline skipped (-SkipPipeline)"
    }

    # 3. The pages.
    Invoke-Step "build_site" { & $Python build_site.py }

    # 4. The gate.
    if (-not $SkipGate) {
        $env:EEPHUS_DEPLOY_RUN = "1"
        try {
            Invoke-Step "test gate" { & $Python -m pytest -q -p no:cacheprovider }
        } finally {
            Remove-Item Env:EEPHUS_DEPLOY_RUN -ErrorAction SilentlyContinue
        }
    } else {
        Write-Host "!!! test gate skipped (-SkipGate): a hand run only"
    }

    # 5. The served bundle.
    Invoke-Step "served bundle -> $BundleRoot" {
        & $Python tools\port_bundle.py --served-bundle $BundleRoot --keep $Keep
    }

    # 6. The ship.
    if (-not $NoShip) {
        Invoke-Step "ship" { & $Python tools\port_ship.py --latest $BundleRoot }
    } else {
        Write-Host "--- ship skipped (-NoShip)"
    }
    Write-Host "=== $(Get-Date -Format o) port nightly done"
} catch {
    Write-Host "!!! port nightly stopped: $_"
    $code = 1
} finally {
    Stop-Transcript | Out-Null
}
exit $code
