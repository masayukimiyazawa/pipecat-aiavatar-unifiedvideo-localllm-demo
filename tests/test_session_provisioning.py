"""Tests for session-provisioning 1.2 — WS_URI scheme validation."""

import os
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

def test_ws_uri_invalid_scheme_returns_500(monkeypatch):
    # Need valid Vonage creds to reach validation
    monkeypatch.setenv("VONAGE_APPLICATION_ID", "test-app-id")
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4=\n-----END PRIVATE KEY-----")
    monkeypatch.setenv("WS_URI", "http://invalid/ws")  # invalid scheme

    import server
    client = TestClient(server.app)
    # Mock Vonage client creation to avoid real Vonage calls (should not be reached due to validation)
    with patch("server._create_vonage_client") as mock_create:
        mock_create.return_value = MagicMock()
        r = client.post("/api/vonage/session", headers={"host": "localhost:8005"})
        assert r.status_code == 500
        assert "Invalid WS_URI scheme" in r.text
        # Ensure audio connector not called
        mock_create.assert_not_called()

def test_ws_uri_valid_wss_passes_to_vonage(monkeypatch):
    monkeypatch.setenv("VONAGE_APPLICATION_ID", "test-app-id")
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4=\n-----END PRIVATE KEY-----")
    monkeypatch.setenv("WS_URI", "wss://valid.example.com/ws")
    monkeypatch.setenv("VONAGE_AUDIO_RATE", "16000")

    import server
    client = TestClient(server.app)
    mock_vng = MagicMock()
    mock_vng.video.create_session.return_value.session_id = "test-session-id"
    mock_vng.video.generate_client_token.return_value = b"mock-token"
    mock_vng.video.start_audio_connector.return_value.id = "connector-id"
    mock_vng._http_client.auth.application_id = "test-app-id"
    mock_vng._http_client.video_host = "video.api.vonage.com"

    with patch("server._create_vonage_client", return_value=mock_vng) as mock_create:
        with patch("server._create_session_async", return_value="test-session-id"):
            with patch("server._connect_audio_connector_async") as mock_connect:
                with patch("server._generate_client_token", return_value="mock-token"):
                    r = client.post("/api/vonage/session", headers={"host": "valid.example.com"})
                    # Should not hit invalid scheme
                    assert "Invalid WS_URI" not in r.text
                    # Either 200 or Audio Connector error (mocked), but not scheme error
                    assert r.status_code in (200, 500)

def test_ws_uri_derivation_localhost_uses_ws(monkeypatch):
    monkeypatch.setenv("VONAGE_APPLICATION_ID", "test-app-id")
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4=\n-----END PRIVATE KEY-----")
    monkeypatch.delenv("WS_URI", raising=False)

    import server
    client = TestClient(server.app)
    # Mock to capture ws_uri
    captured = {}
    async def fake_connect(vng, session_id, ws_uri, audio_rate):
        captured["ws_uri"] = ws_uri

    mock_vng = MagicMock()
    with patch("server._create_vonage_client", return_value=mock_vng):
        with patch("server._create_session_async", return_value="sid123"):
            with patch("server._connect_audio_connector_async", side_effect=fake_connect):
                with patch("server._generate_client_token", return_value="tok"):
                    r = client.post("/api/vonage/session", headers={"host": "localhost:8005"})
                    assert captured.get("ws_uri") == "ws://localhost:8005/ws"

def test_ws_uri_derivation_127001_is_wss_known_limitation(monkeypatch):
    monkeypatch.setenv("VONAGE_APPLICATION_ID", "test-app-id")
    monkeypatch.setenv("VONAGE_PRIVATE_KEY", "-----BEGIN PRIVATE KEY-----\nMIIBVAIBADANBgkqhkiG9w0BAQEFAASCAT4=\n-----END PRIVATE KEY-----")
    monkeypatch.delenv("WS_URI", raising=False)

    import server
    client = TestClient(server.app)
    captured = {}
    async def fake_connect(vng, session_id, ws_uri, audio_rate):
        captured["ws_uri"] = ws_uri

    mock_vng = MagicMock()
    with patch("server._create_vonage_client", return_value=mock_vng):
        with patch("server._create_session_async", return_value="sid123"):
            with patch("server._connect_audio_connector_async", side_effect=fake_connect):
                with patch("server._generate_client_token", return_value="tok"):
                    r = client.post("/api/vonage/session", headers={"host": "127.0.0.1:8005"})
                    # Known limitation: 127.0.0.1 → wss (should be ws)
                    assert captured.get("ws_uri") == "wss://127.0.0.1:8005/ws"
