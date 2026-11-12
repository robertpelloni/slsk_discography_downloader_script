"""
Wait for the currently-running fill to finish, then run a second pass over the
artists that were wrongly skipped by the genre filter before the 2026-09-14
whitelist additions in services/orchestrator.py.

Runs detached; logs to pass2_skipped.log.
"""
import json
import os
import time
import urllib.error
import urllib.request
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
STATUS = os.path.join(BASE, "filler_status.json")
LOG = os.path.join(BASE, "pass2_skipped.log")

# Artists skipped purely for missing MusicBrainz genre tags (now whitelisted)
SKIPPED = [
    "Arma", "Ashtar Command", "Avan7", "Basic Element", "Beat Hackers",
    "Bionix", "ClayHeadz", "Cronyx", "Crop Circles", "Epsylon 9",
    "Fungus Funk", "Jumpstreet", "Lunatica", "Madnetic", "Magik",
    "Solitary Shell", "Synkronic", "Transient Disorder", "Zephirus Kane",
    "Zeridium", "Chicago", "1300 Micrograms", "Shanti V Deedrah",
    "Tyler Jack", "Spectra Sonics", "Galactic Explorers", "Sonic Entity",
    "Man With No Name", "Ital", "Andrea Braggio", "Abomination",
    "DJ KETAFLUSH", "Mosq Intelligence", "Kraftwek Orange",
]


def log(msg):
    line = f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}"
    print(line, flush=True)
    with open(LOG, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def filler_running():
    try:
        with open(STATUS, encoding="utf-8") as fh:
            return bool(json.load(fh).get("running"))
    except (OSError, ValueError):
        return False


def trigger(artists):
    body = json.dumps(
        {"artist_names": artists, "depth": 1, "dry_run": False}
    ).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:8000/api/autonomous_fill",
        data=body, headers={"Content-Type": "application/json"}, method="POST",
    )
    r = urllib.request.urlopen(req, timeout=60)
    return r.status, r.read().decode()


def main():
    log(f"pass2 watcher started; waiting for active fill to finish "
        f"({len(SKIPPED)} artists queued)")

    # wait for the current run to end (ignore a stale 'running' flag older than
    # the process that is actually alive)
    while filler_running():
        time.sleep(30)
    log("active fill finished; cooling down 300s for API cooldown")
    time.sleep(305)

    for attempt in range(1, 6):
        try:
            status, body = trigger(SKIPPED)
            log(f"pass 2 triggered (attempt {attempt}): {status} {body[:200]}")
            return
        except urllib.error.HTTPError as e:
            detail = e.read().decode()[:200]
            log(f"attempt {attempt} HTTP {e.code}: {detail}; retrying in 120s")
            time.sleep(120)
        except Exception as e:
            log(f"attempt {attempt} failed: {e}; retrying in 120s")
            time.sleep(120)
    log("pass 2 could not be started after 5 attempts")


if __name__ == "__main__":
    main()
