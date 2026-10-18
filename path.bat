@echo off
rem General patcher alias; forwards arguments and exit status to patch.bat.
call "%~dp0patch.bat" %*
exit /b %ERRORLEVEL%
