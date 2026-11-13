# slsk_discography_downloader_script

A personal tool (v2.3.0, version governed centrally in `VERSION.md`) that builds complete artist discographies from the Soulseek P2P network, driven by MusicBrainz metadata: search Soulseek for an artist's releases, rank and queue candidates, verify lossless spectral integrity, download and tag releases, and organize the results into a local library.

## Status

**Active personal tool.** Last significant activity: **2026-11-12** — v2.3.0: branch/stash reconciliation, credential isolation, persistent memory/DB tracking. The v2.2.0 dashboard consolidation, systray integration, and P2P resilience work landed 2026-11-07.

## Layout

- `discography_webapp/` — FastAPI web application (`http://localhost:8000`, API docs at `/docs`, health probe at `/api/health`):
  - `main.py` — entry point, lifespan handler, WebSocket log broadcaster, UI and compatibility routes
  - `routers/` — modular API routers (`core.py`, `library.py`, `protocol.py`, `agent.py`, `benchmark.py`)
  - `services/` — core engines (`orchestrator.py`, `soulseek.py`, `rust_soulseek.py`, `musicbrainz.py`, `post_processor.py`, `acoustid_service.py`, `config.py`, `queue.py`, `agent.py`, `protocol.py`)
  - `rust_bridge/` — `bob_soulseek_rs` Rust PyO3/maturin crate for concurrent Soulseek P2P search and file transfer
  - `data/` — persistent non-sensitive SQLite/JSON state (`app.db` with 93 managed artists, `mb_cache.db`, `completed_downloads.json`, `artist_blacklist.json`)
  - `templates/`, `static/` — consolidated single-page dashboard UI
  - `watchdog.py`, `launch_watchdog.py`, `systray.py`, `start.bat`, `start_watchdog.bat`, `run_server.sh` — cross-platform and Windows service/watchdog wrappers
- Root scripts & config: `start.bat` (supports `--watchdog` / `--with-filler`), `build_rust.bat` (supports `--no-pause`), `pytest.ini`, `_artist_names.json` (88 curated psytrance artists), `scan_artists.py`, `check_status.py`, `fill_status.py`
- Agent memory & session archives: `.memory/`, `.jules/`, `.pi/`, `discography_webapp/.pi/`, `discography_webapp/.pi-lens/`
- `Dockerfile` + `docker-compose.yml` for containerized deployment
- `tests/` — isolated `pytest` unit and integration test suite (39 unit tests + 3 live-server integration tests)

## Configuration & secrets

Configuration templates are documented in `.env.example`.

- Top-level `.env` contains non-sensitive placeholder defaults only (`your_username` / `your_password`).
- Live credentials (`SLSK_USER`, `SLSK_PASS`, `SLSK_BOOST_USER`, `SLSK_BOOST_PASS`, `GENIUS_API_KEY`) must be stored exclusively in `discography_webapp/.env` (gitignored). `ConfigService` automatically strips secret keys before writing `user_configs` to `discography_webapp/data/app.db`.

## Running

Windows quick start:

```bat
start.bat
:: or launch under the auto-healing watchdog:
start.bat --watchdog
:: rebuild the Rust Soulseek bridge:
build_rust.bat
```

Docker:

```bash
cp .env.example discography_webapp/.env   # fill in Soulseek credentials
docker compose up -d --build
```

Bare metal (Python 3.11–3.14, Rust + maturin, `ffmpeg` and `fpcalc` on PATH):

```bash
pip install -r discography_webapp/requirements.txt
cd discography_webapp/rust_bridge && maturin develop --release && cd ../..
python discography_webapp/main.py
```
