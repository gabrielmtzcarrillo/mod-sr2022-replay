@echo off
rem Builds the ReShade add-on (sr2022_replay.addon64) from src\replay_addon.cpp.
rem
rem Finds what it needs instead of using fixed paths:
rem   - Visual Studio / Build Tools via vswhere (any version with the C++ x64 toolset)
rem   - MinHook via vcpkg (x64-windows-static), installed on demand
rem   - ReShade SDK headers + Dear ImGui, cloned on demand
rem Output goes to build\ so src\ stays clean.
rem
rem Usage: build.bat [/debug] [/install GAME_DIR] [/vcpkg DIR] [/sdk DIR] [/out DIR]
rem   /install GAME_DIR  copy the add-on into the folder that contains SaintsRow_DX12.exe
rem   /vcpkg DIR         vcpkg checkout   (default: %%VCPKG_ROOT%%, else the folder of vcpkg.exe on PATH)
rem   /sdk DIR           crosire/reshade checkout (default: %%RESHADE_SDK%%, else <repo>\..\reshade-sdk)
rem   /out DIR           output folder    (default: <repo>\build)
rem   /debug             debug build instead of release
rem Example: build.bat /install "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
setlocal EnableExtensions
set "REPO=%~dp0"
if "%REPO:~-1%"=="\" set "REPO=%REPO:~0,-1%"
set "VCPKG=%VCPKG_ROOT%"
set "SDK=%RESHADE_SDK%"
set "OUT=%REPO%\build"
set "INSTALL="
set "OPT=/O2 /MT /DNDEBUG"

:args
if "%~1"=="" goto args_done
if /i "%~1"=="/debug"   (set "OPT=/Od /Zi /MTd /D_DEBUG" & shift & goto args)
if /i "%~1"=="/install" (set "INSTALL=%~2" & shift & shift & goto args)
if /i "%~1"=="/vcpkg"   (set "VCPKG=%~2" & shift & shift & goto args)
if /i "%~1"=="/sdk"     (set "SDK=%~2" & shift & shift & goto args)
if /i "%~1"=="/out"     (set "OUT=%~2" & shift & shift & goto args)
echo Unknown argument: %~1
goto usage
:args_done

rem --- Visual Studio toolchain ---
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" goto no_vs
set "VS="
for /f "usebackq delims=" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "VS=%%i"
if not defined VS goto no_vs
if not exist "%VS%\VC\Auxiliary\Build\vcvars64.bat" goto no_vs

rem --- vcpkg + MinHook ---
if defined VCPKG goto have_vcpkg_var
for /f "delims=" %%i in ('where vcpkg.exe 2^>nul') do if not defined VCPKG set "VCPKG=%%~dpi"
:have_vcpkg_var
if not defined VCPKG goto no_vcpkg
if "%VCPKG:~-1%"=="\" set "VCPKG=%VCPKG:~0,-1%"
if not exist "%VCPKG%\vcpkg.exe" goto no_vcpkg
set "LIBS=%VCPKG%\installed\x64-windows-static"
if exist "%LIBS%\lib\minhook.x64.lib" goto have_minhook
echo Installing minhook:x64-windows-static via vcpkg...
"%VCPKG%\vcpkg.exe" install minhook:x64-windows-static || goto fail
:have_minhook

rem --- ReShade SDK + ImGui ---
if not defined SDK set "SDK=%REPO%\..\reshade-sdk"
if exist "%SDK%\include\reshade.hpp" goto have_sdk
echo Cloning ReShade SDK into %SDK% ...
git clone --depth 1 https://github.com/crosire/reshade.git "%SDK%" || goto fail
:have_sdk
if exist "%SDK%\deps\imgui\imgui.h" goto have_imgui
git -C "%SDK%" submodule update --init --depth 1 deps/imgui || goto fail
:have_imgui

rem --- compile ---
if not exist "%OUT%" mkdir "%OUT%"
call "%VS%\VC\Auxiliary\Build\vcvars64.bat" >nul || goto fail
cl /nologo /std:c++17 %OPT% /EHsc /LD /DWIN32_LEAN_AND_MEAN /DNOMINMAX /DImTextureID=ImU64 /D_CRT_SECURE_NO_WARNINGS ^
  /I"%SDK%\deps\imgui" /I"%SDK%\include" /I"%LIBS%\include" "%REPO%\src\replay_addon.cpp" ^
  /Fo"%OUT%\\" /Fe"%OUT%\sr2022_replay.addon64" ^
  /link /IMPLIB:"%OUT%\sr2022_replay.lib" "%LIBS%\lib\minhook.x64.lib" user32.lib || goto fail
echo Built %OUT%\sr2022_replay.addon64

rem --- optional install ---
if not defined INSTALL goto done
if not exist "%INSTALL%\SaintsRow_DX12.exe" (echo %INSTALL% does not contain SaintsRow_DX12.exe & goto fail)
copy /y "%OUT%\sr2022_replay.addon64" "%INSTALL%\sr2022_replay.addon64" >nul || goto fail
echo Installed to %INSTALL%
:done
endlocal
exit /b 0

:no_vs
echo Visual Studio with the C++ x64 toolset not found. Install VS or Build Tools with "Desktop development with C++".
goto fail
:no_vcpkg
echo vcpkg not found. Use /vcpkg DIR or set VCPKG_ROOT.
goto fail
:usage
echo Usage: build.bat [/debug] [/install GAME_DIR] [/vcpkg DIR] [/sdk DIR] [/out DIR]
:fail
endlocal
exit /b 1
