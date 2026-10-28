@echo off
rem Local/private headless DS only. Never start the client from this repo.
if "%ARMA3_DIR%"=="" (
  echo Set ARMA3_DIR to the Arma 3 install directory.
  exit /b 1
)
set "GAME=%ARMA3_DIR%"
set "PROF=%LOCALAPPDATA%\GP_arma_server"
if not exist "%PROF%" mkdir "%PROF%"
cd /d "%GAME%"
arma3server_x64.exe -port=2302 -config="%~dp0server.cfg" -cfg="%~dp0basic.cfg" -profiles="%PROF%" -world=empty -autoInit -name=GPTest -nosound
pause
