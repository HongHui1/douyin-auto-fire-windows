param([string]$PythonCommand = "py")
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
Push-Location $ProjectRoot
try {
    if (-not (Test-Path -LiteralPath $Python)) {
        $LauncherArgs = @()
        if ((Split-Path -Leaf $PythonCommand) -in @("py", "py.exe")) { $LauncherArgs += "-3" }
        & $PythonCommand @LauncherArgs -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -ne 0) { throw "需要可运行的 Python 3.11+；可用 -PythonCommand 指定 python.exe。" }
        & $PythonCommand @LauncherArgs -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "创建虚拟环境失败。" }
    }
    & $Python -m pip install -r requirements.txt
    if ($LASTEXITCODE -ne 0) { throw "安装依赖失败，请检查网络后重试。" }
    & $Python -m playwright install chromium
    if ($LASTEXITCODE -ne 0) { throw "下载 Chromium 失败，请检查网络后重试。" }
    foreach ($Name in @(".env", "config.json")) {
        $Sample = if ($Name -eq ".env") { ".env.example" } else { "config.example.json" }
        if (-not (Test-Path -LiteralPath $Name)) {
            Copy-Item -LiteralPath $Sample -Destination $Name
            Write-Host "已创建 $Name，请填写自己的配置。"
        } else {
            Write-Host "保留已有 $Name。"
        }
    }
    Write-Host "安装完成。先编辑 config.json，再运行 login.ps1 和 run-daily.ps1 -DryRun。" -ForegroundColor Green
} finally { Pop-Location }
