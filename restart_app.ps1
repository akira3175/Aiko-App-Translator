$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$appRoot = $PSScriptRoot
$appPath = Join-Path $appRoot "app.py"
$portablePython = Join-Path $appRoot "runtime\python.exe"
$releaseManifest = Join-Path $appRoot "release-manifest.json"
if (-not (Test-Path -LiteralPath $appPath)) {
    Write-Host "LOI: Thieu app.py. Hay giai nen lai TOAN BO goi ZIP truoc khi chay." -ForegroundColor Red
    exit 2
}
if (Test-Path -LiteralPath $portablePython) {
    $pythonExe = $portablePython
} elseif (Test-Path -LiteralPath $releaseManifest) {
    Write-Host @"
LOI: Khong tim thay runtime\python.exe trong ban portable.
Hay giai nen TOAN BO file ZIP vao mot thu muc roi chay start_app.bat.
Neu da giai nen, hay kiem tra Windows Security/antivirus co cach ly python.exe hay khong.
"@
    exit 2
} else {
    $systemPython = Get-Command python -CommandType Application -ErrorAction SilentlyContinue
    if (-not $systemPython) {
        Write-Host "LOI: Khong tim thay Python. Hay cai Python hoac dung ban portable day du." -ForegroundColor Red
        exit 2
    }
    $pythonExe = $systemPython.Source
}
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
