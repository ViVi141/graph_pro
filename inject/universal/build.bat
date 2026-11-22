@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\universal"
cl /nologo /LD /MT /O2 /EHsc d3d11_universal.cpp /link /DEF:d3d11_universal.def /OUT:d3d11.dll
if errorlevel 1 exit /b 1
echo BUILT universal d3d11.dll OK
