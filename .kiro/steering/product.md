# Product Overview

Real-time voice-and-video AI avatar assistant. A user speaks to an AI avatar via the browser; the avatar responds with spoken Japanese and lip-synced animation. The system bridges Vonage Video for real-time media transport, a local LLM (LM Studio) for conversational intelligence, on-device Whisper STT, and Anam.ai cloud rendering for avatar TTS/animation.

## Core Capabilities

* **Voice-driven conversation**: Browser mic → Vonage Audio Connector → Pipecat pipeline (Silero VAD → mlx-whisper STT → local LLM) → avatar speech. Keeps responses to 2-3 natural Japanese sentences (`bot.py:122` system instruction).
* **Lip-synced avatar rendering**: LLM text is forwarded over a dedicated WebSocket bridge (`/ws-anam` in `server.py:271`) and fed to the Anam.ai JS SDK (`static/script.js:1` `createClient` + `createTalkMessageStream`) which handles both TTS and facial animation in the browser.
* **Unified video session**: User webcam+mic and avatar video+audio are both published into a single Vonage Video session (`static/script.js:131` `createAndPublish`), enabling recording, unified transport, and optional Audio Connector echo-back.
* **On-demand session provisioning**: Backend creates Vonage sessions/tokens and Anam session tokens on request (`server.py:160` `/api/anam/session-token`, `server.py:194` `/api/vonage/session`), and manages the Audio Connector lifecycle (`server.py:71` `_connect_audio_connector_async`).

## Target Use Cases

* **Demo / PoC for avatar assistants**: Showcase that a fully local LLM + local STT can drive a cloud avatar without server-side TTS.
* **Japanese conversational agent**: Primary interaction language is Japanese (`bot.py:51` `STT_LANGUAGE=ja`, greeting `こんにちは。私はAIアバターアシスタントです...` in `server.py:284`).
* **Realtime support / reception kiosk**: Single-page UI (`static/index.html:2`) with left=user video, right=avatar video, single connect/disconnect control — suitable for reception or guided assistance scenarios.

## Value Proposition

* **Privacy & cost**: LLM inference and STT run locally (LM Studio OpenAI-compatible API at `localhost:1234`, `mlx-whisper` on Apple Silicon); only avatar rendering hits the cloud. No server-side TTS hosting.
* **Low-latency voice UX**: Silero VAD (`bot.py:145` confidence 0.7, stop 0.8s) + streaming LLM → incremental `TextFrame` forwarding (`bot.py:96` `LLMTextForwarder`) → chunked `streamMessageChunk` to Anam avoids waiting for full response.
* **Minimal integration surface**: Vonage Video is the single media backbone; Audio Connector WebSocket (`/ws` in `server.py:227`) is the only server media ingress, and `/ws-anam` is the only LLM→avatar bridge. Option A (browser MediaStream publish) was chosen over Experience Composer because EC lacks GPU for WebGL avatar rendering (`README.md:160`).

## Architecture Overview

End-to-end flow spans three planes: Browser (media + avatar rendering), Vonage Cloud (session + Audio Connector relay), and Server (REST session provisioning + Pipecat voice pipeline). Public exposure is via Cloudflare Tunnel (`start.sh:13`).

```
[Browser static/index.html + script.js]
  ├─ OT publisher (user cam+mic → Vonage session)
  ├─ Anam SDK (avatar video/audio ← cloud rendering)
  ├─ Anam publisher (avatar MediaStream → Vonage session, hidden div)
  └─ /ws-anam client (LLM text → Anam TTS)
        ↕ HTTPS/WSS via Cloudflare Tunnel
[Vonage Video Cloud]
  ├─ Session + Token API
  └─ Audio Connector (bidirectional WebSocket → server /ws)
        ↕
[Server FastAPI server.py]
  ├─ REST: POST /api/anam/session-token, POST /api/vonage/session, GET /health, GET /
  ├─ WS /ws → VonageFrameSerializer + Pipecat Pipeline (bot.py)
  └─ WS /ws-anam → LLMTextBridgeProcessor broadcast
[Pipecat Pipeline bot.py]
  transport.input → Silero VAD → WhisperSTT (mlx) → LLMContextAggregator → OpenAI LLM (LM Studio) → LLMAssistantAggregator → LLMTextForwarder → transport.output
```

Audio path: mic → OT → Vonage → `/ws` → STT → LLM → `/ws-anam` → Anam SDK → avatar speech + optional Pipecat audio out → Vonage → subscriber. Video path: user publisher (left panel) and Anam publisher (hidden, for recording) plus local avatar video element (`static/index.html:45` `anam-avatar`).

## Main Components / Modules

| Component | Location | Responsibility | Key Interface |
|-----------|----------|----------------|---------------|
| **Frontend Shell** | `static/index.html:1` | Single-page layout, two video panels, controls/status/log | DOM `userVideoContainer`, `anam-avatar`, `connectBtn` |
| **Frontend Orchestrator** | `static/script.js:29` `connect()` / `disconnect()` | 5-step connection sequence, state machine (`isConnected`), error handling | `fetch /api/anam/session-token`, `fetch /api/vonage/session`, `OT.initSession`, `createClient` |
| **Anam Integration** | `static/script.js:67` + `server.py:160` | Token proxy, SDK init, talk stream chunking, interrupt | `AnamEvent.SESSION_READY`, `createTalkMessageStream().streamMessageChunk/endMessage`, `interruptPersona` |
| **Vonage Session & Media** | `static/script.js:96` + `server.py:44` | Session create, token generation, dual publish, subscribe | `OT.initPublisher`, `session.publish/subscribe`, `TokenOptions(role=publisher)` |
| **Audio Connector Bridge** | `server.py:71` `_connect_audio_connector_async`, `server.py:227` `/ws` | Bidirectional audio relay, keepalive, serializer | `AudioConnectorWebSocket(uri, rate, bidirectional)`, `VonageFrameSerializer`, `FastAPIWebsocketTransport` |
| **Text Bridge** | `server.py:271` `/ws-anam` + `bot.py:54` `LLMTextBridgeProcessor` | LLM text fan-out to browser, greeting, ping/pong | `{"type":"llm_text"}` / `{"type":"llm_end"}`, `broadcast_text/end` |
| **Voice Pipeline** | `bot.py:112` `run_bot` | VAD → STT → LLM → forwarding, turn management | `Pipeline([transport.input, stt, user_aggregator, llm, assistant_aggregator, text_forwarder, transport.output])` |
| **STT / VAD / LLM Services** | `bot.py:132`, `bot.py:145`, `bot.py:118` | Speech recognition (ja), voice activity detection, conversational generation | `WhisperSTTServiceMLX(LARGE_V3_TURBO_Q4, ja)`, `SileroVADAnalyzer(0.7/0.3s/0.8s)`, `OpenAILLMService(base_url, model)` |
| **Ops / Infra** | `start.sh:1`, `Dockerfile:1`, `docker-compose.yml:1` | Tunnel, server lifecycle, containerization, env handling | `cloudflared tunnel --url :8005`, `uv run python server.py`, `WS_URI` |

---
_Focus on patterns and purpose, not exhaustive feature lists_
