# Discography Downloader

## Project Purpose
Automated Soulseek-based discography downloader with MusicBrainz integration. Downloads complete discographies of psytrance/electronic artists by searching Soulseek, ranking candidates, downloading, and post-processing (tagging, renaming, cover art).

## Current State (June 22, 2026)

### Running
- **Watchdog** (`watchdog.py`) — monitors server health every 15s, auto-restarts on crash, captures stderr to `server_crash.log`, exponential backoff on rapid cycling
- **Web Server** (FastAPI/uvicorn) — HTTP 200 on `http://127.0.0.1:8000`
- **Port Registration** — `discography-downloader 8000/tcp` added to `C:\Windows\System32\drivers\etc\services`

### Key Decisions Made
1. **Watchdog architecture**: Python-based, not bash — handles Windows paths properly, does real HTTP health checks (not just port binding)
2. **Process persistence**: Use `wmic process call create` to launch truly independent Windows processes (not `start /B` or `nohup` which die when shell exits)
3. **Crash capture**: Server stderr redirected to `server_crash.log` instead of `DEVNULL` to diagnose crashes
4. **Log noise suppression**: `aioslsk` loggers set to WARNING to suppress ~500+ lines of `ConnectToPeer` and `search reply ticket` noise
5. **Download retries**: 2 retry attempts (3 total) on transient `ConnectionError`/`OSError` in `soulseek.py`'s `download_file()`
6. **Startup dependency check**: `main.py` validates 10 critical modules on startup and exits with clear error if missing
7. **Autonomous filler disabled**: commented out in `main.py` lifespan — triggered via API, not auto-start
8. **Rust bridge disabled**: `bob_soulseek_rs.pyd` causes segfaults — `orchestrator.py` explicitly sets `self.rust_slsk = None`

### Known Issues
1. **Server crash cycle**: Server dies ~5-8 min after autonomous filler triggers. Crash at `Fetching releases for <artist>...` with no Python traceback. Possible causes: stack overflow from `depth=2` recursion in `get_related_artists`, or orphan `asyncio.to_thread` threads accumulating after timeout cancellations.
2. **Soulseek credentials set**: `.env` has `SLSK_USER=mgaijin` / `SLSK_PASS=korn5984` but not tested with actual download job
3. **51 albums already downloaded** from previous sessions — some have "Unmatched file" post-processing issues
4. **`.env` has real credentials** — should not be committed to git

### Milestones
- **[x]** Basic web UI with dark/light theme
- **[x]** Soulseek connection and search
- **[x]** Candidate ranking with format preference
- **[x]** Sequential download with circuit breaker
- **[x]** MusicBrainz metadata tagging (post-processing)
- **[x]** Cover art download
- **[x]** 51 albums downloaded successfully
- **[x]** Autonomous filler for unattended collection building
- **[x]** Startup dependency check
- **[x]** Log noise suppression
- **[x]** Download retry logic
- **[x]** Watchdog with health checks
- **[x]** Crash log capture
- **[x]** Exponential backoff on rapid restarts
- **[x]** Port registration in Windows services config
- **[ ]** Fix server crash during autonomous filler scan
- **[ ]]** Test actual Soulseek download with real credentials
- **[ ]]** Add `.env` to `.gitignore` (contains credentials)
- **[ ]]** Limit related artist depth or cap to prevent explosion

### Architecture Overview
- `discography_webapp/` — FastAPI web application
  - `main.py` — App entry, lifespan, dependency check, route registration
  - `services/`
    - `soulseek.py` — Soulseek client wrapper (connect, search, download with retry)
    - `musicbrainz.py` — MusicBrainz API wrapper (artist search, discography, related artists)
    - `orchestrator.py` — Core download engine (scan, rank candidates, download, post-process)
    - `post_processor.py` — Tagging, renaming, cover art
    - `logger.py` — WebSocket-connected logging infrastructure
    - `queue.py` — State persistence (completed albums, managed artists)
    - `config.py` — User configuration
  - `routers/` — FastAPI route modules
    - `core.py` — Main API endpoints (status, scan, download, config)
    - `library.py` — Library management
    - `protocol.py` — Autonomous protocol execution
    - `agent.py` — Agent cycle endpoints
    - `benchmark.py` — Performance benchmarks
  - `watchdog.py` — Health monitor and auto-restart
  - `static/` — Frontend assets
  - `templates/` — Jinja2 HTML templates
