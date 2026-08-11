param(
    [string]$PythonVersion = "3.10.11"
)

$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem
$projectRoot = $PSScriptRoot
$releaseRoot = Join-Path $projectRoot "release"
$stageRoot = Join-Path $releaseRoot "NovelTranslatorStudio"
$cacheRoot = Join-Path $releaseRoot "cache"

function Get-RemoteFile {
    param(
        [Parameter(Mandatory = $true)][string]$Uri,
        [Parameter(Mandatory = $true)][string]$Destination
    )
    if ((Test-Path -LiteralPath $Destination) -and (Get-Item -LiteralPath $Destination).Length -gt 0) {
        try {
            $archive = [System.IO.Compression.ZipFile]::OpenRead($Destination)
            $archive.Dispose()
            return
        } catch {
            Remove-Item -LiteralPath $Destination -Force
        }
    }
    $partial = "$Destination.part"
    Remove-Item -LiteralPath $partial -Force -ErrorAction SilentlyContinue
    & curl.exe --fail --location --retry 3 --output $partial $Uri
    if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $partial) -or (Get-Item -LiteralPath $partial).Length -eq 0) {
        throw "Tai file that bai: $Uri"
    }
    try {
        $archive = [System.IO.Compression.ZipFile]::OpenRead($partial)
        $archive.Dispose()
    } catch {
        throw "File tai ve khong phai ZIP hop le: $Uri"
    }
    Move-Item -LiteralPath $partial -Destination $Destination -Force
}
$zipPath = Join-Path $releaseRoot "NovelTranslatorStudio-Windows-x64.zip"

New-Item -ItemType Directory -Force -Path $releaseRoot, $cacheRoot | Out-Null
$resolvedRelease = (Resolve-Path $releaseRoot).Path
if (Test-Path $stageRoot) {
    $resolvedStage = (Resolve-Path $stageRoot).Path
    if (-not $resolvedStage.StartsWith($resolvedRelease + [IO.Path]::DirectorySeparatorChar)) {
        throw "Thu muc build nam ngoai release: $resolvedStage"
    }
    Remove-Item -LiteralPath $resolvedStage -Recurse -Force
}
if (Test-Path $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}
New-Item -ItemType Directory -Force -Path $stageRoot | Out-Null

Copy-Item -LiteralPath (Join-Path $projectRoot "app.py") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "start_app.bat") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "restart_app.ps1") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "apply_update.ps1") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "README_USER.md") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "LICENSE") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "requirements-portable.txt") -Destination $stageRoot
Copy-Item -LiteralPath (Join-Path $projectRoot "VERSION") -Destination $stageRoot
foreach ($folder in @("cloudflare", "cores", "defaults", "split", "web", "up")) {
    Copy-Item -LiteralPath (Join-Path $projectRoot $folder) -Destination $stageRoot -Recurse
}
"{}" | Set-Content -LiteralPath (Join-Path $stageRoot "up\image_cache.json") -Encoding UTF8
New-Item -ItemType Directory -Force -Path (Join-Path $stageRoot "truyen"), (Join-Path $stageRoot ".runtime") | Out-Null
New-Item -ItemType File -Force -Path (Join-Path $stageRoot "apikeys.txt") | Out-Null

$stageResolved = (Resolve-Path $stageRoot).Path
Get-ChildItem -LiteralPath $stageResolved -Directory -Recurse -Filter "__pycache__" | ForEach-Object {
    if (-not $_.FullName.StartsWith($stageResolved + [IO.Path]::DirectorySeparatorChar)) {
        throw "Khong xoa thu muc ngoai goi phat hanh: $($_.FullName)"
    }
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
}
Get-ChildItem -LiteralPath $stageResolved -File -Recurse | Where-Object {
    $_.Extension -in @(".pyc", ".pyo")
} | Remove-Item -Force

$runtimeRoot = Join-Path $stageRoot "runtime"
New-Item -ItemType Directory -Force -Path $runtimeRoot | Out-Null
$pythonZip = Join-Path $cacheRoot "python-$PythonVersion-embed-amd64.zip"
Get-RemoteFile -Uri "https://www.python.org/ftp/python/$PythonVersion/python-$PythonVersion-embed-amd64.zip" -Destination $pythonZip
Expand-Archive -LiteralPath $pythonZip -DestinationPath $runtimeRoot -Force
$pythonMinor = ($PythonVersion.Split('.')[0..1] -join '')
$pthPath = Join-Path $runtimeRoot "python$pythonMinor._pth"
@(
    "python$pythonMinor.zip"
    "."
    ".."
    "Lib"
    "Lib\site-packages"
    "import site"
) | Set-Content -LiteralPath $pthPath -Encoding ASCII

