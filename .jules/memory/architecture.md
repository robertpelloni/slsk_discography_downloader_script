# Project Memory: slsk_discography_downloader

## Architecture
- **Backend Framework**: FastAPI (`main.py`) running on Uvicorn. Serves REST API routes (`/api/*`) and handles frontend rendering via Jinja2 (`/`).
- **Orchestration**: The `Orchestrator` class (`services/orchestrator.py`) handles all high-level business logic, integrating metadata fetching, P2P network searching, file queue management, and post-processing tasks.
- **P2P Networking**: Uses `aioslsk` (a Python Soulseek client) via `services/soulseek.py` for connecting and downloading. There is an incomplete "Rust bridge" (`bob_soulseek_rs` in `rust_bridge/`) built with pyo3/tokio intended to replace Python for high-performance concurrent searching.
- **Metadata Management**: `services/musicbrainz.py` wraps `musicbrainzngs` to retrieve artist and release group metadata.
- **Post-Processing**: `services/post_processor.py` tags audio files and fetches cover art using `mutagen`.
- **Frontend**: A single HTML file (`templates/index.html`) using Vanilla JS with an internal polling mechanism for status and websockets for live logs.
- **File System as State**: The application indexes the local library by reading directories (`downloads/Artist/Year - Album`) and falls back to filename regex parsing (`Artist - Year - Album - Track - Title.ext`) for unorganized files.

## Patterns & Decisions
- **Pragmatism & Existing Functionality**: Improvements should preserve existing functionality. Refactoring is only permitted if it explicitly simplifies the code without changing behavior.
- **Configuration & Secrets**: Secrets and configurations should not be hard-coded or logged. They must be managed via `.env` (using `python-dotenv`) and documented in `.env.example`.
- **Dynamic Versioning**: `VERSION.md` serves as the single source of truth for the project's version, wired dynamically into the frontend template instead of hardcoded strings.
- **Single-User Bias**: The application mimics a single-user environment by mocking `USER_ID = 1` and keeping a dictionary of user-specific orchestrators.
- **Circuit Breakers**: The P2P client relies on backoff retries and circuit breakers (aborting sequential downloads if too many consecutive files fail).
- **Documentation**: Hand-off states, roadmap plans, and changelogs are explicitly tracked in root-level markdown files (`HANDOFF.md`, `ROADMAP.md`, `TODO.md`, etc.).

## Known Limitations / Fragile Areas
- `aioslsk` is known to be fragile and slow for large-scale operations, making the Rust bridge a critical path feature.
- File parsing regex patterns are brittle and can fail on complex album titles or unconventional naming schemes.
- Lack of robust unit tests; relying currently on basic syntax verification (`py_compile`).