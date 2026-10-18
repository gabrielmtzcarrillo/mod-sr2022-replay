@echo off
rem Compatibility shortcut for the Replay manifest; GAME_DIR defaults to SR5_DIR.
setlocal EnableExtensions
set "GAME=%~1"
if "%GAME%"=="" set "GAME=%SR5_DIR%"
if "%GAME%"=="" (echo Usage: restore_phone.bat GAME_DIR ^(or set SR5_DIR^) & exit /b 1)
call "%~dp0patch.bat" restore "%~dp0patches\replay.json" "%GAME%"
exit /b %ERRORLEVEL%
