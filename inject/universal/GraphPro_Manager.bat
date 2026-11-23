@echo off
chcp 65001 >nul
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0GraphPro_Manager.ps1"
if errorlevel 1 (
  echo.
  echo [GraphPro] 发生错误，请查看上方提示。
  pause
)
