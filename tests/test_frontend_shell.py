"""Tests for frontend-shell tasks 1.1 and 1.2 — static delivery and favicon.

Covers requirements 4.1-4.4 and design StaticDelivery.
Reuse: tests/conftest.py client fixture (server.py:135 app), beautifulsoup4 for DOM.
"""

def test_get_root_returns_200_with_video_row(client):
    r = client.get("/")
    assert r.status_code == 200, r.text[:500]
    assert "video-row" in r.text
    assert 'id="userVideoContainer"' in r.text
    assert 'id="anam-avatar"' in r.text

def test_get_static_script_js_returns_200(client):
    r = client.get("/static/script.js")
    assert r.status_code == 200
    # contains ESM import for Anam
    assert "createClient" in r.text

def test_get_favicon_returns_204_no_body(client):
    r = client.get("/favicon.ico")
    assert r.status_code == 204
    assert r.content == b""

def test_get_missing_static_returns_404_without_traceback(client):
    r = client.get("/static/missing.js")
    assert r.status_code == 404
    # FastAPI default 404 JSON should not contain Python traceback
    body = r.text
    assert "Traceback" not in body
    assert "stack trace" not in body.lower()
    assert "FileResponse" not in body

def test_static_files_mount_exists():
    # Code-level precondition: server.py:135
    import pathlib
    srv = pathlib.Path("server.py").read_text()
    assert 'StaticFiles(directory="static")' in srv
    assert 'FileResponse("static/index.html")' in srv
    assert 'Response(status_code=204)' in srv
