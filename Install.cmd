@echo off
setlocal
powershell.exe -NoLogo -NoProfile -File "%~dp0Install.ps1"
set "INSTALL_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %INSTALL_RESULT%
