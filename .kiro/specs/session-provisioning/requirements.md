# Requirements Document

## Introduction

Session Provisioning owns the REST layer that issues Vonage Video and Anam avatar sessions. It integrates `POST /api/anam/session-token` at `server.py:160` (proxy to Anam `https://api.anam.ai/v1/auth/session-token`) and `POST /api/vonage/session` at `server.py:194` (Vonage `create_session` → `Audio Connector` connection → `generate_client_token(role=publisher)`) plus Vonage client creation (`server.py:44` `_create_vonage_client` / `server.py:119` `_get_video_client`) and env/private-key handling (`server.py:30` `_require_env` / `server.py:37` `_read_private_key`), so that the browser can obtain all tokens needed for a call with a single request.

## Boundary Context (Optional)
- **In scope**: Vonage `Auth`/`HttpClientOptions` creation, session ID generation, token generation, Anam token proxy, `WS_URI` derivation, env validation, private-key loading with PEM/path dual support
- **Out of scope**: Audio Connector lifecycle management (`audio-connector-bridge`), `/ws` `/ws-anam` WebSocket handling, frontend OT/Anam SDK connection, LLM/STT processing
- **Adjacent expectations**: `audio-connector-bridge` consumes the `session_id`/`ws_uri` produced here, `ops-deployment` provides `.env` and `private.key`, `connection-lifecycle` calls the two POSTs sequentially

## Requirements

### Requirement 1: Anam Session Token Issuance

**Objective:** As a browser, I want to obtain the session token required for Anam avatar initialization via the backend, so that I can specify avatar/voice safely without exposing the API key on the frontend

#### Acceptance Criteria
1. When `POST /api/anam/session-token` is called, the Session Provisioning shall validate `ANAM_API_KEY`/`ANAM_AVATAR_ID`/`ANAM_VOICE_ID` at `server.py:164` via `_require_env` and return 500 `Missing env var` if missing
2. When env is present, the Session Provisioning shall POST to `https://api.anam.ai/v1/auth/session-token` via `aiohttp` with `Authorization: Bearer {ANAM_API_KEY}` and `personaConfig{avatarId, voiceId, llmId:"CUSTOMER_CLIENT_V1", enableAudioPassthrough:false}` plus `sessionOptions{enableSessionReplay:false, sessionTimeout:3600}` — `llmId` is fixed to `CUSTOMER_CLIENT_V1` per Anam contract for custom LLM (implicit rule now explicit)
3. When Anam API returns 200, the Session Provisioning shall return `{"sessionToken": data["sessionToken"]}` as 200 JSON
4. If Anam API returns non-200, then the Session Provisioning shall log status and body via `logger.error` and return 502 `Failed to create Anam token`
5. When multiple requests arrive concurrently, the Session Provisioning shall relay each request to Anam independently without shared state
6. If Anam API returns 401/403, then the Session Provisioning shall treat as invalid `ANAM_API_KEY` and return 502 without echoing the key in logs (security edge case now explicit)

### Requirement 2: Vonage Session Issuance

**Objective:** As a browser, I want to obtain Vonage Video session_id, token, and applicationId in one response, so that I can immediately start `OT.initSession` and Audio Connector connection

#### Acceptance Criteria
1. When `POST /api/vonage/session` is called, the Session Provisioning shall validate `VONAGE_APPLICATION_ID` and `VONAGE_PRIVATE_KEY` via `_require_env` and return 500 if missing
2. When `VONAGE_PRIVATE_KEY` starts with `-----`, the Session Provisioning shall use it as PEM directly; otherwise read the file via `open(value).read()` at `server.py:40`
3. When `VONAGE_PRIVATE_KEY` points to a non-existent file, the Session Provisioning shall catch `FileNotFoundError` and return 500 without stack trace leakage (gap in current `server.py:40` — `open` is unguarded and leaks exception; requirement now mandates guard)
4. When `VONAGE_AUDIO_RATE` is unset, the Session Provisioning shall default to `16000` and return 500 if `int()` conversion fails
5. When the `WS_URI` env var is unset, the Session Provisioning shall auto-derive `ws://{host}/ws` for hosts starting with `localhost` and `wss://{host}/ws` otherwise from `request.headers.host` (`server.py:203`) — note: `127.0.0.1` and `::1` will incorrectly be classified as `wss` (documented limitation)
6. When `WS_URI` is set, the Session Provisioning shall prefer its value for `AudioConnectorWebSocket.uri`
7. When session creation succeeds, the Session Provisioning shall obtain `session_id` via `_create_session_async` (`run_in_executor`) and call `_connect_audio_connector_async` before returning `{"session_id", "token", "application_id"}` as 200 JSON
8. If `Audio Connector` connection throws, then the Session Provisioning shall log via `logger.warning` and return 500 `Audio Connector error: {e}` without returning a token

