param([switch]$DryRun)
$ErrorActionPreference = "Stop"
$ProjectRoot = $PSScriptRoot
$Python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$LogDir = Join-Path $ProjectRoot "logs"
$Code = 1
if (-not (Test-Path -LiteralPath $Python)) { throw "请先运行 setup.ps1。" }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot "config.json"))) { throw "缺少 config.json，请先运行 setup.ps1。" }
[void][System.IO.Directory]::CreateDirectory($LogDir)
$LogFile = Join-Path $LogDir ("run-{0}.log" -f (Get-Date -Format "yyyyMMdd"))
$MarkerFile = Join-Path $LogDir "last-success.txt"
function Write-Log([string]$Message) {
    Add-Content -LiteralPath $LogFile -Value ("{0}  {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message) -Encoding UTF8
}
$Today = Get-Date -Format "yyyy-MM-dd"
if (-not $DryRun -and (Test-Path -LiteralPath $MarkerFile)) {
    if ((Get-Content -LiteralPath $MarkerFile -Raw).Trim() -eq $Today) {
        Write-Log "今天已成功运行，跳过本次。"
        exit 0
    }
}
Write-Log "开始运行；DryRun=$([bool]$DryRun)"
try {
    $StartInfo = New-Object System.Diagnostics.ProcessStartInfo
    $StartInfo.FileName = $Python
    $StartInfo.Arguments = '"' + (Join-Path $ProjectRoot "run.py") + '"'
    if ($DryRun) { $StartInfo.Arguments += " --dry-run" }
    $StartInfo.WorkingDirectory = $ProjectRoot
    $StartInfo.UseShellExecute = $false
    $StartInfo.CreateNoWindow = $true
    $StartInfo.RedirectStandardOutput = $true
    $StartInfo.RedirectStandardError = $true
    $StartInfo.StandardOutputEncoding = [System.Text.Encoding]::UTF8
    $StartInfo.StandardErrorEncoding = [System.Text.Encoding]::UTF8
    $StartInfo.EnvironmentVariables["PYTHONIOENCODING"] = "utf-8"
    $StartInfo.EnvironmentVariables["PYTHONUTF8"] = "1"
    $Process = [System.Diagnostics.Process]::Start($StartInfo)
    try {
        # Both streams must drain concurrently, including large error output.
        $OutTask = $Process.StandardOutput.ReadToEndAsync()
        $ErrTask = $Process.StandardError.ReadToEndAsync()
        $Process.WaitForExit()
        $Code = $Process.ExitCode
        foreach ($Line in (($OutTask.Result + "`n" + $ErrTask.Result) -split "`r?`n")) {
            if ($Line.Trim()) { Write-Log $Line }
        }
    } finally { $Process.Dispose() }
    if ($Code -eq 0 -and -not $DryRun) {
        Set-Content -LiteralPath $MarkerFile -Value $Today -Encoding UTF8
    }
    Write-Log "运行结束 (exit=$Code)"
} catch {
    Write-Log ("启动失败: " + $_.Exception.Message)
    $Code = 1
}
Write-Host "运行结束 (exit=$Code)，日志位于 logs/。"
exit $Code
