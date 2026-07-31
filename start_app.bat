@echo off
chcp 65001 >nul
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0restart_app.ps1"
if errorlevel 1 (
  echo.
  echo Khong the khoi dong Novel Translator Studio.
  echo Vui long xem thong bao loi phia tren.
  pause
)
