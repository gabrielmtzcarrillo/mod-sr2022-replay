@echo off
rem Removes the phone "Replay" app: restores data\sr_vanguard\sr_vanguard.vpp_pc to its original bytes
rem (header and size saved by the patch in sr_vanguard.vpp_pc.srpatch.json). Close the game first.
rem
rem Usage: restore_phone.bat [GAME_DIR]
rem   GAME_DIR  folder that contains SaintsRow_DX12.exe (default: %SR5_DIR%)
setlocal EnableExtensions
set "GAME=%~1"
if "%GAME%"=="" set "GAME=%SR5_DIR%"
if "%GAME%"=="" (echo Usage: restore_phone.bat GAME_DIR  ^(or set SR5_DIR^) & exit /b 1)
if not exist "%GAME%\data\sr_vanguard\sr_vanguard.vpp_pc" (echo Not a Saints Row sr5 folder: %GAME% & exit /b 1)
tasklist /fi "imagename eq SaintsRow_DX12.exe" 2>nul | find /i "SaintsRow_DX12.exe" >nul && (echo Close the game first. & exit /b 1)
where uv >nul 2>nul || set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
where uv >nul 2>nul || (echo uv not found. Install it: winget install astral-sh.uv & exit /b 1)
uv run "%~dp0tools\patcher.py" restore "%~dp0patches\replay.json" "%GAME%"
exit /b %ERRORLEVEL%
