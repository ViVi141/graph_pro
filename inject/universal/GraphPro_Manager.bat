@echo off
chcp 65001 >nul
set "GP_DIR=%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$d=$env:GP_DIR.TrimEnd('\'); [Console]::OutputEncoding=[Text.UTF8Encoding]::new($false); & ([scriptblock]::Create([IO.File]::ReadAllText((Join-Path $d 'GraphPro_Manager.ps1'),[Text.Encoding]::UTF8))) -BaseDir $d"
if errorlevel 1 (
  echo.
  echo [GraphPro] Error occurred. See message above.
  pause
)
