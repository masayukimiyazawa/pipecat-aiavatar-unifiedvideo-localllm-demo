# Implementation Plan

- [ ] 1. Refactor connector lifecycle to remove legacy singletons
- [x] 1.1 Add `asyncio.Lock` for `_active_connectors` and document singleton (P)
  - Introduce ` _connector_lock = asyncio.Lock()` in `server.py:68` region; wrap `for old_sid in list(_active_connectors.keys()): await _stop` and `start/check/store` in `async with _connector_lock`
  - Note in comment that current loop enforces global singleton (only one system-wide) not per-session; add TODO for per-session map
  - Verify concurrent `_connect_audio_connector_async` ×3 no longer races on dict snapshot
  - _Requirements: 1.1, 4.1, 4.3_
  - _Boundary: ConnectorLifecycle_
- [x] 1.2 Reuse `vng` instance in `_stop` and add shutdown cleanup (P)
  - Change `_stop_audio_connector_async(session_id: str, vng: Vonage | None = None)` to reuse passed `vng` if provided; fallback to `_get_video_client()`; avoid re-reading env per stop
  - Add FastAPI `lifespan` shutdown hook to iterate `_active_connectors` and `await _stop` for each (fix gap at `server.py:126`)
  - Observable: `POST /api/vonage/session` second call stops first without re-reading `VONAGE_PRIVATE_KEY` from file twice (mock `open` call count)
  - _Requirements: 1.4, 1.5, 4.4, 5.6_
  - _Boundary: ConnectorLifecycle_
- [ ] 1.3 Replace raw `_http_client.delete` with SDK method (tech debt)
  - Investigate `vonage-video` `stop_audio_connector` SDK; if exists replace `vng._http_client.delete(video_host, "/v2/project/{id}/connect?...")` at `108` with `vng.video.stop_audio_connector(session_id)`; keep fallback with comment
  - Verify DELETE path still includes `application_id` when fallback used
  - _Requirements: 1.5, 5.1_
  - _Boundary: ConnectorLifecycle_

- [ ] 2. Harden `WS /ws` endpoint
- [ ] 2.1 Verify serializer and transport creation per spec
  - Confirm `VonageFrameSerializer(InputParams(vonage_sample_rate=16000))` at `234` and `FastAPIWebsocketTransport(..., audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2)` at `240`; handle non-numeric `VONAGE_AUDIO_RATE` via 500 before `accept` (add guard)
  - Test `VONAGE_AUDIO_RATE=16000` → serializer 16000; `VONAGE_AUDIO_RATE=abc` → connection not established
  - _Requirements: 2.2, 2.3, 3.1, 3.2, 3.3_
  - _Boundary: WsEndpoint_
- [ ] 2.2 Strengthen keepalive and error propagation
  - Ensure `keepalive()` at `250` sends `'{"event":"keepalive"}'` as text every 10s and `break` on exception; on `bot()` exception log `Pipecat bot error`, `cancel` keepalive and `cleanup` transport as at `264-268`
  - Add warning log when `ws_uri` is `ws://` (plain) assuming `session-provisioning` enforces `wss` in prod
  - Observable: mock `websocket.send_text` raise → keepalive loop exits and `transport.cleanup()` called
  - _Requirements: 2.4, 2.5, 3.4, 5.3, 5.4_
  - _Boundary: WsEndpoint_
- [ ] 2.3 Ensure `bidirectional=True` future-proof
  - Verify `AudioConnectorWebSocket(bidirectional=True)` at `86` remains; add comment that `transport.output()` will flow to Vonage when server TTS enabled
  - No functional change; grep confirms `bidirectional=True`
  - _Requirements: 2.2, 5.5_
  - _Boundary: ConnectorLifecycle_

- [ ] 3. Validate rate alignment and no secret leakage
- [ ] 3.1 Test unified 16000 rate and 20ms chunks
  - Assert `PipelineParams(audio_out_10ms_chunks=2)` yields 20ms and matches `VonageFrameSerializer` rate; non-16000 rate logs warning and serializer still 16000 (canonical)
  - Verify `private_key`/`token` never logged, only `session_id`/`connector.id` at `77,96`
  - _Requirements: 3.1, 3.2, 3.4, 5.1_
  - _Boundary: WsEndpoint_

- [ ]* 4. E2E Vonage audio bridge test
  - Mock Vonage Audio Connector WS connect `/ws` → verify `VonageFrameSerializer` produces `AudioRawFrame` and `bot` invoked via `WebSocketRunnerArguments`; second `POST /api/vonage/session` stops first connector (`_active_connectors` size stays 1)
  - _Requirements: 1.1, 1.3, 2.1, 4.1, 4.2_
