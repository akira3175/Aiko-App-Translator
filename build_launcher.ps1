$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$release = Join-Path $root "release"
$project = Join-Path $root "launcher-wpf\AikoLauncher.csproj"
$output = Join-Path $release "Aiko-Launcher.exe"
$msbuild = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe"
$compilerRoot = Join-Path $release "cache\roslyn-4.8.0"
$compiler = Join-Path $compilerRoot "tasks\net472\csc.exe"

New-Item -ItemType Directory -Force -Path $release | Out-Null
if (-not (Test-Path -LiteralPath $compiler)) {
    New-Item -ItemType Directory -Force -Path $compilerRoot | Out-Null
    $package = Join-Path $release "cache\microsoft.net.compilers.toolset.4.8.0.nupkg"
    if (-not (Test-Path -LiteralPath $package)) {
        & curl.exe --fail --location --retry 3 --output $package "https://api.nuget.org/v3-flatcontainer/microsoft.net.compilers.toolset/4.8.0/microsoft.net.compilers.toolset.4.8.0.nupkg"
        if ($LASTEXITCODE -ne 0) { throw "Không tải được Roslyn compiler" }
    }
    $packageZip = "$package.zip"
    Copy-Item -LiteralPath $package -Destination $packageZip -Force
    Expand-Archive -LiteralPath $packageZip -DestinationPath $compilerRoot -Force
    Remove-Item -LiteralPath $packageZip -Force
}
& $msbuild $project /nologo /verbosity:minimal /property:Configuration=Release "/property:CscToolPath=$(Split-Path $compiler)" /property:CscToolExe=csc.exe /target:Rebuild
$built = Join-Path $root "launcher-wpf\bin\Release\Aiko-Launcher.exe"
if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $built)) { throw "Build Aiko Launcher WPF thất bại" }
Copy-Item -LiteralPath $built -Destination $output -Force

& $output --self-test
if ($LASTEXITCODE -ne 0) { throw "Aiko Launcher self-test thất bại: $LASTEXITCODE" }
$hash = (Get-FileHash -LiteralPath $output -Algorithm SHA256).Hash.ToLowerInvariant()
"$hash  $([IO.Path]::GetFileName($output))" | Set-Content -LiteralPath "$output.sha256" -Encoding ASCII
Write-Host "Đã tạo: $output"
Write-Host "SHA-256: $hash"