### Requirement 3: Vonage Client Creation and Token Generation

**Objective:** As a developer, I want Vonage SDK client and token generation managed with timeout and type safety, so that the synchronous SDK does not block the event loop

#### Acceptance Criteria
1. When a Vonage client is needed, the Session Provisioning shall create it via `Auth(application_id, private_key)` and `HttpClientOptions(video_host="video.api.vonage.com", timeout=30)` at `server.py:45`
2. When `generate_client_token` is called, the Session Provisioning shall use `TokenOptions(session_id, role="publisher")` and return `decode("utf-8")` if `bytes`, otherwise return as `str`
3. When `create_session` is called, the Session Provisioning shall offload via `asyncio.get_running_loop().run_in_executor(None, lambda: vng.video.create_session().session_id)`
4. The Session Provisioning shall never `await` Vonage synchronous calls directly and shall always route via `run_in_executor`
5. When `POST /api/anam/session-token` is called, the Session Provisioning shall note that the `Request` parameter at `server.py:161` is unused and shall be removed in refactoring (negative legacy now explicit)

### Requirement 4: Environment and Secret Management

**Objective:** As an operator, I want missing or malformed env vars and private keys detected immediately, so that authentication failures are reported early as 500

#### Acceptance Criteria
1. When required env vars (`VONAGE_APPLICATION_ID`, `VONAGE_PRIVATE_KEY`, `ANAM_API_KEY`, `ANAM_AVATAR_ID`, `ANAM_VOICE_ID`) are empty or unset, the Session Provisioning shall throw `HTTPException(500, "Missing env var: {name}")` via `_require_env` at `server.py:32`
2. The Session Provisioning shall prioritize `.env` via `load_dotenv(override=True)` at `server.py:25` — note: this overwrites process-injected env vars (e.g., Docker/K8s secrets). This is intentional for demo but shall be changed to `override=False` for production (negative legacy now explicit)
3. The Session Provisioning shall not log secrets; `logger` may only output the first 8 characters of `session_id`
4. The Session Provisioning shall treat `VONAGE_PRIVATE_KEY` as either inline PEM or file path based on `startswith("-----")` at `server.py:38` — empty string shall be treated as missing env, not as path

### Requirement 5: Error Handling, Security, and Constraints

**Objective:** As a system, I want to degrade safely on external API failure and invalid input, so that credential leakage and Audio Connector connections with incorrect WS URI are prevented

#### Acceptance Criteria
1. If Vonage `create_session` throws, then the Session Provisioning shall return 500 without including `application_id` or `private_key` in the response
2. If `ANAM_API_KEY` is invalid and Anam API returns 401/403, then the Session Provisioning shall return 502 without including the `ANAM_API_KEY` value in logs or response
3. When `WS_URI` has an invalid scheme that is neither `ws://` nor `wss://`, the Session Provisioning shall return 500 without attempting Audio Connector connection (currently not validated at `server.py:203`; requirement now mandates validation)
4. The Session Provisioning shall not serialize concurrent `POST /api/vonage/session` executions; each request shall generate a fresh `session_id` (no shared session reuse)
5. The Session Provisioning shall never include `private_key` or `ANAM_API_KEY` in responses; only `session_id`/`token`/`application_id`/`sessionToken` shall be returned
6. If `VONAGE_AUDIO_RATE` is not `8000`/`16000`/`48000`, then the Session Provisioning shall allow it but log a warning assuming normalization to 16000 on the `VonageFrameSerializer` side (current code at `server.py:201` does not log; requirement now mandates warning)

### Requirement 6: Implicit Rules and Refactoring Debt

**Objective:** As a maintainer, I want hidden contracts and technical debt explicitly tracked, so that refactoring can remove negative legacy

#### Acceptance Criteria
1. The Session Provisioning shall document that `enableAudioPassthrough:false` and `enableSessionReplay:false` are required for privacy (prevent Anam from capturing mic and storing sessions) at `server.py:178,181` — not just arbitrary defaults
2. The Session Provisioning shall document that `sessionTimeout:3600` at `server.py:182` is the Anam session TTL (1 hour); after expiry `SESSION_READY` will transition to `CONNECTION_CLOSED`
3. The Session Provisioning shall flag `load_dotenv(override=True)` duplication across `server.py:25` and `bot.py:32` as legacy: env should be loaded once at process entry, not per-module
4. The Session Provisioning shall flag the unused `Request` parameter in both POST handlers as legacy to be removed or used for request ID logging
