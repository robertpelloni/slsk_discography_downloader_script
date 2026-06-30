# slsk_discography_downloader

The **slsk_discography_downloader** is an autonomous tool designed to discover, download, and organize complete artist discographies using MusicBrainz metadata and Soulseek's P2P network.

## 🚀 Key Features

- **High-Performance Rust P2P Bridge:** Leverages a custom `bob_soulseek_rs` bridge powered by Rust and Tokio for high-concurrency, non-blocking searches and file transfers, delivering a massive performance boost over native Python implementations.
- **Autonomous Agent Integration:** An embedded AI-driven autonomous framework (`AgentService`) capable of planning tasks, auto-executing background downloads, managing technical debt, and learning from friction to dynamically reprioritize operations.
- **Audio Forensics ("Neural Sentinel"):** Analyzes downloaded files using AcoustID fingerprinting and `ffmpeg` to detect and filter out up-scaled "fake" FLAC files, ensuring pristine library quality and automatically blacklisting malicious peers.
- **Library Organization & Batch Management:** A comprehensive web-UI dashboard to browse downloads, with features for batch renaming, batch deletion, and automatic metadata-driven folder tidying.
- **Automated CI/CD:** Fully Dockerized with multi-platform GitHub Actions workflows for seamless deployments.
- **Headless & Cross-Platform:** Implements specific `asyncio.to_thread` usage for Linux and robust watchdog subprocess isolation for Windows environments.

## 📦 Quick Start (Docker - Recommended)

The easiest way to run the application is via Docker. This avoids needing to compile the Rust bridge manually.

1. **Clone the repository:**
   ```bash
   git clone https://github.com/robertpelloni/slsk_discography_downloader_script.git
   cd slsk_discography_downloader_script
   ```
2. **Configure Environment:**
   Copy the example environment file and configure your credentials.
   ```bash
   cp .env.example .env
   # Edit .env to add your Soulseek username and password
   ```
3. **Run via Docker Compose:**
   ```bash
   docker compose up -d --build
   ```
4. **Access the Dashboard:**
   Open your browser to `http://localhost:8000`

*Note: Downloaded data and internal databases will be mapped to `./data` and `./downloads`.*

## ⚙️ Quick Start (Manual Setup)

If you prefer to run the application on bare metal:

### Prerequisites
- Python 3.11 or 3.12
- Rust and Cargo (`maturin`)
- `ffmpeg` and `fpcalc` (libchromaprint-tools) installed in your system `$PATH`.

### Setup Steps
1. **Clone and setup `.env`:**
   ```bash
   git clone https://github.com/robertpelloni/slsk_discography_downloader_script.git
   cd slsk_discography_downloader_script
   cp .env.example .env
   ```
2. **Install Python Dependencies:**
   ```bash
   pip install -r discography_webapp/requirements.txt
   ```
3. **Compile the Rust Bridge:**
   ```bash
   cd discography_webapp/rust_bridge
   maturin develop --release
   cd ../../
   ```
4. **Run the Application:**
   ```bash
   python discography_webapp/main.py
   ```

## 🛠 Configuration

Configuration is managed entirely through the `.env` file (see `.env.example`).
Key settings include:
- `SLSK_USERNAME` / `SLSK_PASSWORD`: Your Soulseek P2P network credentials.
- Database and path configurations.
- API tuning parameters (e.g. search timeouts, download retry thresholds).

## 🎛 API & Usage Examples

The FastAPI backend exposes several interactive routes. You can view the full interactive API documentation by navigating to `http://localhost:8000/docs` while the server is running.

**Key Endpoints:**
- `GET /api/library/status` - View current download queue and library statistics.
- `POST /api/library/batch_rename` - Pass a JSON payload of target paths to securely rename albums.
- `POST /api/agent/cycle` - Trigger a manual tick of the autonomous agent to plan and execute pending background downloads.

## 🤝 Contributing & Documentation

For deeper insights into the project architecture, consult the following markdown files:
- `VISION.md`: Core project goals and foundational concepts.
- `DEPLOY.md`: Advanced deployment instructions and GitHub Actions flow.
- `CHANGELOG.md`: Detailed version history and structural changes.

*(Version dynamically tracked via `VERSION.md`)*
