@echo off
set GAME=D:\SteamLibrary\steamapps\common\Arma 3
set PROF=%USERPROFILE%\Documents\Arma 3
cd /d "%GAME%"
arma3server_x64.exe -port=2302 -config="%~dp0server.cfg" -cfg="%~dp0basic.cfg" -profiles="%PROF%" -world=empty -autoInit -name=GPTest -nosound
pause