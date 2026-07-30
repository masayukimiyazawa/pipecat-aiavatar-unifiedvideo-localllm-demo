# AI Avatar Assistant — Vonage Video + Anam.ai + Local LLM

A real-time voice-and-video AI avatar assistant. Users speak to an AI-powered avatar through a browser; the avatar responds with voice and lip-synced animation.

## Architecture Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                        Browser (static/)                        │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────┐ │
│  │ User Web │    │  Anam.ai SDK  │    │  /ws-anam WebSocket   │ │
│  │ Cam + Mic│    │  (avatar vid) │    │  (LLM text→Anam TTS)  │ │
│  └────┬─────┘    └──────┬───────┘    └───────────┬────────────┘ │
│       │                 │                         │              │
│       ▼                 ▼                         ▼              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │            Vonage OpenTok JS SDK (OT.initSession)         │   │
│  │    publish(user webcam+mic) / publish(Anam video+audio)   │   │
│  │    subscribe(Audio Connector stream)                      │   │
│  └────────────────────────┬─────────────────────────────────┘   │
└───────────────────────────┼─────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │    Cloudflare Tunnel       │
              │  (public HTTPS/WSS URL)    │
              └─────────────┬─────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                    Server (FastAPI / Uvicorn)                    │
│                                                                  │
│  ┌─────────────┐     ┌──────────────────────────────────────┐  │
│  │ Vonage Video │     │     /ws (Audio Connector)             │  │
│  │ API (REST)   │     │     ┌────────────────────────────┐   │  │
│  │              │     │     │      Pipecat Pipeline       │   │  │
│  │ • Session    │     │     │                              │   │  │
│  │ • Token      │     │     │  Audio In → STT (Whisper)   │   │  │
│  │ • Audio      │─────┼──→  │           → LLM (LM Studio) │   │  │
│  │   Connector  │     │     │           → Text Forwarder  │──┼──┼──→ /ws-anam
│  └─────────────┘     │     │           → Audio Out        │   │  │
│                      │     └────────────────────────────┘   │  │
│                      └──────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  REST API Endpoints                                      │  │
│  │  POST /api/anam/session-token  — Anam auth token         │  │
│  │  POST /api/vonage/session      — Create session+connector│  │
│  │  GET  /health                  — Health check             │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## Audio / Video Flow

### Audio Path
1. **User → Server**: Browser mic → OT publisher → Vonage session → Audio Connector → WebSocket (`/ws`) → Pipecat STT (`mlx-whisper`)
2. **Server → Anam Avatar**: STT text → LLM (LM Studio) → LLM text → `/ws-anam` WebSocket → Anam.ai JS SDK (TTS + lip-sync)
3. **Server → User (optional)**: LLM response → Pipecat audio out → WebSocket → Audio Connector → Vonage session → browser subscriber

The Anam.ai SDK handles **both TTS and avatar animation** — the LLM text output is streamed to the browser via a separate WebSocket bridge (`/ws-anam`), and the Anam SDK renders it as spoken audio with synchronized facial animation.

### Video Display
- **Left panel**: User's webcam (published to Vonage via OT publisher, shown locally)
- **Right panel**: AI avatar video (rendered by Anam.ai JS SDK, streamed from Anam cloud)

## Pipeline Components

| Stage         | Technology                          | Location        |
|---------------|-------------------------------------|-----------------|
| Speech-to-Text| `mlx-whisper` (MLX, Apple Silicon)  | `bot.py`        |
| LLM           | LM Studio (local, OpenAI-compatible)| `bot.py`        |
| Text Bridge   | WebSocket (`/ws-anam`)              | `server.py`     |
| VAD           | Silero VAD                          | `bot.py`        |
| Avatar TTS    | Anam.ai cloud (JS SDK in browser)   | `script.js`     |
| Session Mgmt  | Vonage Video API                    | `server.py`     |
| Audio Relay   | Vonage Audio Connector              | `server.py`     |

## Prerequisites

- Python 3.11+
- [LM Studio](https://lmstudio.ai/) running locally with an LLM model loaded (OpenAI-compatible API server on `localhost:1234`)
- Apple Silicon Mac (for MLX-accelerated Whisper STT; optional otherwise)
- Vonage Video API account (application ID + private key)
- Anam.ai account (API key, avatar ID, voice ID)
- [Cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) tunnel CLI

## Setup

1. **Clone and install**
   ```bash
   git clone <repo>
   cd pipecat-aiavatar-unifiedvideo-localllm-demo
   uv sync
   ```

2. **Configure environment** — copy the template and fill in your credentials:
   ```bash
   cp .env.example .env
   ```
   Required variables:
   - `VONAGE_APPLICATION_ID` — Vonage Video API application ID
   - `VONAGE_PRIVATE_KEY` — Path to your Vonage application private key
   - `ANAM_API_KEY` — Anam.ai API key
   - `ANAM_AVATAR_ID` — Anam avatar ID
   - `ANAM_VOICE_ID` — Anam voice ID
   - `LM_STUDIO_BASE_URL` — Default: `http://localhost:1234/v1`
   - `LM_MODEL` — Model name loaded in LM Studio

3. **Start LM Studio**
   - Load your model
   - Start the inference server on port 1234

## Running

Use the provided startup script:

```bash
bash start.sh
```

This will:
1. Start a Cloudflare tunnel to expose your local server publicly
2. Start the Uvicorn server on port 8005
3. Print the public URL to open in your browser

### Manual Start

```bash
# Start Cloudflare tunnel
cloudflared tunnel --url http://localhost:8005 &

# Start the server
uv run python server.py
```

## Connecting

1. Open the printed URL in a browser
2. Click **接続** (Connect)
3. Grant camera and microphone permissions
4. The AI avatar will greet you: "こんにちは。私はAIアバターアシスタントです。何かお手伝いできますか？"
5. Start speaking — the system processes your speech through STT → LLM → avatar response

## Project Structure

```
├── server.py          # FastAPI server: REST APIs, WebSocket endpoints
├── bot.py             # Pipecat pipeline: STT → LLM → text forwarder
├── pyproject.toml     # Python dependencies
├── start.sh           # Tunnel + server startup script
├── .env               # Configuration (credentials)
├── private.key        # Vonage application private key
├── static/
│   ├── index.html     # Single-page UI
│   └── script.js      # Frontend logic: OT, Anam SDK, WebSocket bridge
└── README.md
```

## Key Technical Decisions

- **Option A (current)**: Publish Anam video+audio to Vonage via browser `MediaStream` — chosen over Option B (Experience Composer) because the EC server lacks a GPU for WebGL avatar rendering
- **`createAndPublish()` helper**: Wraps `OT.initPublisher` + `session.publish` in a Promise to ensure the stream exists before proceeding
- **Text bridge**: LLM text output is sent to the browser via a separate WebSocket (`/ws-anam`) and fed to the Anam SDK for TTS — this decouples LLM inference from avatar rendering
