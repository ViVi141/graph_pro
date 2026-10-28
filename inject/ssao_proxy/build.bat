@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "%~dp0"
cl /nologo /LD /MT /O2 /EHsc ssao_proxy.cpp /link /DEF:ssao_proxy.def /OUT:GFSDK_SSAO_D3D11.win64.dll
