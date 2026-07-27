@echo off
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0build_release.ps1"
if errorlevel 1 (
  echo.
  echo Dong goi that bai.
  pause
  exit /b 1
)
echo.
echo Dong goi thanh cong.
pause
