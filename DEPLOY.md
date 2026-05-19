# Deployment

## Setup Instructions (Docker - Recommended)
1. Copy `.env.example` to `.env` and configure any required secrets.
2. Run `docker compose up -d --build`.
3. The application will be available at http://localhost:8000. Data and downloads will map to the `./data` and `./downloads` folders in your current directory.

## Setup Instructions (Manual)
1. Copy `.env.example` to `.env` and fill in any secrets.
2. Install python dependencies: `pip install -r discography_webapp/requirements.txt`
3. Run the application: `python discography_webapp/main.py`

## Inventory of Major Libraries and Packages
- **FastAPI** (v0.100+ via requirements): Used for the high-performance async web framework.
- **Uvicorn**: ASGI server to run FastAPI.
- **Jinja2**: Templating engine for rendering `index.html`.
- **aioslsk**: The async Soulseek client library for the P2P connection. Located in `services/soulseek.py`.
- **musicbrainzngs**: The Python wrapper for the MusicBrainz API, for metadata fetching.
- **mutagen**: Python module to handle audio metadata (ID3 tags, FLAC tags).
- **bob_soulseek_rs** (Internal Submodule): Custom Rust bridge located in `discography_webapp/rust_bridge` to handle high-performance searches (partially implemented).
- **python-dotenv**: For loading `.env` files into environment variables.
