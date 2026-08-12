# eephus.io - Windows Task Scheduler stopgap for the close odds capture.
#
# WHAT THIS IS FOR, AND WHY IT IS TEMPORARY.
#
# The close capture is designed to run on the production box under cron
# (deploy/betting-crontab.example). It never has: as of 2026-08-12 the odds
# cache held 5 snapshots, every one of them kind="open", and the job had left no
# log anywhere, because nothing ever scheduled it. Meanwhile the only machine
# taking open snapshots was the Windows dev box, which runs run_monthly by hand.
#
# CLV grades an open price against the close for the SAME slate, so the pair has
# to be captured by the SAME machine into the SAME cache. Split the two across
# two boxes and neither ever assembles a gradeable slate. This task exists so
# the dev box can hold both halves until the box cron is installed and verified.
#
# THE OWNER DECISION THIS IMPLEMENTS (2026-08-12): both machines, box primary.
# Install this, confirm the box crontab, then DELETE this task. It is a
# stopgap, not a second home.
#
# DE-DUPE. Each machine keeps its own once-per-slate guard against its own
# cache, so two machines running at once will each capture their own close and
# each spend 3 credits. That is why this task refuses to run unless
# EEPHUS_CLOSE_STOPGAP=1 is set: turning it off is one environment variable, not
# an uninstall. Budget while both run: about 12 credits a day against 500 a
# month, which is affordable for the days it takes to verify the box.
#
# USAGE
#   Register (run as the user who owns the checkout, in an elevated shell):
#       powershell -ExecutionPolicy Bypass -File deploy\betting-close-task.ps1 -Register
#   Check what it would do right now, spending nothing:
#       powershell -ExecutionPolicy Bypass -File deploy\betting-close-task.ps1 -Why
#   Remove it once the box cron is verified:
#       powershell -ExecutionPolicy Bypass -File deploy\betting-close-task.ps1 -Unregister

[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Why,
    [string]$TaskName = "EephusBettingClose",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot          # ...\prospect-tracker
$Job  = Join-Path $Repo "tools\betting_close_job.py"

if (-not (Test-Path $Job)) {
    throw "close job not found at $Job. Run this from the repo's deploy\ directory."
}

function Invoke-Job {
    param([string[]]$JobArgs)
    Push-Location $Repo
    try { & $Python $Job @JobArgs } finally { Pop-Location }
}

if ($Why) {
    # Same inspection the box runbook uses. Spends no credits and, by design,
    # writes NO heartbeat: a stamp written by a human at a terminal would report
    # the scheduler as alive on a machine where it is not installed, which is
    # the one question the heartbeat exists to answer.
    Invoke-Job -JobArgs @("--why")
    return
}

if ($Unregister) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
        Write-Output "removed scheduled task $TaskName"
    } else {
        Write-Output "no scheduled task named $TaskName"
    }
    return
}

if (-not $Register) {
    Write-Output "nothing to do. Pass -Register, -Unregister or -Why."
    return
}

# EVERY 15 MINUTES, ALL DAY, exactly like the cron entry, and for the same
# reason: the job decides. First pitch moves several hours across the calendar,
# so any fixed time is either too early to be a closing line or too late to be
# one at all. decide() does all of its clock reasoning against UTC instants, so
# this task needs no timezone configuration and is correct under any the machine
# happens to have.
$action = New-ScheduledTaskAction -Execute $Python `
    -Argument "`"$Job`"" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 15) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries -StartWhenAvailable `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 10)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description ("eephus.io close odds capture (STOPGAP). " +
    "Delete once the production box crontab is verified. Requires " +
    "EEPHUS_CLOSE_STOPGAP=1 and EEPHUS_ODDS_API_KEY in the machine environment.") `
    -Force | Out-Null

Write-Output "registered $TaskName, every 15 minutes"
Write-Output ""
Write-Output "STILL REQUIRED, or every run is a silent no-op:"
Write-Output "  setx EEPHUS_ODDS_API_KEY <key> /M"
Write-Output "  setx EEPHUS_CLOSE_STOPGAP 1 /M"
Write-Output ""
Write-Output "Then confirm with:"
Write-Output "  powershell -File deploy\betting-close-task.ps1 -Why"
Write-Output ""
Write-Output "Health, which is the evidence that matters (the job exits 0 on"
Write-Output "every legitimate no-op, so its exit code proves nothing):"
Write-Output "  python -c ""import betting_export as be, json; print(json.dumps(be.snapshot_health(14)['diagnosis']))"""
