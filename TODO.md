# TODOs

- [x] Phase 6: P2P Expansion - Full Rust implementation of the file transfer protocol (Download).
- [x] MusicBrainz SQLite cache for artist/discography data
- [x] Soulseek connection state detection and auto-retry
- [x] Rate limiting for Soulseek searches
- [x] Merge conflict cleanup from jules feature branch
- [x] Unified single-page Dashboard redesign with high-value prioritization
- [x] Full interactive tooltip coverage and inline guidance (`[data-tooltip]`)
- [x] Server lifecycle control (`/api/server/shutdown` & `/api/server/restart`)
- [x] System Tray process control & health monitoring integration
- [x] Backend feature wiring for MusicBrainz cache stats, Agent cycles, and Single-Artist organize
- [x] Script cleanup with nondestructive archiving in `scripts_archive/`
- [x] Real-time Autonomous Agent session telemetry & background monitoring endpoint (`/api/agent/telemetry`)
- [x] Add .env to .gitignore (contains credentials)
- [x] Test filler and discography download with actual Soulseek credentials end-to-end (Ajja FLAC discography + 93 managed artists)
- [x] Reconcile dropped commits (`d7d9c53`), stashes (`stash@{0}`, `stash@{2}`), and feature branches (`jules-57044827041196387-8ad75250`) into `main`
- [x] Isolate live credentials strictly in gitignored `discography_webapp/.env` and scrub `data/app.db` `user_configs`
- [x] Isolate `pytest` SQLite fixtures via `tmp_path` so test teardown never touches live `data/app.db`
- [x] Unify `psutil` + multi-retry HTTP health checks + 500 MB RAM threshold in `watchdog.py` to auto-recover hung servers
- [x] Track `.memory/`, `.jules/`, `.pi/`, and non-sensitive databases in Git

## Remaining

- [ ] Monitor orphan thread accumulation in `filler_worker.py` across multi-day runs
- [ ] Optional: add automated spectral graph export for flagged Fake FLAC files in Sentinel UI
