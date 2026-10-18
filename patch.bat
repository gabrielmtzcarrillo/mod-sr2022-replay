@echo off
rem General manifest patcher: patch.bat prepare^|apply^|status^|restore MANIFEST GAME_DIR
setlocal EnableExtensions
where uv >nul 2>nul || set "PATH=%PATH%;%LOCALAPPDATA%\Microsoft\WinGet\Links"
where uv >nul 2>nul || (echo uv not found. Install it: winget install astral-sh.uv & exit /b 1)
uv run "%~dp0tools\patcher.py" %*
exit /b %ERRORLEVEL%
