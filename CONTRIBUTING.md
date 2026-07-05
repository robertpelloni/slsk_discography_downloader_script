# Contributing to slsk_discography_downloader_script

Thank you for your interest in contributing to this project!

## Architecture

This project is built on a hybrid architecture:
- **Backend**: Python (FastAPI/AIOHTTP) providing orchestrator services.
- **P2P Bridge**: A high-performance Rust FFI library specifically built to handle slsk packet protocol and state management asynchronously without blocking the Python event loop.
- **Frontend**: A modern UI for batch queuing, viewing logs, and configuration.

## Setup for Development

1. Ensure Python 3.11+ and Cargo/Rustc 1.70+ are installed.
2. Clone the repository and navigate into it.
3. Install Python dependencies:
   ```bash
   pip install -r discography_webapp/requirements.txt
   ```
4. Compile the Rust bridge (requires `maturin`):
   ```bash
   cd discography_webapp/rust_bridge
   maturin develop --release
   ```
5. Run the tests to ensure your environment is set up correctly:
   ```bash
   PYTHONPATH=. pytest tests/
   ```

## Pull Requests

1. **Keep it focused:** PRs should address a single concern (bug, feature, etc.).
2. **Include tests:** If you add new logic (Python or Rust), please include relevant `pytest` integration or unit tests in the `tests/` directory.
3. **Follow the CI:** Ensure that your branch passes the GitHub Actions workflow tests before merging.
