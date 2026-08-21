# Implementation Plan

- [x] 1. Harden environment and private key handling
- [x] 1.1 Guard `_read_private_key` against missing file (P)
  - Wrap `open(value).read()` at `server.py:40` with `FileNotFoundError` → `HTTPException(500, "Missing env var: VONAGE_PRIVATE_KEY")` without stack trace
  - Verify `VONAGE_PRIVATE_KEY=./missing.key` POST `/api/vonage/session` returns 500 with `Missing env var` not traceback
  - _Requirements: 2.2, 4.2_
  - _Boundary: EnvHelper_
- [x] 1.2 Add `WS_URI` scheme validation and localhost edge documentation (P)
  - After deriving `ws_uri` at `server.py:203`, validate `startswith("ws://") or "wss://"` else raise 500; add comment about `127.0.0.1`→`wss` misclassification as known limitation
  - Test `WS_URI=wss://valid/ws` passes, `WS_URI=http://invalid` → 500 without calling Audio Connector
  - _Requirements: 2.5, 5.3_
  - _Boundary: VonageSessionHandler_
- [x] 1.3 Remove unused `Request` param and unify `load_dotenv` policy
  - Remove unused `request: Request` from `POST /api/anam/session-token` at `server.py:161` (keep for Vonage handler where `host` header used); extract `load_dotenv` to single call at process entry and change to `override=False` for prod note
  - Verify both POSTs still 200 with mocked externals and no duplicate env loads
  - _Requirements: 3.5, 4.3, 6.3_
  - _Boundary: EnvHelper_

- [ ] 2. Implement Anam token proxy hardening
- [ ] 2.1 Verify `POST /api/anam/session-token` success and error paths
  - Mock `aiohttp` 200 → 200 `{sessionToken}`; mock 401/403 → 502 without echoing `ANAM_API_KEY` in logs; concurrent calls independent (no shared state)
  - Observable: `pytest -k test_anam_token` passes with key leak assertion
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6_
  - _Boundary: AnamTokenHandler_
- [ ] 2.2 Document `CUSTOMER_CLIENT_V1` and session options
  - Add inline comment in `server.py:174-182` explaining `llmId:"CUSTOMER_CLIENT_V1"` custom LLM contract, `enableAudioPassthrough:false`/`enableSessionReplay:false` privacy, `sessionTimeout:3600`
  - No code change; ensure response still `{sessionToken}`
  - _Requirements: 1.2, 6.1, 6.2_
  - _Boundary: AnamTokenHandler_

- [ ] 3. Implement Vonage session issuance with Audio Connector trigger
- [ ] 3.1 Ensure Vonage client and session creation via `run_in_executor` (P)
  - Verify `_create_vonage_client` uses `Auth` + `HttpClientOptions(video_host="video.api.vonage.com", timeout=30)` at `44` and `_create_session_async` uses `run_in_executor` at `59`
  - Mock `vng.video.create_session()` and assert not awaited directly
  - _Requirements: 2.6, 3.1, 3.3, 3.4_
  - _Boundary: VonageClientFactory_
- [ ] 3.2 Ensure token generation and response contract (P)
  - Verify `_generate_client_token` uses `TokenOptions(session_id, role="publisher")` at `50` and handles bytes→str; `POST /api/vonage/session` returns `200 {session_id, token, application_id}` only on Audio Connector success
  - Test Audio Connector exception → 500 `Audio Connector error` without token
  - _Requirements: 2.6, 2.7, 3.2_
  - _Boundary: VonageSessionHandler_
- [ ] 3.3 Handle `VONAGE_AUDIO_RATE` parsing per spec
  - Ensure default 16000 when unset, 500 on `int()` ValueError, and warn when not 8000/16000/48000 as per Requirement 5.6 (add warning log)
  - Observable: env `VONAGE_AUDIO_RATE=abc` → 500; `VONAGE_AUDIO_RATE=48000` → warning logged
  - _Requirements: 2.3, 5.6_
  - _Boundary: VonageSessionHandler_

- [ ] 4. Security and error contract audit
- [ ] 4.1 Verify no secret leakage in logs or responses
  - Assert `private_key`/`ANAM_API_KEY` never in response bodies and `session_id` only first 8 chars logged at `59`
  - Test `_require_env` empty string → 500 `Missing env var` via `server.py:32`
  - _Requirements: 4.1, 4.4, 5.1, 5.4, 5.5_
  - _Boundary: EnvHelper, VonageSessionHandler, AnamTokenHandler_

- [ ]* 5. Load and concurrency test
  - Concurrent `POST /api/vonage/session` ×5 each yields fresh `session_id` (no reuse) and independent `POST /api/anam/session-token` fan-out
  - _Requirements: 1.5, 5.4_
