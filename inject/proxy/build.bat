@echo off
rem Build the d3d11 proxy. Location-independent: works from any cwd.
rem /utf-8 because the source is UTF-8 (comments + a few log strings use U+2014/U+2248);
rem without it MSVC decodes the file as the ANSI code page and mangles those bytes.
setlocal
set "VSW=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VSW%" set "VSW=%ProgramFiles%\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VSW%" set "VSW=%ProgramFiles(x86)%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VSW%" set "VSW=%ProgramFiles%\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat"
if not exist "%VSW%" (
  echo [build] vcvars64.bat not found - open a "Developer Command Prompt for VS 2022" and run this script there.
  exit /b 1
)
call "%VSW%" >nul
if errorlevel 1 exit /b 1
cd /d "%~dp0"
cl /nologo /LD /MT /O2 /EHsc /utf-8 d3d11_proxy.cpp /link /DEF:d3d11_proxy.def /OUT:d3d11.dll
