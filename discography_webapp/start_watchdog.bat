@echo off
setlocal
cd /d "%~dp0"

if exist "C:\Python314\python.exe" (
    "C:\Python314\python.exe" "%~dp0launch_watchdog.py" %*
) else if exist "%~dp0venv\Scripts\python.exe" (
    "%~dp0venv\Scripts\python.exe" "%~dp0launch_watchdog.py" %*
) else (
    python "%~dp0launch_watchdog.py" %*
)
endlocal
