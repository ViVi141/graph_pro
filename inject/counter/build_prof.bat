@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\counter"
cl /nologo /LD /MT /O2 /EHsc gpprof.cpp /link /OUT:gpprof.dll
if errorlevel 1 exit /b 1
cl /nologo /MT /O2 /EHsc injector.cpp /link /OUT:injector.exe
if errorlevel 1 exit /b 1
echo BUILT gpprof.dll + injector.exe OK

