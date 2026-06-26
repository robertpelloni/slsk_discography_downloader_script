"""
Standalone autonomous filler worker, launched as a subprocess by the
web server.  If this process crashes, the web server stays up.
"""

import asyncio
import json
import os
import socket
import sys
import time

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

# Apply socket timeout BEFORE any MusicBrainz imports
socket.setdefaulttimeout(15)

STATUS_FILE = os.path.join(BASE_DIR, "filler_status.json")


def write_status(data: dict):
    data["_ts"] = time.time()
    tmp = STATUS_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(data, f)
    os.replace(tmp, STATUS_FILE)


class SimpleLogger:
    def info(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] {msg}")

    def warning(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] WARN {msg}")

    def error(self, msg):
        print(f"[{time.strftime('%H:%M:%S')}] ERROR {msg}")


def main():
    # CLI: filler_worker.py <user> <pass> <depth> <dry_run> <artist_names...>
    if len(sys.argv) < 6:
        print("Usage: filler_worker.py <user> <pass> <depth> <dry_run> <artists...>")
        sys.exit(1)

    slsk_user = sys.argv[1]
    slsk_pass = sys.argv[2]
    depth = int(sys.argv[3])
    dry_run = sys.argv[4].lower() == "true"
    artist_names = sys.argv[5:]

    write_status({"running": True, "status": "starting", "artists": len(artist_names)})
    logger = SimpleLogger()
    logger.info(
        f"Filler worker started — {len(artist_names)} artists, depth={depth}, dry_run={dry_run}"
    )

    # Import services (after socket.setdefaulttimeout)
    from services.musicbrainz import MusicBrainzService
    from services.soulseek import SoulseekService
    from services.orchestrator import Orchestrator
    from services.config import ConfigService
    from services.queue import QueueService
    from services.post_processor import PostProcessor

    mb = MusicBrainzService()
    slsk = SoulseekService()
    config = ConfigService()
    queue = QueueService()
    pp = PostProcessor(mb, config, logger)
    orch = Orchestrator(logger, mb, slsk, config, pp, queue)

    try:
        asyncio.run(
            orch.run_autonomous_filler(
                slsk_user=slsk_user,
                slsk_pass=slsk_pass,
                artist_names=artist_names,
                depth=depth,
                dry_run=dry_run,
            )
        )
        write_status({"running": False, "status": "completed"})
        logger.info("Filler completed successfully")
    except Exception as e:
        logger.error(f"Filler failed: {e}")
        import traceback

        traceback.print_exc()
        write_status({"running": False, "status": "failed", "error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()
