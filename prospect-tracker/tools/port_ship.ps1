# Copyright (C) 2026 Noah J. Dengler (@ARKNDJL) - All Rights Reserved
# Unauthorized copying of this file, via any medium is strictly prohibited
# Proprietary and confidential
# Written by Noah J. Dengler (@ARKNDJL), 2026
#
# eephus.io port (Strategy D): ship a verified served bundle to the box.
#
# A thin wrapper around tools\port_ship.py, which verifies the bundle, runs the
# two rsync calls over the restricted SSH user (READY last) and records the
# ship. Connection settings come from the local config file the owner fills
# (EEPHUS_PORT_SHIP_CONF, else %USERPROFILE%\.eephus\port_ship.conf; template
# deploy\port_ship.conf.example), never from this repository.
#
# USAGE (from prospect-tracker\)
#   Ship the newest bundle:
#       powershell -ExecutionPolicy Bypass -File tools\port_ship.ps1 -Latest C:\eephus\bundles
#   Ship one bundle:
#       powershell -ExecutionPolicy Bypass -File tools\port_ship.ps1 -Bundle C:\eephus\bundles\<bundle-id>
#   See the commands without running them:
#       powershell -ExecutionPolicy Bypass -File tools\port_ship.ps1 -Latest C:\eephus\bundles -DryRun

[CmdletBinding()]
param(
    [string]$Bundle,
    [string]$Latest,
    [string]$Config,
    [switch]$DryRun,
    [string]$Python = "python"
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot          # ...\prospect-tracker
$Tool = Join-Path $PSScriptRoot "port_ship.py"

$argv = @($Tool)
if ($Bundle) { $argv += @("--bundle", $Bundle) }
elseif ($Latest) { $argv += @("--latest", $Latest) }
else { throw "pass -Bundle <dir> or -Latest <bundle root>" }
if ($Config) { $argv += @("--config", $Config) }
if ($DryRun) { $argv += "--dry-run" }

Push-Location $Repo
try {
    & $Python @argv
    $code = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $code
