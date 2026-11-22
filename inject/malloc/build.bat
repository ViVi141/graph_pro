@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul
cd /d "C:\Users\74738\Desktop\Projects\Arma3\graph_pro\inject\malloc"
cl /nologo /c /MT /O2 /Oi /arch:AVX2 /DMI_STATIC_LIB /Isrc\include src\src\static.c /Fomimalloc_static.obj
if errorlevel 1 exit /b 1
cl /nologo /LD /MT /O2 /Oi /arch:AVX2 /EHsc /Isrc\include gp_mimalloc.cpp mimalloc_static.obj advapi32.lib bcrypt.lib /link /OUT:gp_mimalloc_x64.dll
if errorlevel 1 exit /b 1
echo BUILT gp_mimalloc_x64.dll OK

