# eephus.io - Windows Task Scheduler entry for the MLB Scores job, on this machine.
#
# WHAT THIS IS FOR. Owner answer SC-JOB (a): the scores job runs on the box, and
# here for checks. On this machine it writes only .cache/scores/ (its output
# under .cache/scores/preview/ while scores_core.SCORES_LIVE is False), never
# anything under data/, and it holds itself (exit 0, action epoch_hold) while
# ..\_pre_epoch_fwar_2026-10\ exists without a step Z entry, so no pause switch
# is needed around the fWAR label epoch.
#
# Registering is the OWNER's act (SCORES_PLAN.md section 17, item 7). No task
# registers it, and nothing here runs until someone passes -Register.
#
# pythonw.exe, because a console window every two minutes is not acceptable on a
# working desktop. -MultipleInstances IgnoreNew, so a slow run is never doubled.
# A 3-minute execution limit: the job bounds itself to 90 seconds plus a start
# jitter of up to 20, and a task killed at the limit leaves no lock behind (the
# job's lock is an OS lock the process releases when it exits).
#
# USAGE (from prospect-tracker\)
#   Register:
#       powershell -ExecutionPolicy Bypass -File deploy\scores-task.ps1 -Register
#   Check what the job would do right now (no call, no write):
#       powershell -ExecutionPolicy Bypass -File deploy\scores-task.ps1 -Why
#   After the first cycle, confirm the scheduler reaches it:
#       python tools\scores_job.py --selfcheck
#   Remove it:
#       powershell -ExecutionPolicy Bypass -File deploy\scores-task.ps1 -Unregister

[CmdletBinding()]
param(
    [switch]$Register,
    [switch]$Unregister,
    [switch]$Why,
    [string]$TaskName = "EephusScores",
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot          # ...\prospect-tracker
$Job  = Join-Path $Repo "tools\scores_job.py"

if (-not (Test-Path $Job)) {
    throw "scores job not found at $Job. Run this from the repo's deploy\ directory."
}

$Py  = (Get-Command $Python).Source
$Pyw = Join-Path (Split-Path $Py) "pythonw.exe"
if (-not (Test-Path $Pyw)) { $Pyw = $Py }

if ($Why) {
    # The gate's opinion only: no network call, and by design NO heartbeat, so a
    # stamp written by a human at a terminal never reports the scheduler alive.
    Push-Location $Repo
    try { & $Py $Job --why } finally { Pop-Location }
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

# EVERY 2 MINUTES, ALL DAY, exactly like the box's cron line: the job decides.
$action = New-ScheduledTaskAction -Execute $Pyw `
    -Argument "`"$Job`" --log-file logs\scores-job.log" -WorkingDirectory $Repo
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).Date `
    -RepetitionInterval (New-TimeSpan -Minutes 2) `
    -RepetitionDuration (New-TimeSpan -Days 3650)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -StartWhenAvailable `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries `
    -ExecutionTimeLimit (New-TimeSpan -Minutes 3)

Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger `
    -Settings $settings -Description ("eephus.io MLB Scores job, no credits. Local mode: " +
    "writes .cache/scores/ in this checkout only and holds itself during the fWAR label epoch.") `
    -Force | Out-Null

Write-Output "registered $TaskName, every 2 minutes"
Write-Output ""
Write-Output "After the first cycle, confirm the scheduler reaches it:"
Write-Output "  python tools\scores_job.py --selfcheck"
Write-Output "It runs only while this machine is awake; the gaps it leaves are honest."
