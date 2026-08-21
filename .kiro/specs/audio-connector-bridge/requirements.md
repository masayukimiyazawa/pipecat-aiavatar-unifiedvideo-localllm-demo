# Requirements Document

## Introduction

Audio Connector Bridge is the boundary that relays Vonage Video audio to the server Pipecat pipeline. It integrates Audio Connector lifecycle management via `_connect_audio_connector_async` at `server.py:71` / `_stop_audio_connector_async` at `server.py:99` and the `WS /ws` endpoint at `server.py:227` (`VonageFrameSerializer` `server.py:234`, `FastAPIWebsocketTransport` `server.py:240`, 10-second keepalive `server.py:250`) to convert browser microphone audio into 16000Hz Pipecat frames and hand them to `voice-pipeline-core`.

## Boundary Context (Optional)
- **In scope**: Audio Connector creation/stop, `_active_connectors` management, `/ws` WebSocket acceptance and serialization, keepalive, Transport creation and delegation to `bot()`
- **Out of scope**: Vonage session/token issuance (`session-provisioning`), STT/LLM inference (`voice-pipeline-core`), text delivery (`text-bridge-avatar`), frontend OT operations
- **Adjacent expectations**: `session-provisioning` provides `session_id`/`token`/`ws_uri`, `voice-pipeline-core` consumes `transport` and executes `bot()`, `ops-deployment` supplies `VONAGE_AUDIO_RATE`

## Requirements

### Requirement 1: Audio Connector Lifecycle

**Objective:** As a server, I want exactly one Audio Connector running per session, so that duplicate relay or orphaned connectors are prevented

#### Acceptance Criteria
1. When `_connect_audio_connector_async(vng, session_id, ws_uri, audio_rate)` is called, the Audio Connector Bridge shall sequentially `await _stop_audio_connector_async(old_sid)` for all entries in `_active_connectors` (`server.py:74`) — note: this implements a global singleton (only one connector system-wide), not per-session isolation (implicit behavior now explicit)
2. When stop completes, the Audio Connector Bridge shall generate a token via `TokenOptions(session_id, role="publisher")` and build `AudioConnectorOptions(session_id, token, websocket=AudioConnectorWebSocket(uri=ws_uri, audio_rate=audio_rate, bidirectional=True))`
3. When `AudioConnectorOptions` is built, the Audio Connector Bridge shall start asynchronously via `run_in_executor(None, lambda: vng.video.start_audio_connector(audio_opts))`, store in `_active_connectors[session_id] = connector`, and log `Audio Connector started: id={connector.id}`
4. When `_stop_audio_connector_async(session_id)` is called and no matching connector exists, the Audio Connector Bridge shall return without action
5. When a stop target exists, the Audio Connector Bridge shall execute `DELETE /v2/project/{appId}/connect?sessionId={session_id}` via `run_in_executor` at `server.py:108` and on exception log `Failed to stop Audio Connector: {e}` via `logger.warning` without propagating — note: uses raw `_http_client.delete` bypassing SDK; should migrate to `vng.video.stop_audio_connector` when available (legacy flagged)
6. If `run_in_executor` for `start_audio_connector` throws, then the Audio Connector Bridge shall not register in `_active_connectors` and shall propagate the exception

### Requirement 2: /ws WebSocket Endpoint

**Objective:** As a Vonage Audio Connector, I want to connect to `/ws` via WebSocket to exchange audio frames, so that the server Pipecat can process audio

