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

## Remaining

- [ ] Fix the orphan thread accumulation issue in the filler subprocess (still occurs after extended uptime)
- [ ] Test filler download with actual Soulseek credentials to verify end-to-end
- [ ] Add .env to .gitignore (contains credentials)
- [ ] Investigate server "listening but not responding HTTP" after extended uptime
