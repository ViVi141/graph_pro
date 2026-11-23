@echo off
rem Build the universal proxy. Location-independent: works from any cwd.
rem VS is looked up in the standard install roots; for custom installs run this
rem from a "Developer Command Prompt for VS".
setlocal
cd /d "%~dp0"

call "%~dp0..\vcvars64_locate.bat"
if errorlevel 1 (
  echo [build] vcvars64.bat not found - install VS C++ tools or run this from a Developer Command Prompt.
  exit /b 1
)
call "%VSW%" >nul
if errorlevel 1 exit /b 1

cl /nologo /LD /MT /O2 /EHsc /utf-8 d3d11_universal.cpp /link /DEF:d3d11_universal.def /OUT:d3d11.dll
if errorlevel 1 exit /b 1

for /f "delims=" %%F in ('powershell -NoProfile -Command "(Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\fxc.exe' | Sort-Object FullName -Descending | Select-Object -First 1).FullName"') do set "FXC=%%F"
if "%FXC%"=="" (
  echo [WARN] fxc.exe not found, skipping HLSL rebuild
  exit /b 0
)

rem tonemap_agx.dxbc lands one directory up on purpose: tools\universal_smoke_test.py
rem reads inject\tonemap_agx.dxbc as its replacement payload. The other nine stay here.
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo ..\tonemap_agx.dxbc       tonemap_agx_punchy.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo tonemap_agx_night.dxbc    tonemap_agx_night.hlsl  || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo bloom_hdr_init.dxbc       bloom_hdr_init.hlsl     || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /D CASCADE_BLEND=1 /Fo sssm_veryhigh.dxbc sssm_soft_contact.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /D CASCADE_BLEND=0 /Fo sssm_high.dxbc     sssm_soft_contact.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo ps_sssm_super_pbr.dxbc ps_sssm_super_pbr.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo tonemap_ssgi.dxbc      tonemap_ssgi.hlsl      || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo rtgi_trace.dxbc        rtgi_trace.hlsl        || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo rtgi_denoise.dxbc      rtgi_denoise.hlsl      || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo tonemap_ultimate.dxbc  tonemap_ultimate.hlsl  || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo ps_sssm_glass_pbr.dxbc   ps_sssm_glass_pbr.hlsl   || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo ps_sssm_treeadv_sss.dxbc ps_sssm_treeadv_sss.hlsl || exit /b 1
echo BUILT universal d3d11.dll + 12 DXBC payloads OK
