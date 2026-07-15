# TODOs

- [x] Phase 6: P2P Expansion - Full Rust implementation of the file transfer protocol (Download).
- [x] MusicBrainz SQLite cache for artist/discography data
- [x] Soulseek connection state detection and auto-retry
- [x] Rate limiting for Soulseek searches
- [x] Merge conflict cleanup from jules feature branch

## Remaining

- [ ] Fix the orphan thread accumulation issue in the filler subprocess (still occurs after extended uptime)
- [ ] Test filler download with actual Soulseek credentials to verify end-to-end
- [ ] Add .env to .gitignore (contains credentials)
- [ ] Investigate server "listening but not responding HTTP" after extended uptime
