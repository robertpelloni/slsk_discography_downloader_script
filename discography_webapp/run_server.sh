#!/bin/bash
# Auto-restart server wrapper
while true; do
    echo "[$(date)] Starting server..."
    venv/Scripts/python.exe -m uvicorn main:app --host 0.0.0.0 --port 8000 2>&1 | tee -a /tmp/uvicorn_restart.log
    EXIT_CODE=$?
    echo "[$(date)] Server exited with code $EXIT_CODE"
    if [ $EXIT_CODE -eq 0 ]; then
        echo "Clean exit, not restarting"
        break
    fi
    echo "Restarting in 5 seconds..."
    sleep 5
done