#### Acceptance Criteria
1. When Vonage Audio Connector connects to `WS /ws`, the Audio Connector Bridge shall `await websocket.accept()` and log `Client connected to /ws`
2. When the connection is established, the Audio Connector Bridge shall obtain `int(os.getenv("VONAGE_AUDIO_RATE","16000"))` and create `VonageFrameSerializer(InputParams(vonage_sample_rate=sample_rate))`
3. When Transport is needed, the Audio Connector Bridge shall create `FastAPIWebsocketTransport(websocket, FastAPIWebsocketParams(audio_in_enabled=True, audio_out_enabled=True, audio_out_10ms_chunks=2, serializer=serializer))` — `audio_out_10ms_chunks=2` yields 20ms chunks (implicit rule now explicit)
4. While the `/ws` session continues, the Audio Connector Bridge shall `websocket.send_text` every 10 seconds with `{"event":"keepalive"}` and break the loop on send failure (`server.py:250`) — Vonage requires keepalive within 30s or it closes the connector (implicit rule now explicit)
5. When `bot(runner_args, transport)` throws, the Audio Connector Bridge shall log via `logger.exception("Pipecat bot error: {e}")` and execute `keepalive_task.cancel()` and `transport.cleanup()` before logging `WebSocket endpoint cleaned up`
6. When `VONAGE_AUDIO_RATE` env changes after startup, the Audio Connector Bridge shall use the value at connection time per `/ws` request, not the value from `POST /api/vonage/session` (edge case: rate mismatch between connector and serializer now explicit)

### Requirement 3: Audio Rate and Serialization

**Objective:** As a developer, I want the sample rate between Vonage and Pipecat unified, so that audio distortion and STT accuracy degradation are prevented

#### Acceptance Criteria
1. When `VONAGE_AUDIO_RATE` is `16000`, the Audio Connector Bridge shall align `VonageFrameSerializer` input rate with `PipelineParams(audio_in_sample_rate, audio_out_sample_rate=16000)`
2. When `audio_out_10ms_chunks` is `2`, the Audio Connector Bridge shall output 20ms audio chunks
3. If `VONAGE_AUDIO_RATE` is non-numeric, then the Audio Connector Bridge shall delegate the exception to `session-provisioning` 500 handling and not establish `/ws`
4. The Audio Connector Bridge shall treat 16000 Hz as the canonical rate; other rates (8000/48000) shall be rejected or resampled — current code at `server.py:233` accepts any int without validation (gap flagged)

### Requirement 4: Concurrent Connections and Resource Management

**Objective:** As a system, I want Audio Connectors not to leak across multiple sessions, so that connector count does not diverge during long operation

#### Acceptance Criteria
1. When `_connect_audio_connector_async` is called with a new `session_id`, the Audio Connector Bridge shall always stop all old `session_id` connectors before starting the new one — this enforces global singleton, so concurrent users share one connector (limitation now explicit)
2. While `/ws` is connected, the Audio Connector Bridge shall create `WebSocketRunnerArguments(websocket, body={})` and pass to `bot()`, guaranteeing `worker.cancel` on disconnect
3. The Audio Connector Bridge shall note that `_active_connectors` at `server.py:68` is a plain `dict` without locking — concurrent `POST /api/vonage/session` may race on `list(_active_connectors.keys())` (legacy flagged for `asyncio.Lock`)
4. The Audio Connector Bridge shall note that connectors are never cleaned on server shutdown via `lifespan` — `lifespan` at `server.py:126` should iterate `_active_connectors` and stop all on shutdown (gap flagged)

### Requirement 5: Non-Functional, Security, and Constraints

**Objective:** As an operator, I want Audio Connector Bridge to be secure and observable, so that audio relay failures are detected early

#### Acceptance Criteria
1. The Audio Connector Bridge shall not log `private_key` or `token`; only `session_id` and `connector.id` shall be logged at INFO
2. The Audio Connector Bridge shall execute Vonage synchronous calls via `run_in_executor` without blocking the FastAPI event loop
3. When `ws_uri` is not `wss://` (plain `ws://`), the Audio Connector Bridge shall allow it only for development (localhost) and log a warning assuming `session-provisioning` enforces `wss` in production — current code at `server.py:71` does not log; requirement now mandates warning
4. If an invalid frame arrives at `/ws`, then the Audio Connector Bridge shall not swallow `VonageFrameSerializer` exceptions but record via `logger.exception` and clean up Transport
5. The Audio Connector Bridge shall always specify `bidirectional=True` so future server→Vonage audio return (`transport.output`) is not blocked — current hardcode at `server.py:86` is intentional for future TTS back-channel
6. The Audio Connector Bridge shall note that `_stop_audio_connector_async` at `server.py:100` re-creates a Vonage client via `_get_video_client()` per call (re-reading env/keys) — shall be refactored to reuse the `vng` instance passed to `_connect` (legacy flagged)
