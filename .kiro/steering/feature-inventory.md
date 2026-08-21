# Feature Inventory — pipecat-aiavatar-unifiedvideo-localllm-demo

> Exhaustive feature extraction via full codebase scan. Evidence: `server.py`, `bot.py`, `static/*`, `start.sh`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`.

## 1. Screen / UI

| # | Feature | Category | Location | Description |
|---|---------|----------|----------|-------------|
| F01 | Single-page layout | Screen | `static/index.html:33` | `video-row` two-pane (left: You / right: AI Avatar), `#subscriberContainer` hidden, responsive 960px centered |
| F02 | Connection controls | Screen | `static/index.html:52`, `static/script.js:6` `connectBtn` | Connect/disconnect toggle, status `statusEl`, log `logEl` |
| F03 | Video display | Screen | `static/index.html:19` `anam-avatar` video + `static/script.js:84` `srcObject` | Render Anam MediaStream in `<video autoplay playsinline>` with `object-fit: cover` |

## 2. Frontend Logic

| # | Feature | Category | Location | Description |
|---|---------|----------|----------|-------------|
| F04 | Connection orchestration | Module | `static/script.js:29` `connect()` | 5-step: ①Anam token fetch ②Vonage session creation ③Anam init ④Vonage connect+dual publish ⑤/ws-anam connect. Each step with `fetch` + error handling + status/log updates |
| F05 | Disconnect & cleanup | Module | `static/script.js:272` `disconnect()` | wsAnam close, session.unpublish, session.disconnect, stream tracks stop, anamClient stopStreaming, state reset |
| F06 | Anam SDK lifecycle | Module | `static/script.js:67` `createClient` | `disableInputAudio:true`, `SESSION_READY/CONNECTION_CLOSED` listeners, `client.stream()`→MediaStream |
| F07 | Anam text streaming | Module | `static/script.js:226` `handleLLMText/handleLLMEnd/handleInterrupt` | `createTalkMessageStream().streamMessageChunk(text,false)/endMessage`, `isActive` guard, `interruptPersona` |
| F08 | Vonage session/connection | Module | `static/script.js:97` `OT.initSession` | `session.connect(token)`, `streamCreated`→exclude self→`session.subscribe(audioOnly:true)`, `streamDestroyed` handling |
| F09 | Dual publisher | Module | `static/script.js:131` `createAndPublish` | Promise-wrapped `OT.initPublisher`+`session.publish`. ①User cam+mic→`userVideoContainer` ②Avatar MediaStream(Video/AudioTrack)→hidden div |
| F10 | ws-anam client | Module | `static/script.js:180` `wsAnam` | Auto-select `wss/ws`, `onmessage`→`llm_text/llm_end` dispatch, `onclose/onerror`, 15s `ping` keepalive |

## 3. Backend REST API

| # | Feature | Category | Endpoint | Location | Description |
|---|---------|----------|----------|----------|-------------|
| F11 | Static delivery | API | `GET /` | `server.py:150` | `FileResponse static/index.html` |
| F12 | Static assets | API | `GET /static/*` | `server.py:135` `StaticFiles` | Serve `static/` directory |
| F13 | favicon | API | `GET /favicon.ico` | `server.py:146` | 204 No Content |
| F14 | Health check | API | `GET /health` | `server.py:155` | `{"ok": true}` (used for wait in start.sh) |
| F15 | Anam token issuance | API | `POST /api/anam/session-token` | `server.py:160` | Proxy to `https://api.anam.ai/v1/auth/session-token`. `personaConfig(avatarId/voiceId/llmId/CUSTOMER_CLIENT_V1)` + `sessionOptions(timeout 3600)`. 502 on failure |
| F16 | Vonage session issuance | API | `POST /api/vonage/session` | `server.py:194` | `create_session`→`AudioConnector` connect→`generate_client_token(publisher)` return. Auto-derive `WS_URI` from `host` (`wss/ws`) if env missing |

## 4. Backend WebSocket / Vonage Integration

