@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GraphPro_Manager.ps1"
if errorlevel 1 (
  echo.
  echo [GraphPro] Error occurred. See message above.
  pause
)
