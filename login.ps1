$ErrorActionPreference = "Stop"
$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $Python)) { throw "请先运行 setup.ps1 安装环境。" }
Push-Location $PSScriptRoot
try {
    & $Python "scripts\login.py"
    $Code = $LASTEXITCODE
} finally { Pop-Location }
if ($Code -eq 0) {
    Write-Host "下一步：运行 .\run-daily.ps1 -DryRun，只验证而不发送。" -ForegroundColor Green
} else {
    Write-Host "登录未确认成功，可重新运行 login.ps1。" -ForegroundColor Yellow
}
exit $Code
