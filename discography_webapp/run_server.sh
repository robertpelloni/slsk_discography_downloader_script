#!/usr/bin/env bash
# Discography Downloader - Cross-Platform Server Runner
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$DIR"

if command -v python3 >/dev/null 2>&1; then
    PY_CMD="python3"
elif command -v python >/dev/null 2>&1; then
    PY_CMD="python"
elif [ -f "venv/bin/python" ]; then
    PY_CMD="venv/bin/python"
elif [ -f "venv/Scripts/python.exe" ]; then
    PY_CMD="venv/Scripts/python.exe"
else
    echo "Error: Python interpreter not found in PATH or venv."
    return 1 2>/dev/null || exit 1
fi

PORT="${PORT:-8000}"
HOST="${HOST:-0.0.0.0}"
export PYTHONPATH="$DIR:$(dirname "$DIR"):$PYTHONPATH"

while true; do
    echo "[$(date)] Starting server process on http://${HOST}:${PORT}..."
    $PY_CMD main.py
    CODE=$?
    echo "[$(date)] Server exited with code $CODE"
    if [ $CODE -eq 0 ]; then
        echo "Clean exit requested, stopping runner loop."
        break
    fi
    echo "Restarting server in 3 seconds..."
    sleep 3
done
