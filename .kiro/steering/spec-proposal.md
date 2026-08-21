# Spec Proposal — .kiro/specs/ Directory List

> Cluster Feature Inventory (F01-F37) into Specs considering boundaries, dependencies, and independent deliverability. kebab-case, 2-4 words.

## Proposal (Recommended 7 Specs + 1 Infra)

| # | Directory | Covers Features | Responsibility / Boundary | Depends On | Size |
|---|-----------|----------------|---------------------------|------------|------|
| 1 | `frontend-shell` | F01, F02, F03, F11, F12, F13 | Single-page UI (video two-pane, controls/status/log), CSS layout, static delivery. Integrates `static/index.html` and static `server.py:135,150,146`. Boundary: appearance and DOM structure only. No logic | none | S |
| 2 | `session-provisioning` | F15, F16, F17, F18, F19, F32 | REST layer for Vonage/Anam session/token issuance + Vonage client creation and env/private-key handling. Owns contract for `POST /api/anam/session-token`, `POST /api/vonage/session`. Boundary: auth token issuance and env validation only. No Audio Connector | none | M |
| 3 | `audio-connector-bridge` | F20, F21 | Audio Connector lifecycle and `/ws` WebSocket bridge. `_active_connectors`, `VonageFrameSerializer`, `FastAPIWebsocketTransport`, keepalive. Boundary: converts Vonage audio to Pipecat frames | `session-provisioning` | M |
| 4 | `voice-pipeline-core` | F25, F26, F27, F28, F29, F30, F31 | Pipecat voice pipeline core. STT/VAD/LLM/Context Aggregator/Pipeline/Worker/Monkey-patch covering `bot.py:112-202`. Boundary: conversion logic from audio input to LLM text output. Does not own Transport/Bridge | `audio-connector-bridge` | L |
| 5 | `text-bridge-avatar` | F22, F23, F24, F06, F07 | LLM text delivery to browser and Anam rendering. Server `/ws-anam` + `LLMTextBridgeProcessor`/`LLMTextForwarder` + frontend Anam SDK (init/talk stream). Boundary: bridge contract `LLM Text → Avatar TTS/video` via `{type: llm_text/llm_end}` | `voice-pipeline-core` | M |
| 6 | `vonage-media-frontend` | F08, F09, F10 | Frontend Vonage media. `OT.initSession/connect`, dual publishers, subscriber covering `static/script.js:97-216` media part. Boundary: only media send/receive in Vonage session. No orchestration | `session-provisioning`, `text-bridge-avatar` | M |
| 7 | `connection-lifecycle` | F04, F05, F33, part of F08 | 5-step connection/disconnection orchestration, state management, error handling, keepalive, logging. Full `connect()/disconnect()` plus `lifespan/CORS/loguru`. Boundary: owns user's experience `Connect click → In conversation → Disconnect`. Delegates individual module details | `frontend-shell`, `session-provisioning`, `vonage-media-frontend`, `text-bridge-avatar` | M |
| 8 | `ops-deployment` | F14, F34, F35, F36, F37 | Operations/deployment. Health check, tunnel startup script, Docker, dependency management. `start.sh`, `Dockerfile`, `docker-compose.yml`, `pyproject.toml`, `GET /health`. Boundary: how to start/operate/publish. No app logic | `session-provisioning` | S |

## Dependency Graph (Recommended Implementation Order)

```
Wave 1 (parallel):  frontend-shell, session-provisioning, ops-deployment
Wave 2:             audio-connector-bridge (←session-provisioning)
Wave 3:             voice-pipeline-core (←audio-connector-bridge)
Wave 4:             text-bridge-avatar (←voice-pipeline-core)
Wave 5:             vonage-media-frontend (←session-provisioning, text-bridge-avatar)
Wave 6:             connection-lifecycle (←all) — integrated E2E
```

## Alternative (Coarser 5 Specs Integration)

| Directory | Integration | When to Choose |
|-----------|-------------|----------------|
| `frontend-app` | Merge `frontend-shell` + `vonage-media-frontend` + `connection-lifecycle` | Want frontend in one Spec. But tends to 20+ tasks |
| `backend-api` | Merge `session-provisioning` + `audio-connector-bridge` + `ops-deployment` | Want backend in one Spec |
| `voice-pipeline` | Merge `voice-pipeline-core` + `text-bridge-avatar` | Want pipeline fully integrated |

> Recommended: 7 Specs (+1 infra) covering Wave 1-6. Each Spec fits 8-15 tasks, enabling parallel implementation and review. 5-Spec alternative is simpler but each Spec bloats and review load increases.

## Example Next Commands

```bash
# Sequential from Wave 1
/kiro-spec-init "frontend shell — single page layout and static serving"
/kiro-spec-init "session provisioning — Vonage and Anam token APIs"
/kiro-spec-init "audio connector bridge — Audio Connector lifecycle and /ws"

# Or via Discovery for roadmap generation
/kiro-discovery "AI avatar voice pipeline: STT→LLM→Anam rendering with Vonage media"

# Quick generation (auto, review gate internal only)
/kiro-spec-quick "voice pipeline core --auto"
```

## Naming Notes

* kebab-case, lowercase, 2-4 words. Example: `session-provisioning` not `sessionProvisioning`
* No suffix `-2` needed as no existing specs
* Keep `spec.json.language` consistent to `en` for all specs
* This proposal traces to `feature-inventory.md` F01-F37 — requirements `Requirements` sections can reference `Fxx`

---
_Generated after full codebase scan. See `.kiro/steering/feature-inventory.md` for 37-feature source._
