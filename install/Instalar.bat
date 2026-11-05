@echo off
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0Instalar-Strata.ps1" %*
set "result=%ERRORLEVEL%"
echo.
pause
exit /b %result%
