$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $PSScriptRoot
$compiler = Join-Path $root 'release\cache\roslyn-4.8.0\tasks\net472\csc.exe'
$wpf = Join-Path $env:WINDIR 'Microsoft.NET\Framework64\v4.0.30319\WPF'
$testExe = Join-Path $root 'release\ReleaseNotesMarkdownTests.exe'
& $compiler /nologo "/out:$testExe" "/r:$wpf\PresentationFramework.dll" "/r:$wpf\PresentationCore.dll" "/r:$wpf\WindowsBase.dll" /r:System.Xaml.dll (Join-Path $root 'launcher-wpf\ReleaseNotesMarkdown.cs') (Join-Path $root 'tests\ReleaseNotesMarkdownTests.cs')
if ($LASTEXITCODE -ne 0) { throw 'Markdown test compilation failed.' }
& $testExe
if ($LASTEXITCODE -ne 0) { throw 'Markdown tests failed.' }
