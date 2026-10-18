@echo off
rem Adds the "Replay" app to the in-game phone (patches data\sr_vanguard\sr_vanguard.vpp_pc, append-only).
rem Undo with restore_phone.bat. Close the game first.
rem
rem Usage: patch_phone.bat [GAME_DIR]
rem   GAME_DIR  folder that contains SaintsRow_DX12.exe (default: %SR5_DIR%)
rem Example: patch_phone.bat "D:\SteamLibrary\steamapps\common\Saints Row\sr5"
setlocal EnableExtensions
set "GAME=%~1"
if "%GAME%"=="" set "GAME=%SR5_DIR%"
if "%GAME%"=="" (echo Usage: patch_phone.bat GAME_DIR  ^(or set SR5_DIR^) & exit /b 1)
if not exist "%GAME%\data\sr_vanguard\sr_vanguard.vpp_pc" (echo Not a Saints Row sr5 folder: %GAME% & exit /b 1)
tasklist /fi "imagename eq SaintsRow_DX12.exe" 2>nul | find /i "SaintsRow_DX12.exe" >nul && (echo Close the game first. & exit /b 1)
where uv >nul 2>nul || set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
where uv >nul 2>nul || (echo uv not found. Install it: winget install astral-sh.uv & exit /b 1)
echo Patching "%GAME%" ...
uv run "%~dp0tools\patcher.py" apply "%~dp0patches\replay.json" "%GAME%"
exit /b %ERRORLEVEL%
