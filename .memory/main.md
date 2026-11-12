# Discography Downloader

## Project Purpose
Automated Soulseek-based discography downloader with MusicBrainz integration. Downloads complete discographies of psytrance/electronic artists by searching Soulseek (Python `aioslsk` + Rust `bob_soulseek_rs` PyO3 bridge), ranking candidates, auditing lossless spectral quality, downloading, and post-processing (tagging, renaming, cover art).

## Current State (November 12, 2026 — v2.3.0)

### Running & Verified
- **Version**: `2.3.0` (governed centrally in `VERSION.md`; never hardcoded in UI).
- **Web Server** (`discography_webapp/main.py`, FastAPI/uvicorn) — serves consolidated dashboard on `http://127.0.0.1:8000` with `/api/status` and `/api/health` probes.
- **Watchdog** (`discography_webapp/watchdog.py`) — unified `psutil` process manager with multi-retry HTTP health checks, 500 MB RAM-leak auto-restart threshold, PID lock, exponential backoff, crash stderr logging, and opt-in `--with-filler` daemon mode.
- **Persistent State (`discography_webapp/data/`)** — tracked in Git with SQLite WAL mode enabled (`app.db` preserving 93 `managed_artists`, `mb_cache.db`, `completed_downloads.json`, `artist_blacklist.json`).
- **Test & Lint Suite** — `ruff check` passes with 0 errors; `pytest` passes 39 unit tests (3 live-server tests skipped when offline) with `tmp_path` SQLite isolation so test runs never touch live `data/app.db`.

### Key Decisions Made
1. **Strict Credential Isolation**: Live Soulseek and API secrets (`SLSK_PASS`, `SLSK_BOOST_PASS`, `GENIUS_API_KEY`) reside **only** in gitignored `discography_webapp/.env`. `ConfigService` strips secret keys before persisting `user_configs` to `data/app.db` and syncs secret updates back to `discography_webapp/.env`. Root `.env` remains a harmless placeholder template.
2. **Multi-Branch & Stash Reconciliation (v2.3.0)**:
   - Recovered dropped production commit `d7d9c53` (`Protocol #277`: 88-artist `_artist_names.json`, 36 whitelisted psytrance acts including `Eskimo`, `download_playlist` `transfer` fix).
   - Merged `stash@{0}` (`tmp_path` test DB isolation, `max_api_calls=30` cap in `MusicBrainzService.get_related_artists`, cross-platform pure-Python `ProtocolService.extract_roadmap`, SQLite WAL mode).
   - Merged `stash@{2}` (`/api/health`, 24-hour expiring `_CooldownBlacklist`, `QUEUED`/`INITIALIZING` transfer stall detection + `transfer.abort()`, stripped-prefix + exact track-number matching in `PostProcessor`, random port `50000-59999` + Windows TCP `TIME_WAIT` retry in `SoulseekService`).
   - Synchronized `main` and active feature branch `jules-57044827041196387-8ad75250`.
3. **Python 3.14 Windows Execution**: `venv\Scripts\python.exe` on Python 3.14 spawns stub child processes; batch launchers and `watchdog.py` prefer `C:\Python314\python.exe` with `PYTHONPATH` pointing to `discography_webapp\venv\Lib\site-packages` when available, eliminating deprecated `wmic` calls.
4. **Watchdog & Filler Isolation**: Autonomous filler runs in an isolated subprocess (`filler_worker.py`) or opt-in `--with-filler` watchdog mode so heavy scans cannot block FastAPI's event loop.

### Milestones
- **[x]** Consolidated single-page web UI with dark/light theme & tooltips (`v2.2.0`–`v2.3.0`)
- **[x]** Soulseek connection, rate limiting, random port `TIME_WAIT` retry, and Rust P2P bridge
- **[x]** Candidate ranking with format preference & 24-hour peer cooldown blacklisting
- **[x]** MusicBrainz SQLite cache (`mb_cache.db`) with TTL and `max_api_calls=30` depth cap
- **[x]** Neural Sentinel (`ffmpeg` spectral fake-FLAC check) & AcoustID fingerprinting
- **[x]** Ajja FLAC discography run & 93 managed artists persisted in `data/app.db`
- **[x]** Strict `.env` credential isolation (`SLSK_USER=mgaijin` / `SLSK_PASS=[REDACTED_IN_ENV]` stored only in gitignored `discography_webapp/.env`)
- **[x]** Unified `psutil` watchdog with multi-retry health probes and 500 MB RAM guard
- **[x]** Persistent tracking of `.memory/`, `.jules/`, `.pi/`, and non-sensitive databases in Git

## Ajja FLAC Discography Run (Historical Reference)
Completed a full download pass for **Ajja** (MB `6e6e3359-1291-4a71-83d2-181c5ece4acd`) in FLAC only (`preferred_format=flac`, `depth=0`):
- 76 FLAC files (~4.1 GB), 15 of 16 MusicBrainz release groups complete (only missing *Ultrasonic* (2025) track 6 "Time Reactor", unshared in FLAC on Soulseek at run time).
