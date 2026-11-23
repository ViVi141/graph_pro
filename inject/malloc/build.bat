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
cl /nologo /c /MT /O2 /Oi /arch:AVX2 /DMI_STATIC_LIB /Isrc\include src\src\static.c /Fomimalloc_static.obj
if errorlevel 1 exit /b 1
cl /nologo /LD /MT /O2 /Oi /arch:AVX2 /EHsc /Isrc\include gp_mimalloc.cpp mimalloc_static.obj advapi32.lib bcrypt.lib /link /OUT:gp_mimalloc_x64.dll
if errorlevel 1 exit /b 1
echo BUILT gp_mimalloc_x64.dll OK

