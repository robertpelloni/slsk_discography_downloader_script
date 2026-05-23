@echo off
setlocal
cd /d "%~dp0"
if not exist venv (
    echo Creating virtual environment...
    python -m venv venv
)
echo Installing dependencies...
venv\Scripts\python.exe -m pip install -r requirements.txt

echo Starting Discography Downloader...
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
pause
endlocal
