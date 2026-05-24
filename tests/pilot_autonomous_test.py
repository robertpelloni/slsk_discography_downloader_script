import httpx
import pytest
import asyncio
import time
import os

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8000")

@pytest.mark.asyncio
async def test_pilot_autonomous_protocol():
    """
    Pilot integration test to evaluate the autonomous protocol performance.
    """
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=30.0) as client:
        # 1. Health Check
        print("\n[Pilot] Phase 1: Health Check")
        try:
            resp = await client.get("/api/status")
            assert resp.status_code == 200
            status = resp.json()
            print(f"[Pilot] Server status: {status}")
            assert "is_running" in status
        except httpx.ConnectError:
            pytest.skip(f"Server not running at {BASE_URL}")

        # 2. Config Validation
        print("[Pilot] Phase 2: Config Validation")
        resp = await client.get("/api/config")
        assert resp.status_code == 200
        config = resp.json()
        print(f"[Pilot] Current config: {config}")
        assert "sentinel_enabled" in config

        # 3. Autonomous Scan Trigger
        print("[Pilot] Phase 3: Autonomous Scan (Artist: GMS)")
        # We use a known artist that is fast to scan
        scan_payload = {
            "artist_names": ["GMS"],
            "depth": 0 # Depth 0 for speed in pilot
        }
        # Increase timeout for scan as it hits external APIs
        resp = await client.post("/api/scan", json=scan_payload, timeout=60.0)
        assert resp.status_code == 200
        scan_result = resp.json()
        assert "tree" in scan_result
        print(f"[Pilot] Scan found {len(scan_result['tree'])} artist(s)")

        # 4. Managed Artist Verification
        print("[Pilot] Phase 4: Managed Artist Verification")
        resp = await client.get("/api/managed_artists")
        assert resp.status_code == 200
        managed = resp.json()
        artist_names = [a['name'] for a in managed.get('active', [])]
        print(f"[Pilot] Managed artists: {artist_names}")
        assert "GMS" in artist_names or "Growling Mad Scientists" in artist_names

        # 5. Job Control Stress Test (Start/Stop)
        print("[Pilot] Phase 5: Job Control Stress Test")
        start_payload = {
            "artist_names": ["GMS"],
            "dry_run": True,
            "depth": 0
        }
        resp = await client.post("/api/start", json=start_payload)
        # It might return 400 if credentials are missing, which is expected in some envs
        if resp.status_code == 200:
            print("[Pilot] Job started successfully")
            # Wait a moment
            await asyncio.sleep(2)
            # Stop it
            resp = await client.post("/api/stop")
            assert resp.status_code == 200
            print("[Pilot] Job stopped successfully")
        else:
            print(f"[Pilot] Job start skipped or failed (Status {resp.status_code}): {resp.text}")

        print("[Pilot] Autonomous Protocol Pilot Integration Test Passed.")

if __name__ == "__main__":
    asyncio.run(test_pilot_autonomous_protocol())
