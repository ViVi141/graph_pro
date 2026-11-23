@echo off
rem Location-independent: works from any cwd.
setlocal
call "%~dp0..\vcvars64_locate.bat"
if errorlevel 1 (
  echo [build] vcvars64.bat not found - install VS C++ tools or run this from a Developer Command Prompt.
  exit /b 1
)
call "%VSW%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /LD /MT /O2 /arch:AVX2 /EHsc gp_turbo.cpp /link /OUT:gp_turbo_x64.dll
if errorlevel 1 exit /b 1
echo BUILT gp_turbo_x64.dll OK

