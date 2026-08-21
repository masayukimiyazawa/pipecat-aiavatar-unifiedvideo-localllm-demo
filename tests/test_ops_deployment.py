"""Tests for ops-deployment 1.1 — health endpoint."""

import time

def test_health_returns_ok_true(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"ok": True}

def test_health_fast_without_auth(client):
    start = time.time()
    last = None
    for _ in range(10):
        last = client.get("/health")
        assert last.status_code == 200
    elapsed = time.time() - start
    # 10 requests should be < 100ms total (avg <10ms) — generous
    assert elapsed < 1.0, f"health too slow: {elapsed}s for 10 requests"
    # No auth header needed — verify no 401
    assert last.headers.get("www-authenticate") is None

def test_health_usable_for_curl_and_compose():
    import pathlib
    srv = pathlib.Path("server.py").read_text()
    assert '@app.get("/health")' in srv
    assert 'return {"ok": True}' in srv
    sh = pathlib.Path("start.sh").read_text()
    assert "curl -s http://localhost:8005/health" in sh
