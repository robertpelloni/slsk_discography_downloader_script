# Ideas for Improvement & New Features

## Architecture & Code Quality
1. **Comprehensive Unit Testing**: The project currently lacks automated testing. Implementing `pytest` across all services (MusicBrainz, config parsing, post-processing, Soulseek interactions) will greatly improve robustness and allow for safer refactoring.
2. **Pydantic Validation**: Expand `Pydantic` models to strictly validate all incoming data and backend configurations.
3. **Database Integration**: Currently, the application uses local `.json` or filesystem scans for state. Moving configuration, queue states, and library tracking to SQLite (or an async ORM like SQLAlchemy/Tortoise) will massively speed up index rendering and prevent race conditions.
4. **WebSocket Authentication**: Add basic auth tokens to the WebSocket connections so that logs cannot be hijacked if the server is exposed publicly.

## UI & Frontend
1. **Interactive Library Editor**: A frontend page where users can manually rename mismatched tracks, fetch alternate cover art, or edit ID3 tags in the browser.
2. **Live Metrics Dashboard**: Visual graphs indicating download speeds, remaining queue size, active connections, and disk space usage.
3. **Responsive Mobile Overhaul**: The current UI is functional but dense. Using a lightweight CSS framework (like Tailwind or Pico) would make it pleasant to use on mobile devices.

## Features
1. **AcoustID Audio Fingerprinting**: Integrate the `pyacoustid` package (already in `requirements.txt`) to fingerprint unknown audio files on disk and automatically match them against MusicBrainz.
2. **Lyrics Embedding**: Utilize the Genius API to fetch lyrics post-download and embed them directly into the ID3/FLAC tags (currently indicated in the UI but backend implementation may be incomplete).
3. **Rust P2P Implementation**: Finish Phase 2 of the roadmap. The `bob_soulseek_rs` library needs native async socket routing and Soulseek protocol packet building.
