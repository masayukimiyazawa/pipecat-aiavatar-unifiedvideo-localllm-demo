# Requirements Document

## Introduction

Connection Lifecycle owns the 5-step connection orchestration and disconnection/state management on the frontend. It integrates `connect()` at `static/script.js:29` (① Anam token `POST /api/anam/session-token` → ② Vonage session `POST /api/vonage/session` → ③ Anam init `createClient/stream` → ④ Vonage connect + dual publish + subscribe → ⑤ `/ws-anam` connection) and `disconnect()` at `static/script.js:272`, plus server `lifespan` at `server.py:126` / `CORSMiddleware` at `server.py:137` / `loguru` logging, so that a user reaches conversation state with one "Connect" button and releases all resources on disconnect. The `isConnected` flag (`static/script.js:18`) and `connectBtn`/`statusEl`/`logEl` (`static/script.js:4`) are the single source of truth.

## Boundary Context (Optional)
- **In scope**: 5-step connection sequence, state transitions (disconnected → creating session → in conversation → disconnected), button/status/log UI reflection, full resource release on disconnect, keepalive coordination, server lifespan/CORS
- **Out of scope**: Screen layout itself (`frontend-shell`), individual Vonage/Anam SDK call details (owned by respective specs), STT/LLM inference, tunnel/deployment
- **Adjacent expectations**: `frontend-shell` provides DOM, `session-provisioning` supplies two POSTs, `vonage-media-frontend` provides OT connection, `text-bridge-avatar` provides Anam/WS, `audio-connector-bridge` provides `/ws`

## Requirements

### Requirement 1: 5-Step Connection Orchestration

**Objective:** As a user, I want five steps executed sequentially by pressing the connect button, so that I can start conversation without awareness of complex initialization

#### Acceptance Criteria
1. When `connectBtn` is clicked and `isConnected===false`, the Connection Lifecycle shall immediately execute `connectBtn.disabled=true` and `setStatus('Creating session...')` at `static/script.js:30`
2. When Step 1 `fetch('/api/anam/session-token',{method:'POST'})` returns 200, the Connection Lifecycle shall obtain `atData.sessionToken` and log `Anam token obtained` then proceed to Step 2 (`static/script.js:37`)
3. When Step 2 `fetch('/api/vonage/session',{method:'POST'})` returns 200, the Connection Lifecycle shall obtain `vonageData{application_id, session_id, token}` and log `Vonage session: {8 chars}...` then proceed to Step 3 (`static/script.js:53`)
4. When Step 3 `createClient(anamToken,{disableInputAudio:true})` and `await anamClient.stream()` succeed, the Connection Lifecycle shall store `anamStream` and set `anamVideo.srcObject` then proceed to Step 4 (`static/script.js:67`)
5. When Step 4 `OT.initSession` → `session.connect` → dual `createAndPublish` complete, the Connection Lifecycle shall proceed to Step 5 `/ws-anam` connection (`static/script.js:96`)
6. When Step 5 `new WebSocket(wsProto://host/ws-anam)` is created, the Connection Lifecycle shall log `Anam text WebSocket connecting` and on `wsAnam.onopen` log `Anam WS connected` (`static/script.js:184`) — note: current code at `static/script.js:219` sets `isConnected=true` immediately after `new WebSocket` without waiting for `onopen` (bug flagged: optimistic state; requirement now mandates waiting for `onopen` before `isConnected=true`)

### Requirement 2: Error Handling and Interruption

**Objective:** As a user, I want failures mid-flow logged and the button re-enabled, so that I can retry and diagnose

#### Acceptance Criteria
1. If Step 1 `fetch /api/anam/session-token` is non-200 or throws, then the Connection Lifecycle shall log `Anam token error: {msg}` and execute `setStatus('Connection failed')` and `connectBtn.disabled=false` then interrupt remaining steps with `return` (`static/script.js:42`) — note: this blocks Vonage even though Vonage could proceed without Anam (gap flagged; should degrade to audio-only instead of abort)
2. If Step 2 `fetch /api/vonage/session` is non-200 or throws, then the Connection Lifecycle shall log `Vonage error: {msg}` and execute `setStatus('Connection failed')` and `disabled=false` then interrupt (`static/script.js:57`)
3. If Step 3 Anam initialization throws, then the Connection Lifecycle shall log `Anam initialization error: {msg}` and continue to Vonage connection (degrade to audio-only, `static/script.js:87`) — this is the intended degradation path, unlike Step 1 which currently aborts
4. If Step 4 `session.connect` throws, then the Connection Lifecycle shall log `Vonage connection error: {msg}` and execute `setStatus('Connection failed')` and `disabled=false` then interrupt (`static/script.js:171`)
5. If the order of Step 2 and Step 3 is swapped, then the Connection Lifecycle shall allow reordering since Anam init does not depend on Vonage sessionId, but shall preserve log order `Anam obtained → Vonage created` — current code order is fixed; requirement now documents that swapping is safe

### Requirement 3: State Management and UI Reflection

**Objective:** As a user, I want the current connection state accurately reflected on the button and status, so that I am not confused about operability

