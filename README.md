# slsk_discography_downloader_script

A personal tool that builds complete artist discographies from the Soulseek
P2P network, driven by MusicBrainz metadata: search Soulseek for an
artist's releases, queue and download them, and organize the results into a
local library. It has actually been used for this — a September 2026 commit
records an "Ajja FLAC discography run".

## Layout

- `discography_webapp/` — the application, a FastAPI web app:
  - `main.py` — entry point; dashboard on `http://localhost:8000`
    (API docs at `/docs`)
  - `routers/`, `services/` — API routes (status, library batch rename,
    agent cycle) and the download/agent services behind them
  - `rust_bridge/` — a Rust crate (built with `maturin`) used for Soulseek
    search/transfer concurrency
  - `templates/`, `static/` — the dashboard UI
  - `systray.py`, `launch_watchdog.py`, and the assorted `.bat`/`.ps1`
    scripts — Windows tray/watchdog/service wrappers
  - `requirements.txt`
- Root helpers: `scan_artists.py`, `check_status.py`, `fill_status.py`,
  `_artist_names.json`
- `Dockerfile` + `docker-compose.yml` for the containerized run
- `tests/` at the root

Configuration is via `.env` (see `.env.example`): Soulseek credentials
(`SLSK_USER`/`SLSK_PASS`, plus an optional second "boost" account), paths,
and toggles for the AcoustID/fake-FLAC checking features. **Note: a real
`.env` file is committed in this repo root** — if those credentials are
live, they are public; rotate them and switch to `.env.example` only.

## Running

Docker:

```bash
cp .env.example .env   # fill in Soulseek credentials
docker compose up -d --build
```

Bare metal (Python 3.11/3.12, Rust + maturin, `ffmpeg` and `fpcalc` on
PATH):

```bash
pip install -r discography_webapp/requirements.txt
cd discography_webapp/rust_bridge && maturin develop --release && cd ../..
python discography_webapp/main.py
```

## Status

Working personal utility, maintained in bursts (created May 2026, runs
recorded through September 2026). The old README's framing — an "autonomous
AI agent framework" with a "Neural Sentinel" — refers to the background
download-scheduling service and the AcoustID up-scaled-FLAC filter in
`services/`; real features, grander names. Soulseek is a third-party P2P
network; you are responsible for what you download with it.
