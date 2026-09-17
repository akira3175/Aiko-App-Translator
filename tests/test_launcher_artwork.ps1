param([switch]$Live)
$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compiler = Join-Path $root 'release\cache\roslyn-4.8.0\tasks\net472\csc.exe'
$wpf = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\WPF'
$testExe = Join-Path $root 'release\LauncherArtworkTests.exe'
& $compiler /nologo "/out:$testExe" "/r:$wpf\PresentationCore.dll" "/r:$wpf\WindowsBase.dll" (Join-Path $root 'launcher-wpf\LauncherArtwork.cs') (Join-Path $root 'tests\LauncherArtworkTests.cs')
if ($LASTEXITCODE -ne 0) { throw 'Artwork test compilation failed.' }
$testArgs = @((Join-Path $root 'web\assets\anime\aiko-blue-logo.png'))
if ($Live) { $testArgs += 'live' }
& $testExe @testArgs
if ($LASTEXITCODE -ne 0) { throw 'Artwork tests failed.' }
