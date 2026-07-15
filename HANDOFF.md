# Handoff — Session 2026-07-12/13

## Completed Work

### 1. MusicBrainz SQLite Cache

Added persistent caching for all MusicBrainz API calls in `services/musicbrainz.py`:

- Artist search: 30 days TTL
- Artist details: 30 days TTL
- Discography: 7 days TTL
- Related artists: 14 days TTL
- Cache stored in `data/mb_cache.db` (SQLite with WAL mode)
- Cache stats logged at scan start and filler end
- API endpoints: `GET /api/mb_cache_stats`, `POST /api/mb_cache_cleanup`

### 2. Soulseek Connection Fix

Fixed the root cause of 238,642 "not sending message" errors:

- `ConnectionState` was being imported from `aioslsk.events` (wrong) — changed to `aioslsk.network.connection`
- Added real connection state detection via `server_manager.connection_state`
- Added rate limiting: max 5 searches per 10 seconds
- Added auto-retry: reconnect + retry on dead connection

### 3. Merge Conflict Cleanup

Resolved all remaining merge conflict markers from the jules feature branch merge:

- `services/orchestrator.py` (7 blocks)
- `filler_worker.py` (1 block)
- `VERSION.md` (1 block)
- `HANDOFF.md`, `ROADMAP.md`, `TODO.md`

### 4. Dashboard UI Fix

Fixed merge markers visible in the dashboard by resolving `VERSION.md` conflict.

## Known Issues

- The venv Python 3.14.6 spawns stub processes — always use `C:\Python314\python.exe` with `PYTHONPATH` for subprocesses
- Server gets "listening but not responding HTTP" after extended uptime — likely aioslsk memory leak
- Bash tool intermittently fails with "hypa: command not found" — terminal encoding corruption

## State

- Web server: running on port 8000
- Watchdog: monitoring with 15s interval
- Systray: star icon with activity log
- Filler: active, searches working at 94% success rate (was 2.5%)
- MB cache: ready, will speed up subsequent scans from hours to seconds
