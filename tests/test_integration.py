import httpx
import pytest

# This test requires a running server at http://localhost:8000
# It is intended for live environment validation.

BASE_URL = "http://localhost:8000"

@pytest.mark.asyncio
async def test_live_server_smoke():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        try:
            resp = await client.get("/api/status")
            assert resp.status_code == 200
            assert "is_running" in resp.json()
        except httpx.ConnectError:
            pytest.skip("Server not running at http://localhost:8000")

@pytest.mark.asyncio
async def test_live_config_flow():
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=10.0) as client:
        try:
            # Get current config
            resp = await client.get("/api/config")
            assert resp.status_code == 200
            orig_config = resp.json()

            # Update a non-sensitive field
            new_val = not orig_config.get("sentinel_enabled", False)
            orig_config["sentinel_enabled"] = new_val

            resp = await client.post("/api/config", json=orig_config)
            assert resp.status_code == 200

            # Verify update
            resp = await client.get("/api/config")
            assert resp.json()["sentinel_enabled"] == new_val
        except httpx.ConnectError:
            pytest.skip("Server not running at http://localhost:8000")
