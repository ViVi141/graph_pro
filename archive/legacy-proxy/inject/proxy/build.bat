@echo off
rem Build the d3d11 proxy. Location-independent: works from any cwd.
rem /utf-8 because the source is UTF-8 (comments + a few log strings use U+2014/U+2248);
rem without it MSVC decodes the file as the ANSI code page and mangles those bytes.
setlocal
call "%~dp0..\vcvars64_locate.bat"
if errorlevel 1 (
  echo [build] vcvars64.bat not found - open a "Developer Command Prompt for VS" and run this script there.
  exit /b 1
)
call "%VSW%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /LD /MT /O2 /EHsc /utf-8 d3d11_proxy.cpp /link /DEF:d3d11_proxy.def /OUT:d3d11.dll