| # | Feature | Category | Endpoint/Function | Location | Description |
|---|---------|----------|-------------------|----------|-------------|
| F17 | Vonage client creation | Module | `_create_vonage_client`/`_get_video_client` | `server.py:44`, `119` | `Auth(appId, privateKey)` + `HttpClientOptions(video_host, timeout30)`, PEM string/file path dual support via `_read_private_key` |
| F18 | Session creation | Module | `_create_session_async` | `server.py:59` | Offload sync SDK via `run_in_executor` |
| F19 | Token generation | Module | `_generate_client_token` | `server.py:50` | `TokenOptions(session_id, role=publisher)`, bytes/str normalization |
| F20 | Audio Connector control | Module | `_connect_audio_connector_async`/`_stop_audio_connector_async` | `server.py:71`, `99` | Stop existing connectors→`AudioConnectorWebSocket(uri, rate, bidirectional:true)`→`start_audio_connector`. Manage via `_active_connectors` dict, stop via `DELETE /v2/project/{id}/connect?sessionId=` |
| F21 | Audio WebSocket (/ws) | WS | `WS /ws` | `server.py:227` | `VonageFrameSerializer`, `FastAPIWebsocketTransport(audio_in/out, chunks2)`, 10s `keepalive` text, delegate to `bot()` via `WebSocketRunnerArguments` |
| F22 | Text WebSocket (/ws-anam) | WS | `WS /ws-anam` | `server.py:271` | `LLMTextBridgeProcessor.add_client`, initial greeting `Hello...` + `llm_end`, `ping→pong`, `remove_client` on disconnect |

## 5. Pipecat Voice Pipeline

| # | Feature | Category | Location | Description |
|---|---------|----------|----------|-------------|
| F23 | LLM Text Bridge Processor | Module | `bot.py:54` `LLMTextBridgeProcessor` | Manage `set[WebSocket]`, `broadcast_text/end` with JSON `llm_text/llm_end`, discard on disconnect |
| F24 | LLM Text Forwarder | Module | `bot.py:96` `LLMTextForwarder` | Capture `TextFrame`/`LLMFullResponseEndFrame` via `FrameProcessor`→bridge→`push_frame` |
| F25 | STT (Whisper) | Module | `bot.py:132` `WhisperSTTServiceMLX` | `MLXModel.LARGE_V3_TURBO_Q4`, `Language(ja)`, `no_speech_prob 0.3`, Apple Silicon optimized |
| F26 | VAD | Module | `bot.py:8` `SileroVADAnalyzer` | `VADParams(confidence0.7, start0.3s, stop0.8s, min_volume0.4)`, `audio_idle_timeout2.0`, `user_turn_stop_timeout5.0` |
| F27 | LLM (LM Studio) | Module | `bot.py:118` `OpenAILLMService` | `base_url` LM_STUDIO_BASE_URL, `model` LM_MODEL, system instruction: 2-3 sentences natural Japanese, no markdown/symbols/English |
| F28 | Context aggregation | Module | `bot.py:140` `LLMContext`/`LLMContextAggregatorPair` | `user_aggregator`/`assistant_aggregator`, VAD integration, conversation history |
| F29 | Pipeline assembly | Module | `bot.py:160` `Pipeline` | 7 elements `[transport.input, stt, user_aggregator, llm, assistant_aggregator, text_forwarder, transport.output]` |
| F30 | Pipeline execution | Module | `bot.py:172` `PipelineWorker`/`WorkerRunner` | `PipelineParams(audio_in/out 16000, metrics)`, `on_client_connected/disconnected`→`worker.cancel`, `Runner.add_workers→run` |
| F31 | Forwarding Monkey-patch | Module | `bot.py:34` | Wrap `LLMAssistantAggregator._handle_text/_handle_llm_end` to add `push_frame(DOWNSTREAM)` (default Pipecat does not forward to TTS) |

## 6. Infra / Operations

| # | Feature | Category | Location | Description |
|---|---------|----------|----------|-------------|
| F32 | Env config | Module | `server.py:25`, `bot.py:32`, `.env.example:1` | `load_dotenv(override=True)`, `_require_env` 500 fail-fast, `VONAGE_PRIVATE_KEY` supports PEM or path |
| F33 | CORS/lifecycle | Module | `server.py:126`, `137` | `CORSMiddleware allow_origins *`, `lifespan` startup/shutdown log, `loguru` |
| F34 | Cloudflare Tunnel startup | Module | `start.sh:8` | `cloudflared tunnel --url :8005` background, poll 30s for `https://*.trycloudflare.com`, print URL and `WS_URI` |
| F35 | Server startup management | Module | `start.sh:36` | Free port via `lsof -ti:8005`→`nohup uv run python server.py`→wait 30s for `curl /health` |
| F36 | Dockerization | Module | `Dockerfile:1`, `docker-compose.yml:1` | `python:3.13-slim`, `uv pip install`, `EXPOSE 8005`, compose propagates `WS_URI` and mounts `private.key` volume |
| F37 | Dependency management | Module | `pyproject.toml:1`, `uv.lock` | `pipecat-ai[mlx-whisper,openai,silero,websocket]>=1.4.0`, `vonage`, `vonage-video`, `fastapi`, `uvicorn`, `anam` |

---
_Total 37 features (Screen 3, Frontend 7, REST 6, WS/Vonage 6, Pipeline 9, Infra 6) — Each Spec can trace to Feature IDs in Requirements Traceability_
