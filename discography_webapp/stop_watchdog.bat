@echo off
cd /d "%~dp0"
echo Stopping Discography Downloader Watchdog...
echo.

:: Read watchdog PID file
if exist watchdog.pid (
    set /p WPID=<watchdog.pid
    echo Watchdog PID: %WPID%
    taskkill /F /PID %WPID% 2>nul && echo Watchdog stopped.
)

:: Read server PID file
if exist server.pid (
    set /p SPID=<server.pid
    echo Server PID: %SPID%
    taskkill /F /PID %SPID% 2>nul && echo Server stopped.
)

:: Also clean any orphaned Python on port 8000
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do (
    taskkill /F /PID %%a 2>nul
)

echo Done.
pause
