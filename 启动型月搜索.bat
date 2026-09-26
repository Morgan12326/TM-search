@echo off
setlocal
title Type-Moon Search
cd /d "%~dp0"

where python >nul 2>&1
if not errorlevel 1 (
    python -m app.server
    set "RC=%ERRORLEVEL%"
    goto :finish
)

where py >nul 2>&1
if not errorlevel 1 (
    py -3 -m app.server
    set "RC=%ERRORLEVEL%"
    goto :finish
)

echo.
echo Python 3 was not found.
echo Install Python 3, then run this file again.
echo.
pause
exit /b 1

:finish
if not "%RC%"=="0" (
    echo.
    echo The search service exited with code %RC%.
    pause
)
exit /b %RC%
