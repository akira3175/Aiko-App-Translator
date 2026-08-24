param(
    [Parameter(Mandatory = $true)][string]$ZipPath,
    [Parameter(Mandatory = $true)][string]$AppRoot,
    [Parameter(Mandatory = $true)][string]$ExpectedVersion,
    [Parameter(Mandatory = $true)][int]$ServerPid
)

$ErrorActionPreference = "Stop"
$Host.UI.RawUI.WindowTitle = "Aiko App Translator - Update"
$root = [IO.Path]::GetFullPath($AppRoot).TrimEnd('\')
$runtimeRoot = Join-Path $root ".runtime"
$updatesRoot = Join-Path $runtimeRoot "updates"
$stagingRoot = Join-Path $runtimeRoot "update-staging"
$backupRoot = Join-Path $runtimeRoot "update-backup"
$logPath = Join-Path $runtimeRoot "update.log"
$protected = @(".runtime", "truyen", "data", "apikeys.txt", "r19_words.txt", "r19_word.txt")
$installedNames = @()

function Assert-ChildPath {
    param([string]$Path, [string]$Parent)
    $full = [IO.Path]::GetFullPath($Path)
    $base = [IO.Path]::GetFullPath($Parent).TrimEnd('\') + '\'
    if (-not $full.StartsWith($base, [StringComparison]::OrdinalIgnoreCase)) {
        throw "Update path is outside the safe application area: $full"
    }
    return $full
}

function Remove-SafeTree {
    param([string]$Path, [string]$Parent)
    $safe = Assert-ChildPath $Path $Parent
    if (Test-Path -LiteralPath $safe) {
        Remove-Item -LiteralPath $safe -Recurse -Force
    }
}

function Start-Aiko {
    $python = Join-Path $root "runtime\python.exe"
    $app = Join-Path $root "app.py"
    if (-not (Test-Path -LiteralPath $python) -or -not (Test-Path -LiteralPath $app)) {
        throw "The application files required to start Aiko are missing"
    }
    return Start-Process -FilePath $python -ArgumentList @("`"$app`"") -WorkingDirectory $root -WindowStyle Hidden -PassThru
}

New-Item -ItemType Directory -Force -Path $runtimeRoot, $updatesRoot | Out-Null
$zip = Assert-ChildPath $ZipPath $updatesRoot
"[$(Get-Date -Format s)] Starting update to $ExpectedVersion" | Set-Content -LiteralPath $logPath -Encoding UTF8

try {
    Write-Host "Waiting for Aiko App Translator to close..." -ForegroundColor Cyan
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (-not (Get-Process -Id $ServerPid -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Get-Process -Id $ServerPid -ErrorAction SilentlyContinue) {
        throw "The previous app did not close within 30 seconds"
    }
    Remove-SafeTree $stagingRoot $runtimeRoot
    Remove-SafeTree $backupRoot $runtimeRoot
    New-Item -ItemType Directory -Force -Path $stagingRoot, $backupRoot | Out-Null
    Write-Host "Extracting and validating version $ExpectedVersion..." -ForegroundColor Cyan
    Expand-Archive -LiteralPath $zip -DestinationPath $stagingRoot -Force
    $payload = Join-Path $stagingRoot "NovelTranslatorStudio"
    $payloadVersion = (Get-Content -LiteralPath (Join-Path $payload "VERSION") -Raw).Trim()
    if ($payloadVersion -ne $ExpectedVersion) {
        throw "Extracted version does not match: $payloadVersion"
    }

    $items = @(Get-ChildItem -LiteralPath $payload -Force)
    $legacyLauncher = Join-Path $root "Aiko App Translator.exe"
    if (Test-Path -LiteralPath $legacyLauncher) {
        Get-CimInstance Win32_Process -Filter "Name = 'Aiko App Translator.exe'" -ErrorAction SilentlyContinue | Where-Object {
            $_.ExecutablePath -and [IO.Path]::GetFullPath($_.ExecutablePath) -eq [IO.Path]::GetFullPath($legacyLauncher)
        } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
        Start-Sleep -Milliseconds 300
        $installedNames += "Aiko App Translator.exe"
        Move-Item -LiteralPath $legacyLauncher -Destination (Join-Path $backupRoot "Aiko App Translator.exe") -Force
    }
    Write-Host "Replacing application files. Your personal data will be preserved..." -ForegroundColor Cyan
    foreach ($item in $items) {
        if ($protected -contains $item.Name) { continue }
        $installedNames += $item.Name
        $target = Assert-ChildPath (Join-Path $root $item.Name) $root
        $backup = Assert-ChildPath (Join-Path $backupRoot $item.Name) $backupRoot
        if (Test-Path -LiteralPath $target) {
            Move-Item -LiteralPath $target -Destination $backup -Force
        }
        Move-Item -LiteralPath $item.FullName -Destination $target -Force
    }

    $oldUp = Join-Path $backupRoot "up"
    $newUp = Join-Path $root "up"
    foreach ($name in @("config_md.json", "image_cache.json")) {
        $saved = Join-Path $oldUp $name
        if (Test-Path -LiteralPath $saved) {
            Copy-Item -LiteralPath $saved -Destination (Join-Path $newUp $name) -Force
        }
    }

    $newProcess = Start-Aiko
    Write-Host "Checking the updated application..." -ForegroundColor Cyan
    $healthy = $false
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        Start-Sleep -Milliseconds 500
        try {
            $health = Invoke-RestMethod -Uri "http://127.0.0.1:8765/api/health" -TimeoutSec 2
            if ($health.ok -and $health.version -eq $ExpectedVersion) {
                $healthy = $true
                break
            }
        } catch {}
    }
    if (-not $healthy) {
        if (Get-Process -Id $newProcess.Id -ErrorAction SilentlyContinue) {
            Stop-Process -Id $newProcess.Id -Force
        }
        throw "The updated application did not start or reported the wrong version"
    }
    "[$(Get-Date -Format s)] Update completed successfully: $ExpectedVersion" | Add-Content -LiteralPath $logPath -Encoding UTF8
    Write-Host "Update completed successfully: $ExpectedVersion." -ForegroundColor Green
    Remove-SafeTree $stagingRoot $runtimeRoot
    Remove-Item -LiteralPath $zip -Force -ErrorAction SilentlyContinue
} catch {
    "[$(Get-Date -Format s)] Update failed: $($_.Exception.Message)" | Add-Content -LiteralPath $logPath -Encoding UTF8
    Write-Host "Update failed: $($_.Exception.Message)" -ForegroundColor Red
    Write-Host "Restoring the previous version..." -ForegroundColor Yellow
    try {
        if (Test-Path -LiteralPath $backupRoot) {
            foreach ($name in $installedNames) {
                $installed = Assert-ChildPath (Join-Path $root $name) $root
                if (Test-Path -LiteralPath $installed) {
                    if ((Get-Item -LiteralPath $installed) -is [IO.DirectoryInfo]) {
                        Remove-SafeTree $installed $root
                    } else {
                        Remove-Item -LiteralPath $installed -Force
                    }
                }
            }
            foreach ($backupItem in @(Get-ChildItem -LiteralPath $backupRoot -Force)) {
                $target = Assert-ChildPath (Join-Path $root $backupItem.Name) $root
                Move-Item -LiteralPath $backupItem.FullName -Destination $target -Force
            }
            Start-Aiko | Out-Null
        }
    } catch {
        "[$(Get-Date -Format s)] Rollback failed: $($_.Exception.Message)" | Add-Content -LiteralPath $logPath -Encoding UTF8
        Write-Host "Automatic rollback failed: $($_.Exception.Message)" -ForegroundColor Red
    }
    Start-Sleep -Seconds 8
    exit 1
}
