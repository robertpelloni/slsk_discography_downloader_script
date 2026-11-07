@echo off
cd /d "%~dp0"
echo Installing Discography Downloader as a scheduled task...
echo.

set TASK_NAME="DiscographyDownloader"

:: Kill existing task if present
schtasks /delete /tn %TASK_NAME% /f 2>nul

:: Create a scheduled task that:
::  - Runs at user logon
::  - Restarts if it crashes
::  - Runs whether logged in or not
::  - Runs with highest privileges
schtasks /create /tn %TASK_NAME% ^
    /tr "'%~dp0venv\Scripts\python.exe' '%~dp0watchdog.py'" ^
    /sc onlogon ^
    /rl highest ^
    /f ^
    /it

if %ERRORLEVEL% neq 0 (
    echo.
    echo FAILED. Try running as Administrator.
    echo Right-click ^> Run as Administrator
    pause
    exit /b 1
)

echo.
echo Task installed successfully!
echo.
echo It will auto-start on next logon.
echo.
echo To start it right now, run:
echo   schtasks /run /tn %TASK_NAME%
echo.
echo To stop it:
echo   schtasks /end /tn %TASK_NAME%
echo.
echo To remove it:
echo   schtasks /delete /tn %TASK_NAME% /f
pause
