param(
    [ValidatePattern('^(?:[01][0-9]|2[0-3]):[0-5][0-9]$')][string]$Time = "21:00",
    [switch]$DryRun,
    [switch]$Remove
)
$ErrorActionPreference = "Stop"
$TaskName = "DouyinAutoFire-Windows-Daily"
if ($Remove) {
    if (Get-ScheduledTask -TaskName $TaskName -ErrorAction SilentlyContinue) {
        Unregister-ScheduledTask -TaskName $TaskName -Confirm:$false
    }
    Write-Host "任务已移除或不存在：$TaskName"
    exit 0
}
$Runner = Join-Path $PSScriptRoot "run-daily.ps1"
if (-not (Test-Path -LiteralPath (Join-Path $PSScriptRoot ".venv\Scripts\python.exe"))) {
    throw "请先运行 setup.ps1、扫码登录并完成 Dry Run。"
}
$Argument = '-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "' + $Runner + '"'
if ($DryRun) { $Argument += " -DryRun" }
$WindowsPowerShell = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
$Action = New-ScheduledTaskAction -Execute $WindowsPowerShell -Argument $Argument -WorkingDirectory $PSScriptRoot
$Trigger = New-ScheduledTaskTrigger -Daily -At $Time
$Settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -WakeToRun -RunOnlyIfNetworkAvailable -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -MultipleInstances IgnoreNew
$Principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $Action -Trigger $Trigger -Settings $Settings -Principal $Principal -Description "抖音续火花 Windows 增强版：本地每日运行" -Force | Out-Null
Write-Host "任务已注册：$TaskName；每天 $Time（电脑本地时间）；DryRun=$([bool]$DryRun)。" -ForegroundColor Green
Write-Host "电脑须开机且当前用户已登录。请勿让两个版本同时使用同一抖音账号。"
