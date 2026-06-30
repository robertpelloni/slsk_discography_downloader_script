# Deployment

## Setup Instructions (Docker - Recommended)
1. Copy `.env.example` to `.env` and configure any required secrets.
2. Run `docker compose up -d --build`.
3. The application will be available at http://localhost:8000. Data and downloads will map to the `./data` and `./downloads` folders in your current directory.

## Setup Instructions (Manual)
1. Copy `.env.example` to `.env` and fill in any secrets.
2. Install python dependencies: `pip install -r discography_webapp/requirements.txt`
3. Compile the Rust bridge natively (requires `maturin` and `cargo` installed): `cd discography_webapp/rust_bridge && maturin develop --release`
4. Run the application: `python discography_webapp/main.py`

## Inventory of Major Libraries and Packages
- **FastAPI**: Used for the high-performance async web framework.
- **Uvicorn**: ASGI server to run FastAPI.
- **Jinja2**: Templating engine for rendering `index.html`.
- **musicbrainzngs**: The Python wrapper for the MusicBrainz API, for metadata fetching.
- **mutagen**: Python module to handle audio metadata (ID3 tags, FLAC tags).
- **bob_soulseek_rs**: Custom Rust bridge located in `discography_webapp/rust_bridge` to handle high-performance searches and concurrent downloading natively.

## CI/CD Pipeline (GitHub Actions)
The repository includes a `.github/workflows/ci.yml` and `release.yml` file designed to automate cross-platform deployment.
Whenever a new semantic version tag (e.g., `v2.0.0`) is pushed to the repository:
1. The **Pytest Suite** runs to verify no regressions were introduced.
2. Ruff linter and mypy type checker executes.
3. The **Docker Buildx** multi-platform job executes, compiling the Python environment and the embedded Rust bridge into a production container.
4. The image is automatically pushed to the GitHub Container Registry (`ghcr.io`).

Users can pull the latest autonomous release from GHCR directly into their Docker environments without needing to manually compile the Rust bridge themselves.

## Headless Watchdog and Subprocess execution
For Linux and headless deployment, the application handles event loops using natively supported `asyncio.to_thread` workers for background routines like autonomous downloading and gap-filling. For Windows specifically, we handle Python venv fork restrictions securely using custom `filler_worker.py` and `watchdog.py` subprocesses managed via `.ps1` hooks.