$sitePackages = Join-Path $runtimeRoot "Lib\site-packages"
New-Item -ItemType Directory -Force -Path $sitePackages | Out-Null
$builderPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $builderPython) {
    $builderPython = Join-Path $runtimeRoot "python.exe"
    $getPip = Join-Path $cacheRoot "get-pip.py"
    & curl.exe --fail --location --retry 3 --output $getPip "https://bootstrap.pypa.io/get-pip.py"
    if ($LASTEXITCODE -ne 0) {
        throw "Khong tai duoc get-pip.py"
    }
    & $builderPython $getPip --disable-pip-version-check --no-warn-script-location
    if ($LASTEXITCODE -ne 0) {
        throw "Khoi tao pip that bai"
    }
}
$builderVersion = & $builderPython -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($builderVersion.Trim() -ne "3.10") {
    throw "Can Python 3.10 de build package native. Hien tai: $builderVersion"
}
& $builderPython -m pip install --disable-pip-version-check --no-compile --upgrade --target $sitePackages -r (Join-Path $projectRoot "requirements-portable.txt")
if ($LASTEXITCODE -ne 0) {
    throw "pip install that bai"
}
$generatedJsonPathScript = Join-Path $sitePackages "bin\jp.py"
if (Test-Path -LiteralPath $generatedJsonPathScript) {
    Remove-Item -LiteralPath $generatedJsonPathScript -Force
}

$chromeMetadata = Invoke-RestMethod -Uri "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
$stable = $chromeMetadata.channels.Stable
$chromeUrl = ($stable.downloads.chrome | Where-Object platform -eq "win64").url
$driverUrl = ($stable.downloads.chromedriver | Where-Object platform -eq "win64").url
if (-not $chromeUrl -or -not $driverUrl) {
    throw "Khong tim thay Chrome for Testing win64"
}
$chromeZip = Join-Path $cacheRoot "chrome-$($stable.version)-win64.zip"
$driverZip = Join-Path $cacheRoot "chromedriver-$($stable.version)-win64.zip"
Get-RemoteFile -Uri $chromeUrl -Destination $chromeZip
Get-RemoteFile -Uri $driverUrl -Destination $driverZip
$chromiumRoot = Join-Path $runtimeRoot "chromium"
New-Item -ItemType Directory -Force -Path $chromiumRoot | Out-Null
Expand-Archive -LiteralPath $chromeZip -DestinationPath $chromiumRoot -Force
Expand-Archive -LiteralPath $driverZip -DestinationPath $chromiumRoot -Force

$manifest = @{
    app = "Novel Translator Studio"
    version = (Get-Content -LiteralPath (Join-Path $projectRoot "VERSION") -Raw).Trim()
    python = $PythonVersion
    chrome = $stable.version
    built_at = (Get-Date).ToString("s")
} | ConvertTo-Json
$manifest | Set-Content -LiteralPath (Join-Path $stageRoot "release-manifest.json") -Encoding UTF8

& (Join-Path $runtimeRoot "python.exe") -c "import yaml, selenium, pyperclip, playwright, boto3; from google import genai; print('Portable runtime OK')"
if ($LASTEXITCODE -ne 0) {
    throw "Portable runtime khong import duoc dependency"
}
if (-not (Test-Path (Join-Path $chromiumRoot "chrome-win64\chrome.exe"))) {
    throw "Thieu chrome.exe"
}
if (-not (Test-Path (Join-Path $chromiumRoot "chromedriver-win64\chromedriver.exe"))) {
    throw "Thieu chromedriver.exe"
}
if ((Get-Item (Join-Path $stageRoot "apikeys.txt")).Length -ne 0) {
    throw "apikeys.txt trong goi phai rong"
}
if ((Get-ChildItem -LiteralPath (Join-Path $stageRoot "truyen") -Force | Measure-Object).Count -ne 0) {
    throw "Thu muc truyen trong goi phai rong"
}
$privateHits = Get-ChildItem -LiteralPath $stageRoot -File -Recurse | Where-Object {
    $_.Extension -in @(".py", ".js", ".json", ".md", ".bat", ".ps1")
} | Select-String -SimpleMatch "C:\Users\LENOVO"
if ($privateHits) {
    throw "Goi phat hanh con duong dan rieng cua may build"
}

Compress-Archive -LiteralPath $stageRoot -DestinationPath $zipPath -CompressionLevel Optimal
$zipHash = (Get-FileHash -LiteralPath $zipPath -Algorithm SHA256).Hash.ToLowerInvariant()
$hashPath = "$zipPath.sha256"
"$zipHash  $([IO.Path]::GetFileName($zipPath))" | Set-Content -LiteralPath $hashPath -Encoding ASCII
Write-Host ""
Write-Host "Da tao: $zipPath" -ForegroundColor Green
Write-Host "SHA-256: $hashPath" -ForegroundColor Green
Write-Host "Python: $PythonVersion | Chrome: $($stable.version)"
