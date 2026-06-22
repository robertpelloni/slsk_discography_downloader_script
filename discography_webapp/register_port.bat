@echo off
cd /d "%~dp0"
echo Adding Discography Downloader port to Windows services config...
echo.
echo Right-click this file and select "Run as Administrator"
echo.
echo This adds the following entry to C:\Windows\System32\drivers\etc\services:
echo   discography-downloader  8000/tcp  # Discography Downloader Web UI
echo.
pause
echo.
echo Adding entry...
echo. >> C:\Windows\System32\drivers\etc\services
echo discography-downloader  8000/tcp  # Discography Downloader Web UI >> C:\Windows\System32\drivers\etc\services
echo.
if %ERRORLEVEL% equ 0 (
    echo Done! Port 8000 is now registered as "discography-downloader".
) else (
    echo Failed. Make sure you are running as Administrator.
)
pause
