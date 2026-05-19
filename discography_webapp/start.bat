@echo off
cd /d C:\Users\hyper\workspace\slsk_discography_downloader_script\discography_webapp
echo Starting Discography Downloader...
venv\Scripts\python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000
pause
