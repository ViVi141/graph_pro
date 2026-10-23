@echo off
rem Launch Arma 3 with the material override mod (glossy hbarrier).
rem Steam must already be running and logged in.
set GAME=D:\SteamLibrary\steamapps\common\Arma 3
if not exist "%GAME%\arma3_x64.exe" (
    echo Game not found: %GAME%
    pause
    exit /b 1
)
start "" "%GAME%\arma3_x64.exe" -skipIntro -noSplash -window -showScriptErrors -mod="%~dp0@gpmat"
exit /b 0
