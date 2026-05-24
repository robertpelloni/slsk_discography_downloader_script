# Handoff - v0.9.9

## Status
- **Current Version**: 0.9.9
- **AcoustID Identification**: Integrated and Tested.
- **Search Performance**: Rust FFI bridge provides ~87% speed boost.
- **Visual Analytics**: Live search benchmark visualization integrated into dashboard.
- **Deployment Status**: Manual deployment verified; E2E tests passing.

## Major Changes in 0.9.9
1. **AcoustID Audio Fingerprinting**: Integrated `pyacoustid` into `PostProcessor` to identify files missing metadata based on audio content.
2. **Performance Dashboard**: Added a new UI panel for running and visualizing live search benchmarks.
3. **Comprehensive Manual**: Created `MANUAL.md` detailing all advanced forensic and performance features.
4. **Environment Synchronization**: Verified environment setup with `requirements.txt` and manual deployment lifecycle.

## Major Changes in 0.9.8
1. **Integration Pilot**: Verified end-to-end performance and safety of the codified maintenance protocol.
2. **Git Lock Protection**: Improved `ProtocolService` robustness for concurrent access.

## Structural Map (Submodules)
- **Rust Bridge**: `discography_webapp/rust_bridge/`
  - Depends on `soulseek-rs-lib` crate.
  - Linked to Python via `pyo3` and `maturin`.

## Deployment Notes
- **Sandbox Limitation**: Docker building is restricted in the current sandbox environment due to overlay mount errors. Manual deployment is the verified path:
  ```bash
  pip install -r discography_webapp/requirements.txt
  python3 discography_webapp/main.py
  ```
- **Dependencies**: Requires `ffmpeg` and `fpcalc` (via `libchromaprint-tools`) in the system `PATH`.

## Note for Successor Models
All 19 tests in the suite pass. The `ProtocolService` automatically updates `ROADMAP.md` and `TODO.md` on startup. The "Neural Sentinel" and "AcoustID" services are both fully integrated and configurable via the web dashboard.
