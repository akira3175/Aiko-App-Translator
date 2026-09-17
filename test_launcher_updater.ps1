param([switch]$Live, [string]$ReuseWork = '')
$ErrorActionPreference = 'Stop'
$root = $PSScriptRoot
$compiler = Join-Path $root 'release\cache\roslyn-4.8.0\tasks\net472\csc.exe'
if (-not (Test-Path -LiteralPath $compiler)) { throw 'Run build_launcher.ps1 first.' }
$testRoot = Join-Path $root 'release\launcher-tests'
New-Item -ItemType Directory -Force -Path $testRoot | Out-Null
$executable = Join-Path $testRoot 'LauncherUpdaterTests.exe'
& $compiler /nologo "/out:$executable" /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Web.Extensions.dll (Join-Path $root 'launcher-wpf\PortableUpdater.cs') (Join-Path $root 'tests\LauncherUpdaterTests.cs')
if ($LASTEXITCODE -ne 0) { throw 'Updater test compilation failed.' }
& $executable
if ($LASTEXITCODE -ne 0) { throw 'Updater tests failed.' }
if ($Live) {
    if (Get-NetTCPConnection -LocalPort 18765 -State Listen -ErrorAction SilentlyContinue) { throw 'Test port 18765 is busy.' }
    $controller = Join-Path $testRoot 'LauncherController.cs'
    [IO.File]::WriteAllText($controller, [IO.File]::ReadAllText((Join-Path $root 'launcher-wpf\LauncherController.cs')).Replace('8765', '18765'))
    $liveExe = Join-Path $testRoot 'LauncherUpdaterLiveTests.exe'
    & $compiler /nologo "/out:$liveExe" /r:System.IO.Compression.dll /r:System.IO.Compression.FileSystem.dll /r:System.Web.Extensions.dll /r:Microsoft.CSharp.dll (Join-Path $root 'launcher-wpf\PortableUpdater.cs') $controller (Join-Path $root 'tests\LauncherUpdaterLiveTests.cs')
    if ($LASTEXITCODE -ne 0) { throw 'Live test compilation failed.' }
    $liveWork = Join-Path $testRoot ([Guid]::NewGuid().ToString('N'))
    if ($ReuseWork) {
        $liveWork = [IO.Path]::GetFullPath($ReuseWork)
        if (-not $liveWork.StartsWith($testRoot + '\', [StringComparison]::OrdinalIgnoreCase)) { throw 'ReuseWork must be inside release/launcher-tests.' }
    }
    & $liveExe $liveWork
    if ($LASTEXITCODE -ne 0) { throw 'Live updater test failed.' }
}
