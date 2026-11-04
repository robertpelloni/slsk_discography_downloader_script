@echo off
cd /d "%~dp0"
set WATCHDOG_LOG=%~dp0watchdog_main.log

echo [%DATE% %TIME%] Starting watchdog... >> "%WATCHDOG_LOG%"

:: Start the watchdog using wmic (persistent, no console)
wmic process call create "%~dp0venv\Scripts\pythonw.exe %~dp0watchdog.py" >> "%WATCHDOG_LOG%" 2>&1

:: Wait for potential duplicate to appear
%WINDIR%\System32\timeout.exe /t 3 /nobreak >nul 2>&1

:: Find all watchdog PIDs
setlocal enabledelayedexpansion
set FIRST_PID=
set KILL_COUNT=0

for /f "skip=2 tokens=2 delims=," %%a in ('wmic process where "CommandLine like '%%watchdog.py%%' and not CommandLine like '%%bash%%' and not CommandLine like '%%wmic%%'" get ProcessId /format:csv 2^>nul') do (
    if not defined FIRST_PID (
        set FIRST_PID=%%a
    ) else (
        if "%%a" neq "!FIRST_PID!" (
            taskkill /F /PID %%a >nul 2>&1
            set /a KILL_COUNT+=1
            echo [%DATE% %TIME%] Killed duplicate watchdog PID %%a >> "%WATCHDOG_LOG%"
        )
    )
)
endlocal

echo [%DATE% %TIME%] Done. Killed %KILL_COUNT% duplicate(s). >> "%WATCHDOG_LOG%"
