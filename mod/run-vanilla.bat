@echo off
rem Baseline run: same launch line as run-gpmat.bat but WITHOUT the mod.
rem Steam must already be running and logged in.
set GAME=D:\SteamLibrary\steamapps\common\Arma 3
if not exist "%GAME%\arma3_x64.exe" (
    echo Game not found: %GAME%
    pause
    exit /b 1
)
start "" "%GAME%\arma3_x64.exe" -skipIntro -noSplash -window -showScriptErrors
exit /b 0
