@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\proxy"
cl /nologo /LD /MT /O2 /EHsc d3d11_proxy.cpp /link /DEF:d3d11_proxy.def /OUT:d3d11.dll
