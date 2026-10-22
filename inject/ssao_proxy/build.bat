@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\ssao_proxy"
cl /nologo /LD /MT /O2 /EHsc ssao_proxy.cpp /link /DEF:ssao_proxy.def /OUT:GFSDK_SSAO_D3D11.win64.dll
