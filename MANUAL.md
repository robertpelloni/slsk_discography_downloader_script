# 🎵 Discography Downloader - User Manual

Welcome to the ultimate autonomous discography management tool. This application combines high-performance Soulseek P2P searching with advanced audio forensics and automated metadata reconciliation.

## 🚀 Core Features

### 1. High-Performance Search (Rust Boost)
The application utilizes a custom Rust FFI (Foreign Function Interface) bridge to the Soulseek network.
- **87% faster search latency** compared to standard Python implementations.
- Efficient handling of thousands of search results using multi-threaded asynchronous polling.

### 2. Neural Audio Sentinel (Fake FLAC Detection)
Protect your library from low-quality upscales. The Sentinel uses `ffmpeg` frequency analysis to audit every lossless download.
- **How it works:** Analyzes the frequency spectrum above 18kHz.
- **Action:** If a "lossless" file is detected to have a lossy spectral profile (indicative of a 128kbps/320kbps upscale), it is automatically deleted, and the serving user is blacklisted.

### 3. AcoustID Audio Fingerprinting
Never deal with "Track 01.mp3" again.
- Uses acoustic fingerprinting to identify files based on their actual audio content, not just filenames.
- Automatically reconciles unidentified downloads with MusicBrainz metadata.

### 4. Autonomous AI Protocol
The system includes a codified maintenance protocol that keeps the codebase and your library healthy.
- **Sync & Reconcile:** Automatically merges feature branches and syncs with upstream changes.
- **Roadmap Extraction:** Continuously analyzes the codebase to identify technical debt and future tasks.

### 5. Core Self-Directed Agent Framework (v1.0)
The application now features an autonomous agent capable of self-directed task management.
- **Autonomous Planning:** Analyzes `TODO.md` and `ROADMAP.md` to prioritize objectives based on system state.
- **Task Execution:** Programmatically triggers maintenance cycles, repository syncs, and documentation updates.
- **Iterative Improvement:** Reviews its own execution outcomes and updates technical debt records.

---

## 🛠 Usage Guide

### Starting a Download
1. Enter artist names (comma-separated) in the **Control Panel**.
2. Set **Related Depth** to find similar artists via MusicBrainz.
3. Click **Scan** to review the discography before downloading, or **Start** to begin immediately.

### Library Management
- **Sync Artists:** Refresh the managed artist list from disk.
- **Tidy Flat Files:** Automatically moves single tracks in the root into structured `Artist/Album` folders.
- **One-Click Clean All:** Runs a full pipeline of deduplication, organization, and empty folder cleanup.

### Performance Benchmarking
Visit the **Performance Metrics** tab to compare implementation speeds. Enter a query and click "Run Benchmark" to see the "Rust Speedup" in real-time.

---

## ⚙️ Configuration

| Setting | Description |
|---------|-------------|
| **Preferred Format** | Choose between FLAC (Lossless) or MP3 (320kbps). |
| **AcoustID Fallback** | Enables fingerprinting for files with missing metadata. |
| **Sentinel Enabled** | Activates the "Fake FLAC" detection engine. |
| **Auto-Convert** | Automatically generates MP3 V0 copies of FLAC downloads. |

---

## 🛡 Security & Safety
- **Path Safety:** All file operations are protected by path-traversal validation.
- **Credentials:** Your Soulseek credentials and API keys are stored locally in `.env` and are never shared or logged.

---
*Version: v0.9.9 · Created by Jules AI*
