# Changelog

## [0.8.0]
- Enhanced `Pydantic` request models with strict `Field` validation constraints to secure and structure API endpoint inputs.

## [0.7.0]
- Added comprehensive unit testing suite using `pytest`. Implemented initial tests for `ConfigService` and `MusicBrainzService` logic, covering db persistence and mocking external network dependencies.

## [0.6.0]
- Refactored `main.py` by splitting API routes into `routers/core.py` and `routers/library.py` to improve maintainability.

## [0.5.0]
- Added Docker containerization (Dockerfile and docker-compose.yml) for reliable, one-click deployments.

## [0.4.0]
- Enhanced log viewing in the UI with dynamic text colors to differentiate errors, warnings, successes, and skips.

## [0.3.0]
- Compiled and wired the Rust bridge (`bob_soulseek_rs`) interface. Note: Reverted the active service to the Python implementation because the Rust code currently only provides mock responses, which broke real downloads.

## [0.2.0]
- Wire up dynamic application version from VERSION.md to the frontend UI so we don't have hardcoded versions.
- Added python-dotenv support for configuration via .env file.
- Added comprehensive project documentation (VISION, ROADMAP, HANDOFF, DEPLOY, etc.).

## [0.1.0] - Initial version
- Basic working prototype.
