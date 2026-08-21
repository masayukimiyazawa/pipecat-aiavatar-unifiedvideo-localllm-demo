# Implementation Plan

- [x] 1. Fix `/ws-anam` greeting and coupling debt
- [x] 1.1 Keep hardcoded greeting while documenting configurability (P)
  - Ensure `WS /ws-anam` at `server.py:271` does `accept`, `bridge.add_client`, then `send_json {"type":"llm_text","text":"こんにちは。私はAIアバターアシスタントです。何かお手伝いできますか？"}` + `{"type":"llm_end"}` at `284-285`; add TODO comment to make `GREETING_TEXT` env configurable vs LLM-generated
  - Verify `TestClient` WebSocket `/ws-anam` immediately receives greeting and `llm_end`
  - _Requirements: 1.1, 1.2, 1.5, 1.6_
  - _Boundary: WsAnamEndpoint_
- [x] 1.2 Decouple `LLMTextBridgeProcessor` from `fastapi.WebSocket` (P)
  - Introduce `Protocol` `HasSendJson` with `send_json` and change `LLMTextBridgeProcessor._clients: set[HasSendJson]` at `bot.py:60`; keep runtime `WebSocket` but type via Protocol; remove direct `from fastapi import WebSocket` import if possible or keep for `add_client` signature but document coupling
  - Test still passes with mock `HasSendJson`
  - _Requirements: 6.5_
  - _Boundary: BridgeProcessor_

- [ ] 2. Implement fan-out bridge with silent-discard fix
- [ ] 2.1 Implement `LLMTextBridgeProcessor` broadcast with discard and logging
  - Ensure `broadcast_text(text)` at `68` loops `await ws.send_json({"type":"llm_text","text":text})` and collects failed `ws` into `disconnected` then `discard` after loop; same for `broadcast_end` at `78`; add optional debug log count of discarded (non-breaking)
  - Verify two mock `WebSocket` where one raises → other still receives and failed one `discard`ed
  - _Requirements: 2.3, 2.4, 2.5, 2.6, 6.3_
  - _Boundary: BridgeProcessor_
- [ ] 2.2 Implement `LLMTextForwarder` capture order
  - Ensure `process_frame` at `103` calls `await super().process_frame`, then if `TextFrame` → `broadcast_text(frame.text)` at `106`, if `LLMFullResponseEndFrame` → `broadcast_end` at `108`, then `push_frame(frame, direction)` at `109`; ensure singleton `_text_bridge` at `89` via `get_text_bridge()`
  - Observable: pipeline `TextFrame("hi")` → bridge receives before downstream
  - _Requirements: 2.1, 2.2, 2.5_
  - _Boundary: TextForwarder_
  - _Depends: 2.1_

- [ ] 3. Wire Anam SDK initialization
- [ ] 3.1 Ensure `createClient` with `disableInputAudio:true` and `stream()` (P)
  - Verify `createClient(anamToken, {disableInputAudio:true})` at `67` and listeners `SESSION_READY`/`CONNECTION_CLOSED` at `71`; `await anamClient.stream()` → `anamVideo.srcObject` → `play()` at `80-85`; on error log `Anam initialization error` and degrade to audio-only (text fallback)
  - Test `createClient` called with `disableInputAudio:true` true
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Boundary: AnamSdkInit_
- [ ] 3.2 Handle empty `anamStream` tracks edge
  - Ensure `getVideoTracks/getAudioTracks` empty → skip avatar publish (coordinated with `vonage-media-frontend` at `155`); no `createAndPublish` call
  - _Requirements: 3.5, 6.5_
  - _Boundary: AnamSdkInit_
  - _Depends: 3.1_

- [ ] 4. Implement TTS streaming with guard and dead-code flag
- [ ] 4.1 Ensure `handleLLMText` lazy stream and `handleLLMEnd` guard (P)
  - Ensure `handleLLMText` at `229` reuses `currentTalkStream` (create if null via `createTalkMessageStream()` then `streamMessageChunk(text,false)` at `236`); fallback to `log('LLM: {text}')` if `!anamClient` at `231`; `handleLLMEnd` at `244` checks `isActive()` then `endMessage()` and `null`
  - Test `streamMessageChunk` throw → log `Anam stream error` without clearing `currentTalkStream`
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Boundary: AnamTtsStreaming_
- [ ] 4.2 Flag `handleInterrupt` dead code and keep `isActive` contract
  - Keep `handleInterrupt` at `256` that `endMessage` then `interruptPersona()`; add comment dead code never invoked and reference VAD interrupt future wiring vs removal decision
  - No functional change
  - _Requirements: 4.5, 4.6_
  - _Boundary: AnamTtsStreaming_

- [ ] 5. Fix ws-anam client keepalive leak
- [ ] 5.1 Store interval ID and clear on disconnect
  - Change `setInterval(() => { if (wsAnam.readyState===OPEN) wsAnam.send('ping') }, 15000)` at `210` to `let wsAnamPingId = setInterval(...);` and export `wsAnamPingId` for `connection-lifecycle` `disconnect()` to `clearInterval(wsAnamPingId)`; ensure `wsAnam.onclose` also clears if present
  - Verify `disconnect()` after full connect no longer leaves interval (mock `setInterval` count goes 0)
  - _Requirements: 5.5, 5.6_
  - _Boundary: WsAnamClient_
  - _Depends: 3.1_

- [ ] 6. Enforce `/ws-anam` ping/pong and security contracts
- [ ] 6.1 Verify `wsProto` auto and event logs plus `ping→pong` (P)
  - Ensure `wsProto = location.protocol==='https:' ? 'wss:' : 'ws:'` at `181` and `new WebSocket(.../ws-anam)`; `onopen`→`log Anam WS connected` at `184`, `onclose`→`log Anam WS disconnected` at `201`, `onerror`→`log Anam WS error` at `205`; server `receive_text` `"ping"`→`"pong"` at `292`
  - Test JSON `{"type":"ping"}` ignored (plain text required) as per Requirement 1.3
  - _Requirements: 1.3, 5.1, 5.2, 5.3, 5.4, 5.5, 6.1_
  - _Boundary: WsAnamClient, WsAnamEndpoint_
- [ ] 6.2 Verify `anamToken` memory-only and `textContent` XSS-safe
  - Ensure `let anamToken` at `35` only memory, never `localStorage`; `d.textContent` at `21` for log not `innerHTML`
  - _Requirements: 6.1, 6.2, 6.4_
  - _Boundary: WsAnamClient_

- [ ]* 7. Optional multi-tab fan-out verification
  - Two `TestClient` `/ws-anam` → pipeline `TextFrame("hi")` → both receive `llm_text` with same text
  - _Requirements: 2.3, 6.3_
