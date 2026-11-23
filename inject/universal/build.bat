@echo off
setlocal
cd /d "%~dp0"
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cl /nologo /LD /MT /O2 /EHsc /utf-8 d3d11_universal.cpp /link /DEF:d3d11_universal.def /OUT:d3d11.dll
if errorlevel 1 exit /b 1

for /f "delims=" %%F in ('powershell -NoProfile -Command "(Get-ChildItem 'C:\Program Files (x86)\Windows Kits\10\bin\*\x64\fxc.exe' | Sort-Object FullName -Descending | Select-Object -First 1).FullName"') do set "FXC=%%F"
if "%FXC%"=="" (
  echo [WARN] fxc.exe not found, skipping HLSL rebuild
  exit /b 0
)

"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo ..\tonemap_agx.dxbc       tonemap_agx_punchy.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo tonemap_agx_night.dxbc    tonemap_agx_night.hlsl  || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo bloom_hdr_init.dxbc       bloom_hdr_init.hlsl     || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /D CASCADE_BLEND=1 /Fo sssm_veryhigh.dxbc sssm_soft_contact.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /D CASCADE_BLEND=0 /Fo sssm_high.dxbc     sssm_soft_contact.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo ps_sssm_super_pbr.dxbc ps_sssm_super_pbr.hlsl || exit /b 1
"%FXC%" /nologo /T ps_5_0 /E main /O2 /Fo tonemap_ssgi.dxbc      tonemap_ssgi.hlsl      || exit /b 1
echo BUILT universal d3d11.dll + 7 DXBC payloads OK
