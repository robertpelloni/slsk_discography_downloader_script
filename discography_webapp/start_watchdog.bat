@echo off
cd /d "%~dp0"
echo Starting Watchdog for Discography Downloader...
echo.
echo The watchdog will:
echo   - Start the server if not running
echo   - Monitor port 8000 every 15 seconds
echo   - Restart the server if it crashes or hangs
echo   - Log everything to watchdog.log
echo.
echo Close this window to stop the watchdog.
echo.
echo --- Starting at %date% %time% ---
venv\Scripts\python.exe watchdog.py
echo.
echo Watchdog exited (code %ERRORLEVEL%)
pause
