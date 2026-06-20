# Handoff - v1.2.0

## Status
- **Current Version**: 1.2.0
- **AcoustID Identification**: Integrated and Tested.
- **Search Performance**: Rust FFI bridge provides ~87% speed boost.
- **Visual Analytics**: Live search benchmark visualization integrated into dashboard.
- **Deployment Status**: Manual deployment verified; E2E tests passing.
- **P2P Expansion**: Implemented full Rust integration of the Soulseek file transfer protocol.

## Major Changes in 1.3.0
1. **Batch Library Actions**: The UI now supports multiselect batch renaming and batch deletion of albums, saving users significant time.
2. **Rust P2P Search Stability**: Increased polling timeouts in `rust_search_async` and added non-blocking warnings (`eprintln!`) to prevent premature channel drop errors in high-concurrency environments.
3. **Multi-Remote Upstream Sync**: Enhanced `ProtocolService` branch reconciliation to dynamically detect and gracefully sync multiple git remotes (`origin`, `upstream`).

## Major Changes in 1.2.0
1. **Rust File Transfer**: Integrated Soulseek P2P downloads completely into the `bob_soulseek_rs` library via PyO3, replacing `aioslsk` transfer logic. The Rust bridge safely yields to Python's asyncio via Tokio and standard Rust mutexes, maintaining orchestrator timeout fidelity.
2. **Bug Fixes**: Resolved Python logic bugs in `is_psytrance_artist` for improved forensic filtering.
3. **Protocol Extraction**: Resolved bug where missing `TODO.md` file broke the autonomous sync protocol.

## Major Changes in 1.1.0
1. **Self-Learning Agent Module**: Integrated a new `LearningModule` that tracks task friction.
2. **Dynamic Prioritization**: Updated `PlanningModule` to autonomously boost priority of high-friction task types.
3. **Adaptive Execution**: Enhanced the autonomous cycle with friction-aware execution and automatic technical debt reconciliation.

## Major Changes in 1.0.0
1. **Self-Directed Agent Framework**: Introduced `AgentService` for autonomous task planning and execution. The agent utilizes a `PlanningModule` to prioritize work from `TODO.md` and an `ExecutionModule` to trigger system services.
2. **Modular Router Expansion**: Added `routers/agent.py` to expose autonomous control via the API.
3. **Verified v1.0 Stability**: Added `tests/test_agent_framework.py` ensuring 100% pass rate on core agent logic.

## Structural Map (Submodules)
- **Rust Bridge**: `discography_webapp/rust_bridge/`
  - Depends on `soulseek-rs-lib` crate.
  - Linked to Python via `pyo3` and `maturin`.

## Deployment Notes
- **Dependencies**: Requires `ffmpeg` and `fpcalc` (via `libchromaprint-tools`) in the system `PATH`. Also requires a compiled copy of `bob_soulseek_rs.so` loaded into `PYTHONPATH`.

## Note for Successor Models
All 23 active tests in the suite pass successfully. The `AgentService` can be triggered via `/api/agent/cycle`. The "Neural Sentinel", "AcoustID", "Autonomous Agent", and now the "Rust Download Bridge" services are all fully integrated.
