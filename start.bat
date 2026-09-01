@echo off
REM SparBit starten (Windows) - einfach doppelklicken
cd /d "%~dp0"

where py >nul 2>nul
if %errorlevel%==0 (
    py -3 run.py %*
    goto ende
)

where python >nul 2>nul
if %errorlevel%==0 (
    python run.py %*
    goto ende
)

echo.
echo   Python 3.11 oder neuer wird benoetigt.
echo   Holen unter: https://www.python.org/downloads/
echo   Beim Installieren bitte "Add Python to PATH" ankreuzen.
echo.
pause

:ende
if errorlevel 1 pause
