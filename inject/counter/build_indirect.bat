@echo off
call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\counter"
cl /nologo /LD /MT /O2 /EHsc gpindirect.cpp /link /OUT:gpindirect.dll
