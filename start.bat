@echo off
setlocal
cd /d "%~dp0discography_webapp"

if "%PORT%"=="" set PORT=8000
set "PYTHONPATH=%CD%;%~dp0;%PYTHONPATH%"

:: Prefer system Python 3.14 with venv site-packages on Windows to avoid venv stub duplicates
if exist "C:\Python314\python.exe" (
    if exist "venv\Lib\site-packages" (
        set "PYTHONPATH=%CD%\venv\Lib\site-packages;%PYTHONPATH%"
    )
    set "PY_EXE=C:\Python314\python.exe"
) else if exist "venv\Scripts\python.exe" (
    set "PY_EXE=venv\Scripts\python.exe"
) else (
    echo Creating virtual environment...
    python -m venv venv
    set "PY_EXE=venv\Scripts\python.exe"
    echo Installing dependencies...
    "venv\Scripts\python.exe" -m pip install -r requirements.txt
)

echo Starting Discography Downloader on http://0.0.0.0:%PORT% ...
"%PY_EXE%" -m uvicorn main:app --host 0.0.0.0 --port %PORT%

if /I not "%~1"=="--no-pause" if "%CI%"=="" pause
endlocal
