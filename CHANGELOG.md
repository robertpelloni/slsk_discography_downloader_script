# Changelog

## [1.2.0]\n- **P2P Expansion**: Implemented full Rust integration of the Soulseek file transfer protocol (Phase 6).\n- **Bug Fixes**: Resolved logic issues within the psytrance filtering and TODO extraction modules.\n\n## [1.1.0]
- **Self-Learning Agent Module**: Integrated a new `LearningModule` that tracks task friction (latency/failure) in an experience log.
- **Dynamic Prioritization**: Updated `PlanningModule` to autonomously boost the priority of high-friction task types.
- **Adaptive Execution**: Enhanced the autonomous cycle with friction-aware execution and automatic technical debt reconciliation.
- **Refined Test Suite**: Expanded framework tests to verify the priority-boosting logic and learned experience persistence.

## [1.0.0]
- **Core Self-Directed Agent Framework**: Introduced autonomous planning and execution engine.
- **Unified Maintenance Protocol**: Completed real-world repository sync and branch reconciliation.
- **Scalable Architecture**: Fully modularized backend with dedicated routers for core, library, protocol, and agent services.
- **Verified Stability**: Integrated 23-test suite covering all forensic and autonomous components.

## [0.9.9]
- **AcoustID Audio Fingerprinting**: Integrated `pyacoustid` to identify unmatched files based on audio content.
- **Performance Visualization**: Added live search benchmark visualization to the dashboard.
- **Comprehensive Documentation**: Released `MANUAL.md` covering search boosts, audio forensics, and AI protocols.
- **Refined Unit Testing**: Increased test coverage with dedicated AcoustID and protocol verification suites.

## [0.9.8]
- **Protocol Integration Pilot**: Successfully integrated and validated the Autonomous AI Development Protocol in a live environment.
- **Maintenance Safety**: Added checks for existing Git locks (`MERGE_HEAD`) to prevent corrupted repository states during automated reconciliation.
- **Integrated Performance**: Verified that the codified protocol layer maintains search latency improvements (~86% gain).
- **UI Verification**: Completed visual verification of the integrated System Maintenance dashboard.

## [0.9.7]
- **Performance Benchmarking**: Integrated a new benchmark suite to measure and compare search latency between Python and Rust Soulseek bridges. Initial tests show an ~87% reduction in search time with Rust.
- **Continuous Protocol**: Embedded the Autonomous AI Development Protocol into the application startup, automatically extracting roadmaps to detect technical debt and feature gaps.
- **Robust Error Handling**: Refined benchmark and service initialization to gracefully handle disconnected or unavailable bridge states.

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
