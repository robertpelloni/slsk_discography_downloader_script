@echo off
cd /d "%~dp0"
:: Hide the console window on startup using VBS wrapper
set VBS=%TEMP%\wd_start.vbs
echo Set WshShell = CreateObject("WScript.Shell") > "%VBS%"
echo WshShell.Run "%~dp0venv\Scripts\python.exe %~dp0watchdog.py", 0, False >> "%VBS%"
echo Set WshShell = Nothing >> "%VBS%"

:: Copy to Startup folder
copy /Y "%VBS%" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\watchdog_launcher.vbs" >nul

:: Also create a .bat launcher in Startup for compatibility
copy /Y "%~dp0start_watchdog.bat" "%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup\watchdog.bat" >nul

echo Installed to Startup folder.
echo Will auto-start on next logon.
echo.
echo Starting now...
start /B "" "%~dp0venv\Scripts\python.exe" "%~dp0watchdog.py"

if %ERRORLEVEL% equ 0 (
    echo Watchdog started.
) else (
    echo Failed to start.
)
pause