#### Acceptance Criteria
1. When `connect()` starts, the Connection Lifecycle shall not change `isConnected` and shall prevent double-click with `connectBtn.disabled=true`
2. When all steps succeed and `wsAnam.onopen` fires, the Connection Lifecycle shall set `isConnected=true` — current code sets at `static/script.js:219` before `onopen` (bug flagged)
3. When `disconnect()` starts, the Connection Lifecycle shall immediately set `isConnected=false` (`static/script.js:275`)
4. When `isConnected===true` and `connectBtn` is clicked, the Connection Lifecycle shall call `disconnect()` (`static/script.js:311`)
5. When `isConnected===false` and `connectBtn` is clicked, the Connection Lifecycle shall call `connect()`
6. The Connection Lifecycle shall limit `statusEl` possible values to four Japanese literals: `切断されています` / `セッション作成中...` / `会話中...` / `接続失敗` as set at `static/script.js:31,44,59,220` — literal Japanese now explicit after English translation correction
7. The Connection Lifecycle shall note that `isConnected` as a single boolean is insufficient for states `connecting` vs `connected` vs `failed` — should be refactored to enum `Disconnected | Connecting | Connected | Failed` (legacy flagged)

### Requirement 4: Disconnection and Resource Release

**Objective:** As a user, I want all sessions, streams, and sockets released on disconnect, so that resource conflicts do not occur on reconnect

#### Acceptance Criteria
1. When `disconnect()` is called, the Connection Lifecycle shall execute `if (wsAnam) try{wsAnam.close()}catch{}` → `wsAnam=null` (`static/script.js:277`) — note: `wsAnam` ping `setInterval` at `static/script.js:210` is not cleared here (bug flagged; shall add `clearInterval`)
2. When `session` exists, the Connection Lifecycle shall sequentially execute `try{if(anamPublisher) session.unpublish(anamPublisher)}catch{}` → `try{if(userPublisher) session.unpublish(userPublisher)}catch{}` → `try{session.disconnect()}catch{}` and set `subscriber=null; session=null` (`static/script.js:282`) — order: publishers before session
3. When `anamStream` exists, the Connection Lifecycle shall execute `anamStream.getTracks().forEach(t=>t.stop())` → `anamStream=null` (`static/script.js:290`)
4. When `anamClient` exists, the Connection Lifecycle shall execute `try{anamClient.stopStreaming()}catch{}` → `anamClient=null` (`static/script.js:294`)
5. When release completes, the Connection Lifecycle shall execute `currentTalkStream=null`, `setStatus('切断されています')`, `connectBtn.textContent='接続'`, `className='connect'`, `log('Disconnected')` (`static/script.js:299`)
6. If an exception occurs during release, then the Connection Lifecycle shall log `Disconnect error: {msg}` and continue subsequent release steps (`static/script.js:305`) — each resource is attempted even if prior fails

### Requirement 5: Server Lifecycle and CORS

**Objective:** As an operator, I want server startup/shutdown and CORS properly managed, so that browser access from any origin (demo) is allowed while startup logs are observable

#### Acceptance Criteria
1. When FastAPI starts, the Connection Lifecycle shall log `Server starting up...` via `lifespan` at `server.py:126` and on shutdown log `Server shutting down...` — note: `lifespan` does not clean `_active_connectors` on shutdown (gap flagged; should stop all connectors)
2. When a request from any origin arrives, the Connection Lifecycle shall allow via `CORSMiddleware(allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])` at `server.py:137` — note: `allow_origins=["*"]` with `allow_credentials=True` is invalid per CORS spec and will be rejected by browsers; for production shall be changed to explicit origins or `allow_credentials=False` (bug/legacy flagged)
3. The Connection Lifecycle shall suppress Pipecat deprecation warnings via `warnings.filterwarnings("ignore", "'asyncio.iscoroutinefunction' is deprecated")` (`server.py:27`) — note: this hides future deprecation, should be removed after pipecat-ai fix
4. When the `click` listener for `connectBtn` is registered, the Connection Lifecycle shall register `if(isConnected) disconnect() else connect()` at `static/script.js:311` and on page load log `Ready. Please click the connect button.` (`static/script.js:316`)

### Requirement 6: Keepalive Coordination

**Objective:** As a system, I want keepalive maintained for both WebSockets, so that idle disconnections are prevented

#### Acceptance Criteria
1. While `/ws` is connected, the Connection Lifecycle shall assume server 10-second `{"event":"keepalive"}` at `server.py:250` and browser 15-second `ping` in `text-bridge-avatar` operate independently — intervals are not synchronized; 10s vs 15s is intentional (server more frequent)
2. When keepalive send on `/ws` throws, the Connection Lifecycle shall `break` the loop and delegate to `transport.cleanup()` without logging (gap flagged; should log)
3. When `ping` send on `/ws-anam` has `readyState !== OPEN`, the Connection Lifecycle shall skip sending (`static/script.js:211`) — prevents `InvalidStateError`
4. The Connection Lifecycle shall note that `/ws` keepalive uses `websocket.send_text` with JSON string `{"event":"keepalive"}` not `send_json` — must remain text to satisfy Vonage Audio Connector spec (implicit rule now explicit)
