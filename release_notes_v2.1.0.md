# v2.1.0 Release Notes

## Major Changes
- **DevOps Hardening**: Completed 130 Ruff linter fixes and Mypy typings.
- **Docker Ready**: Audited and confirmed Docker deployments using multi-arch Github Actions `ci.yml`.
- **Rust Parity Verified**: Tested and verified fully complete hybrid Python/Rust implementations of the download P2P protocol without race conditions.
- **Headless Stability**: Hardened socket timeouts for API transfers and ThreadSafety constraints natively inside async event loops for server stability across deployments.
- **Windows Subprocess Isolation (Watchdog)**: Fully integrated back the previously lost Phase 7 watchdog tracking features targeting `Windows` distributions specifically. Re-introduced `filler_worker.py` and `watchdog.py`, along with `launch_watchdog.py` and `startup.ps1` helper shell bindings to handle the python venv duplicates bug.
- **End to End tests**: Full 26 Integration unit test suite executed and passed validating Phase 7 stability and E2E transfers.

## Enhancements
- Interactive UI Library Management for batch renaming and deletions.
- Automated generation of TODOs and ROADMAP progression tracking using AI agent workflows.
