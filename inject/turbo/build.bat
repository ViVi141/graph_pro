@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\turbo"
cl /nologo /LD /MT /O2 /arch:AVX2 /EHsc gp_turbo.cpp /link /OUT:gp_turbo_x64.dll
if errorlevel 1 exit /b 1
echo BUILT gp_turbo_x64.dll OK

