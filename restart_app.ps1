$ErrorActionPreference = "Stop"
$appRoot = $PSScriptRoot
$appPath = Join-Path $appRoot "app.py"
$portablePython = Join-Path $appRoot "runtime\python.exe"
$pythonExe = if (Test-Path -LiteralPath $portablePython) { $portablePython } else { "python" }
$appFilePattern = '(^|[\\/"\s])app\.py(["\s]|$)'

$listenerPids = @(
    Get-NetTCPConnection -LocalPort 8765 -State Listen -ErrorAction SilentlyContinue |
        Select-Object -ExpandProperty OwningProcess -Unique
)
$oldServers = @(
    Get-CimInstance Win32_Process | Where-Object {
        $listenerPids -contains $_.ProcessId -and
        $_.Name -eq "python.exe" -and
        $_.CommandLine -match $appFilePattern
    }
)
foreach ($server in $oldServers) {
    Stop-Process -Id $server.ProcessId -Force
}
if ($oldServers.Count -gt 0) {
    Start-Sleep -Milliseconds 500
}

$env:PYTHONUTF8 = "1"
Set-Location -LiteralPath $appRoot
& $pythonExe $appPath
exit $LASTEXITCODE
