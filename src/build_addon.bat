@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1 || call "C:\Program Files (x86)\Microsoft Visual Studio\2022\BuildTools\VC\Auxiliary\Build\vcvars64.bat" >nul 2>&1
set V=D:\git\vcpkg\installed\x64-windows-static
set R=D:\git\reshade-sdk
cl /nologo /std:c++17 /O2 /MT /EHsc /LD /DWIN32_LEAN_AND_MEAN /DNOMINMAX /DImTextureID=ImU64 /D_CRT_SECURE_NO_WARNINGS /I%R%\deps\imgui /I%V%\include /I%R%\include replay_addon.cpp /Fe:sr2022_replay.addon64 /link %V%\lib\minhook.x64.lib user32.lib
