@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1 || call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set V=D:\git\vcpkg\installed\x64-windows-static
cl /nologo /O2 /MT /EHsc /LD /I%V%\include replay.cpp /Fe:dinput8.dll /link /DEF:dinput8.def %V%\lib\minhook.x64.lib user32.lib
