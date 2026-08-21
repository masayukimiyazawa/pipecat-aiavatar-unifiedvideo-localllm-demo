# Implementation Plan

- [ ] 1. Fix optimistic state and boolean insufficiency
- [x] 1.1 Move `isConnected=true` to `wsAnam.onopen` and add `Connecting` guard (P)
  - Current at `219` sets `isConnected=true` immediately after `new WebSocket`; change to set inside `wsAnam.onopen` handler where `log Anam WS connected` at `184` occurs; until `onopen`, `isConnected` remains false and `status` stays `セッション作成中...`; add `Connecting` status handling comment referencing Requirement 3.7 enum future `Disconnected|Connecting|Connected|Failed`
  - Verify `connect()` with mocked `WebSocket` that never `onopen` does not set `isConnected=true` and `connectBtn` stays `disabled=true`
  - _Requirements: 1.6, 3.2, 3.7_
  - _Boundary: ConnectionState, ConnectionOrchestrator_
- [ ] 1.2 Make Step 1 Anam token failure degrade not abort (P)
  - Change `catch` at `42-46` from `return` abort to log `Anam token error` and continue to `POST /api/vonage/session` (audio-only degrade) aligning with Step 3 degrade at `87`; keep `setStatus('接続失敗')` only for Vonage Step 2 failure
  - Test Step 1 401 → still proceeds to Vonage `OT.initSession` and later `ws-anam` (with `anamClient` null fallback `log('LLM: text')`)
  - _Requirements: 2.1, 2.3_
  - _Boundary: ConnectionOrchestrator_

- [ ] 2. Implement 5-step orchestration verification
- [ ] 2.1 Verify each step maps to spec primitives
  - Ensure `fetch /api/anam/session-token` at `37` → `sessionToken`; `fetch /api/vonage/session` at `53` → `vonageData`; `createClient`/`stream` at `67-85` with `disableInputAudio:true`; `OT.initSession`/`session.connect`/`createAndPublish` at `97-164` (delegates to `vonage-media-frontend` but orchestrated); `new WebSocket(.../ws-anam)` at `182` with `wsProto` auto at `181`
  - Mock each `fetch` → check `log` sequence `Anam token obtained`→`Vonage session: ...`→`Anam avatar ready`→`Vonage session connected`→`Anam WS connected`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - _Boundary: ConnectionOrchestrator_
- [ ] 2.2 Keep Step 3 degrade and Step 4 abort semantics
  - Ensure Step 3 catch at `88` logs `Anam initialization error` and continues; Step 4 `session.connect` catch at `171` logs `Vonage connection error`, `setStatus('接続失敗')`, `disabled=false`, `return`
  - Observable: Step 3 throw does not set `Connection failed`; Step 4 throw does
  - _Requirements: 2.3, 2.4, 2.5_
  - _Boundary: ConnectionOrchestrator_

- [ ] 3. Implement state reflection and button toggle
- [ ] 3.1 Ensure `isConnected` and `statusEl` mapping plus initial log
  - Verify `let isConnected=false` at `18`, `connect()` entry `disabled=true` at `30` (no `isConnected` change per 3.1), `disconnect()` immediate `isConnected=false` at `275`, click listener `if (isConnected) disconnect() else connect()` at `311`, and initial `log('Ready...')` at `316`
  - Validate `statusEl` only four Japanese literals `切断されています`/`セッション作成中...`/`会話中...`/`接続失敗` at `31,44,59,220,299`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 5.4_
  - _Boundary: ConnectionState_

- [ ] 4. Fix disconnect cleanup including interval leak
- [ ] 4.1 Store ping interval ID and clear on disconnect
  - Change `setInterval(() => { if (wsAnam...send('ping')}, 15000)` at `210` to `let wsAnamPingId = setInterval(...,15000)` exported to `disconnect()`; in `disconnect()` add `clearInterval(wsAnamPingId)` before `wsAnam.close()` at `277`; ensure `wsAnamPingId = null` after clear
  - Test full connect then `disconnect()` → `setInterval` cleared (mock timer count 0)
  - _Requirements: 4.1, 6.3_
  - _Boundary: DisconnectionCleanup_
  - _Depends: text-bridge-avatar 5.1_
- [ ] 4.2 Verify exhaustive resource release order
  - Ensure `wsAnam.close`→`session.unpublish(anamPublisher)`→`unpublish(userPublisher)`→`session.disconnect`→`subscriber=null; session=null` at `282-287`; `anamStream.getTracks().forEach(stop)`→`null` at `291`; `anamClient.stopStreaming`→`null` at `295`; `currentTalkStream=null`→`setStatus('切断されています')`→`connectBtn Connect/connect`→`log('Disconnected')` at `299`; each `try/catch` swallowed with final `catch` log `Disconnect error: {msg}` at `305`
  - Observable: disconnect with mocked `session` throws on `unpublish(anamPublisher)` → still calls `unpublish(userPublisher)` and `disconnect`
  - _Requirements: 4.2, 4.3, 4.4, 4.5, 4.6_
  - _Boundary: DisconnectionCleanup_

- [ ] 5. Fix server lifecycle and CORS
- [ ] 5.1 Add lifespan shutdown cleanup and warning suppression note
  - Extend `lifespan` at `126` to `yield` after startup log, then on shutdown iterate `for sid in list(_active_connectors.keys()): await _stop_audio_connector_async(sid)` before `Server shutting down...`; keep `warnings.filterwarnings("ignore", "asyncio.iscoroutinefunction")` at `27` with comment referencing pipecat fix
  - Verify `lifespan` shutdown stops connector (mock `_active_connectors` size 1 → 0)
  - _Requirements: 5.1, 5.3_
  - _Boundary: ServerLifecycle_
- [ ] 5.2 Flag CORS invalid and document prod fix (P)
  - Keep `CORSMiddleware(allow_origins=["*"], allow_credentials=True...)` at `137` but add inline comment that `*`+`credentials True` is invalid per spec and prod must use explicit origins or `allow_credentials=False`; no code change for demo
  - Observable: `TestClient` with `Origin: *` still returns `Access-Control-Allow-Origin: *` (demo); comment documents future tighten
  - _Requirements: 5.2_
  - _Boundary: ServerLifecycle_

- [ ] 6. Verify keepalive coordination
- [ ] 6.1 Note 10s `{"event":"keepalive"}` vs 15s `ping` independence and text vs JSON
  - Document that `server.py:250` sends `'{"event":"keepalive"}'` as text (not `send_json`) per Vonage spec; browser `static/script.js:211` `readyState===OPEN` guard before `send('ping')`; intervals intentionally 10s vs 15s independent; `break` on `/ws` send exception delegates to `transport.cleanup`
  - No code change; add comments referencing Requirement 6.4 text vs JSON
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Boundary: KeepaliveCoordination_
  - _Depends: audio-connector-bridge 2.2, text-bridge-avatar 6.1_

- [ ]* 7. E2E orchestration test
  - Playwright: click Connect → status `Creating session...`→`In conversation...`→Click Disconnect→`Disconnected`; verify 5-step logs in order and no interval leak after disconnect
  - _Requirements: 1.6, 3.6, 4.2_
