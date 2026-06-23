# Handoff — Session 2026-06-22/23

## Completed Work

### 1. Server Crash Investigation & Fix

The web server was crashing every 5-20 minutes when the autonomous filler triggered. Root cause: `to_thread()`-based MusicBrainz API calls could hang indefinitely (no socket timeout), leaking orphan threads into the thread pool until the event loop froze.

### 2. Thread Safety Improvements

- Added `_run_in_thread()` method with `asyncio.Semaphore(3)` to cap concurrent thread workers
- `get_discography()` and `get_related_artists()` now accept `cancel_event` callbacks for early bail-out on timeout
- Cancel events are set when `wait_for` fires, stopping orphan threads between API calls

### 3. Socket Timeout

- Added `socket.setdefaulttimeout(15)` globally in `services/musicbrainz.py` so every MusicBrainz API call times out after 15s instead of hanging forever

### 4. Filler Subprocess Isolation

- Moved the autonomous filler from `background_tasks.add_task()` (inside the uvicorn event loop) to a detached subprocess (`filler_worker.py`)
- Uses system Python (`C:\Python314\python.exe`) with PYTHONPATH pointing to venv site-packages to avoid the Python 3.14.6 venv stub-process bug
- Added Soulseek service wiring so filler can actually download

### 5. Watchdog Hardening

- Changed `start_server()` to use system Python with PYTHONPATH (avoids venv stub duplicates)
- Added wmic fallback to `kill_process()` for "Access denied" cases from taskkill
- Added PID file lock + named mutex in `main()` to prevent duplicate watchdog instances
- Fixed `sys.stdout` handling for `pythonw.exe` (was None)

### 6. API & UX

- Added 5-minute cooldown to `/api/autonomous_fill` (HTTP 429)
- Fixed frontend fill button to show server response messages in the log panel instead of hiding silently

### 7. Repository Sync

- Fetched and rebased local `main` with `origin/main`
- Resolved merge conflicts preserving both remote infrastructure (blacklist, singles, file_size) and local fixes (thread safety, socket timeout, cancel events)
- Forward-merged feature branch (`jules-13629667631350246499-2bfde27f`) with Rust bridge, library router, batch UI
- Reverse-merged `main` back into feature branch
- Bumped version to 1.4.0 and updated CHANGELOG/ROADMAP

## Known Issues

- The venv Python 3.14.6 (`discography_webapp/venv/Scripts/python.exe`) spawns a stub process on every Popen call, creating duplicate children. Always use `C:\Python314\python.exe` with `PYTHONPATH` set to the venv's `Lib/site-packages` for subprocess launches.
- Server still gets "listening but not responding HTTP" after extended uptime (1h+). Likely a separate issue (memory leak in aioslsk?).
- `filler_worker.py` uses `config.py` and `queue.py` which load from the project directory — ensure working directory is correct when launching.

## State

- Web server: running on port 8000, watchdog PID 51764 monitoring
- Filler subprocess: PID 48648 (if still running)
- `_last_fill_time` cooldown variable is module-level — resets on server restart
