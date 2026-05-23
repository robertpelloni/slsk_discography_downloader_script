# Changelog

## [0.9.6]
- **Codified AI Protocol**: Integrated the Autonomous AI Development Protocol into the core codebase via `ProtocolService`.
- **System Maintenance UI**: Added a new dashboard panel for triggering repo sync, branch reconciliation, and roadmap extraction.
- **Interactive Library Management**: Fully wired backend rename/delete endpoints to the UI with interactive confirmation dialogs.
- **Robust Path Handling**: Improved virtual environment and path resolution in batch scripts and library organization logic.

## [0.9.5]
- **Pilot Integration Protocol**: Successfully executed pilot integration test verifying health, config, scanning, and managed artist persistence.
- **Security & Safety**: Implemented `is_safe_path` validation for all file-system modifying API endpoints (rename, delete, organize) to prevent path traversal vulnerabilities.
- **Improved Initialization**: Ensured `rust_slsk` is explicitly initialized and handled correctly in `Orchestrator`.
- **Portable Automation**: Updated `start.bat` for automatic venv/dependency management and added `build_rust.bat`.
- **Refined Error Handling**: Improved error reporting in the download loop when no files are saved.

## [0.9.0]
- **Modular Architecture**: Refactored monolithic `main.py` into dedicated FastAPI routers (`core`, `library`).
- **Rust P2P Search Bridge**: Replaced mock Rust code with real `soulseek-rs-lib` implementation for high-performance concurrent searching.
- **Neural Audio-Quality Sentinel**: Integrated `ffmpeg`-based fake FLAC detection with automatic user blacklisting.
- **Enhanced Managed Artists**: Added persistent tracking of "Managed Artists" and automatic discovery of related artists.
- **Modern FastAPI**: Transitioned to the `lifespan` context manager for robust resource handling.
- **Improved Testing**: Expanded `pytest` suite to cover `QueueService`, `Orchestrator`, and library indexing logic.
- **Enhanced Rust Bridge**: Search results now include rich metadata (size, bitrate, speed).
- **Library Management**: New backend routes for manual album renaming and deletion; refined "Tidy" logic.

... [rest of changelog remains same]
