param([switch]$DryRun)
$ErrorActionPreference = "Stop"
& (Join-Path (Split-Path -Parent $PSScriptRoot) "run-daily.ps1") -DryRun:$DryRun
exit $LASTEXITCODE
