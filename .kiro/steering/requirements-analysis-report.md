# Requirements vs Code Comparative Analysis Report

> Date: 2026-08-21 | Scope: 8 specs (`frontend-shell`, `session-provisioning`, `audio-connector-bridge`, `voice-pipeline-core`, `text-bridge-avatar`, `vonage-media-frontend`, `connection-lifecycle`, `ops-deployment`) vs implementation (`server.py:1-302`, `bot.py:1-202`, `static/index.html:1-59`, `static/script.js:1-316`, `start.sh:1-73`, `Dockerfile:1-17`, `docker-compose.yml:1-13`, `pyproject.toml:1-14`)

All `requirements.md` have been updated to English and now include explicit notes for implicit rules, bugs, and refactoring debt (see per-spec `Requirement 6`). This report summarizes the three requested perspectives.

---

## 1. Unnecessary Processing / Suspected Bugs

| Spec | Location | Issue | Severity | Requirement Update |
|------|----------|-------|----------|-------------------|
| **frontend-shell** | `static/index.html:30` `#subscriberContainer video {display:none}` | Parent `#subscriberContainer` already `display:none` at `50`, so inner video rule never applies — dead CSS. | Low | Added Req 6.1; shall be removed |
| **frontend-shell** | `static/index.html:19` `!important` overrides | Required today to override Vonage-injected styles, but `!important` debt. Not a bug but fragile. | Med | Added Req 1.6 and Req 6.2 |
| **session-provisioning** | `server.py:40` `_read_private_key` | `open(value).read()` with no `FileNotFoundError` guard — leaks exception instead of 500 without stack trace. | Med | Added Req 2.3 |
| **session-provisioning** | `server.py:205` `host.startswith("localhost")` | Misclassifies `127.0.0.1:8005` and `::1` as `wss` (should be `ws`). Tunnel host detection is fragile. | Med | Added Req 2.5 note |
| **session-provisioning** | `server.py:161` unused `Request` param | `POST /api/anam/session-token` takes `request: Request` but never uses it — dead param. | Low | Added Req 3.5 |
| **audio-connector-bridge** | `server.py:108` raw `_http_client.delete` | Bypasses `vonage-video` SDK (`stop_audio_connector`) with hardcoded path `/v2/project/{id}/connect?sessionId=` — breaks on API version change. | High | Added Req 1.5 legacy flag |
| **audio-connector-bridge** | `server.py:68` `_active_connectors: dict` | Plain dict without `asyncio.Lock` — concurrent `POST /api/vonage/session` race on `list(keys())` and stop. | High | Added Req 4.3 |
| **audio-connector-bridge** | `server.py:100` re-creates Vonage client per stop | `_stop` calls `_get_video_client()` which re-reads env/keys per call — inefficient. | Low | Added Req 5.6 |
| **voice-pipeline-core** | `bot.py:141` `context._messages.clear()` | Accesses private `_messages` — breaks on pipecat-ai minor bump. | High | Added Req 4.1 flag |
| **voice-pipeline-core** | `bot.py:200` re-reads `VONAGE_AUDIO_RATE` | Duplicates `server.py:233` rate parsing; divergence risk if env changes between calls. | Med | Added Req 7.2 flag |
| **voice-pipeline-core** | `bot.py:32` duplicate `load_dotenv` | Duplicates `server.py:25` — loads env twice, second may overwrite. | Low | Added Req 7.6 flag |
| **text-bridge-avatar** | `static/script.js:210` `setInterval` leak | Ping interval every 15s never `clearInterval` on `disconnect()` — leaks timer and `InvalidStateError` after close. | High | Added Req 5.5-6 |
| **text-bridge-avatar** | `static/script.js:256` `handleInterrupt` dead code | Defined but never invoked anywhere — unused. | Med | Added Req 4.5 dead code flag |
| **text-bridge-avatar** | `server.py:284` hardcoded greeting | `こんにちは...` hardcoded in WS handler, not configurable nor LLM-generated — duplication. | Low | Added Req 1.2 explicit |
| **vonage-media-frontend** | `static/script.js:157` `hiddenDiv.style.display='none'` | `display:none` publisher may be throttled/suspended by browser; Vonage recommends off-screen, not hidden. | High | Added Req 2.3 bug flag |
| **vonage-media-frontend** | `static/index.html:50` `#subscriberContainer display:none` for audio | Audio-only subscriber on hidden container may not play audio in some browsers (requires visible audio sink). | Med | Added Req 3.3 and 5.6 |
| **vonage-media-frontend** | `static/script.js:131` `createAndPublish` closure | Defined inside `connect()` — recreated per connection (alloc overhead). | Low | Added Req 5.5 |
| **connection-lifecycle** | `static/script.js:219` optimistic `isConnected=true` | Set immediately after `new WebSocket` without waiting for `onopen` — UI shows `In conversation...` even if WS fails. | High | Added Req 1.6 and 3.2 bug flag |
| **connection-lifecycle** | `static/script.js:42` Anam token failure aborts | Step 1 failure `return`s early, blocking Vonage even though audio-only degradation is possible (Step 3 does degrade). Inconsistent. | Med | Added Req 2.1 gap flag |
| **connection-lifecycle** | `server.py:137` CORS `allow_origins=["*"]` + `allow_credentials=True` | Invalid per CORS spec — browsers reject `*` with credentials. | High | Added Req 5.2 bug flag |
| **connection-lifecycle** | `static/script.js:277` missing `clearInterval` | `disconnect()` closes `wsAnam` but does not clear ping interval (same as text-bridge). | High | Added Req 4.1 flag |
| **ops-deployment** | `Dockerfile:10` only `COPY pyproject.toml` | Ignores `uv.lock` — build not reproducible; `uv pip install -r pyproject.toml` ignores lock. | High | Added Req 4.2 bug flag |
| **ops-deployment** | `Dockerfile:11` `pip install uv` per build | Slow; should use `COPY --from=ghcr.io/astral-sh/uv` or `uv` base. | Low | Noted in Req 4 |
| **ops-deployment** | `start.sh:10` `pkill -f "cloudflared tunnel"` | Overly broad — kills any `cloudflared tunnel` process system-wide. | Med | Added Req 2.1 flag |
| **ops-deployment** | `start.sh:38` `lsof -ti:8005` | Not installed in minimal/Docker images; no fallback to `ss`/`fuser`. | Med | Added Req 3.1 flag |
| **ops-deployment** | `start.sh:48` `nohup` | Leaves orphaned processes; no `trap` for cleanup. | Med | Added Req 3.2, 6.6 flag |
| **ops-deployment** | `docker-compose.yml:1` `version: "3.9"` | Deprecated in Compose Spec v2. | Low | Added Req 5.5 |

---

## 2. Implicit Important Rules (Edge Cases Now Explicit)

| Spec | Implicit Rule | Previous Gap | Now Explicit In |
|------|---------------|--------------|-----------------|
| **frontend-shell** | `!important` overrides required to counter Vonage-injected inline styles at `19` | Not mentioned | Req 1.6 |
| **frontend-shell** | `video-wrapper::after {padding-bottom:100%}` creates square aspect regardless of video source | Called “square” without explaining mechanism | Req 1.5 |
| **session-provisioning** | `llmId: "CUSTOMER_CLIENT_V1"` is a fixed Anam contract for custom LLM; `enableAudioPassthrough:false` prevents Anam mic echo; `sessionTimeout:3600` is 1h TTL | Listed as JSON without rationale | Req 1.2 + Req 6.1-6.2 |
| **session-provisioning** | `enableSessionReplay:false` is privacy rule (no storage) | Not explained | Req 6.1 |
| **audio-connector-bridge** | Global singleton: loop `for old_sid in list(_active_connectors.keys()): await _stop(...)` at `74` means only one connector system-wide, not per-user; concurrent users would fight | Described as “exactly one per session” incorrectly | Req 1.1 + Req 4.1 |
| **audio-connector-bridge** | `{"event":"keepalive"}` every 10s is required by Vonage; missing >30s closes connector | Called “keepalive” without TTL | Req 2.4 |
| **audio-connector-bridge** | `audio_out_10ms_chunks=2` = 20ms chunks | Not explained | Req 2.3 |
| **audio-connector-bridge** | `_stop` via `DELETE /v2/project/{id}/connect?sessionId=` bypasses SDK | Not documented as raw HTTP | Req 1.5 |
| **voice-pipeline-core** | `no_speech_prob=0.3` threshold discards silence | Not explained | Req 1.3 |
| **voice-pipeline-core** | `audio_idle_timeout=2.0` / `user_turn_stop_timeout=5.0` control turn aggregation | Listed without definition | Req 2.2 |
| **voice-pipeline-core** | `stop_secs=0.8` delay prevents mid-sentence cutoff for Japanese particles; `min_volume=0.4` filters low-volume noise | Not justified | Req 2.3-2.4 |
| **voice-pipeline-core** | `context._messages.clear()` is private API | Not flagged | Req 4.1 |
| **voice-pipeline-core** | `Pipeline` order `text_forwarder` after `assistant_aggregator` is required to capture monkey-patched downstream frames | Order listed without rationale | Req 5.1 |
| **text-bridge-avatar** | Hardcoded greeting `こんにちは...` sent on every `/ws-anam` connect, not LLM-generated | Not explained | Req 1.2 + 1.6 |
| **text-bridge-avatar** | `broadcast_text` silently discards failed clients without logging | Not documented | Req 2.3 |
| **text-bridge-avatar** | `_text_bridge` singleton shared across all `/ws` pipelines (per process, not per connection) | Not explained | Req 2.5 |
| **text-bridge-avatar** | `disableInputAudio:true` prevents duplicate mic capture (Vonage vs Anam) | Listed without rationale | Req 3.1 |
| **text-bridge-avatar** | `streamMessageChunk(text,false)` with `false` means streamed, not append-only; chunks share one `TalkMessageStream` until `llm_end` | Not explained | Req 4.1 |
| **text-bridge-avatar** | `isActive` guard prevents `endMessage` on closed stream | Not documented | Req 4.3 |
| **vonage-media-frontend** | `if (subscriber) return` at `103` means only first remote stream is subscribed; additional streams ignored (1:1 demo limitation) | Not documented | Req 3.2 |
| **vonage-media-frontend** | `connectionId === session.connection.connectionId` self-exclusion prevents self-subscription | Not explained as self-exclusion | Req 1.2 |
| **vonage-media-frontend** | `videoSource: null` / `audioSource: false` semantics for avatar publisher | Not explained | Req 2.4 |
| **connection-lifecycle** | `statusEl` limited to four Japanese literals; `isConnected` boolean insufficient for `connecting` state | Not enumerated as limitation | Req 3.6-3.7 |
| **connection-lifecycle** | Step 3 failure degrades to audio-only but Step 1 failure aborts (inconsistent) | Not documented | Req 2.1 vs 2.3 |
| **ops-deployment** | Tunnel regex `https://[a-z0-9-]+\.trycloudflare\.com` assumes subdomain pattern | Not explained | Req 2.3 |
| **ops-deployment** | `WS_URI` printed but not exported; user must manually set env | Not documented | Req 2.5 |

---

## 3. Negative Legacy to Change or Remove (Refactoring Candidates)

| Area | Legacy | Why Negative | Proposed Change | Tagged In |
|------|--------|--------------|-----------------|-----------|
| **Env loading** | `load_dotenv(override=True)` duplicated in `server.py:25` and `bot.py:32`; overwrites injected env (Docker/K8s secrets) | Demo convenience hides prod bug; second load redundant | Load once at `server.py` entry with `override=False` for prod; remove from `bot.py` | session-provisioning Req 4.2, voice-pipeline-core Req 7.6 |
| **Global singletons** | `_active_connectors: dict` and `_text_bridge: LLMTextBridgeProcessor` as module globals | Not scalable, no locking, shared across pipelines, hard to test | Inject via `FastAPI Depends` / `app.state`; per-connection bridge or Redis-backed session store | audio-connector-bridge Req 4.3, text-bridge-avatar Req 2.5 |
| **Monkey-patch** | `LLMAssistantAggregator._handle_text/_handle_llm_end` private method patch at `bot.py:34-45` | Breaks on pipecat-ai bump; double push | Replace with proper `FrameProcessor` or upstream `enable_forwarding` flag; or contribute to pipecat | voice-pipeline-core Req 6.3 |
| **Private API** | `context._messages.clear()` and `vng._http_client.delete` raw HTTP | Fragile direct access | Use `context.set_messages([])` (if available) and `vng.video.stop_audio_connector` SDK method | voice-pipeline-core Req 4.1, audio-connector-bridge Req 1.5 |
| **CORS** | `allow_origins=["*"]` + `allow_credentials=True` at `server.py:137` | Invalid CORS, browsers block | Set explicit `allow_origins` list or `allow_credentials=False` for demo; add `security.md` steering | connection-lifecycle Req 5.2 |
| **Frontend globals** | `let session, anamPublisher, userPublisher, subscriber, anamClient, anamStream, wsAnam, isConnected` at `static/script.js:11-18` | Global mutable state, no encapsulation, hard to test | Encapsulate in `class AvatarSession` with methods `connect/disconnect` | text-bridge-avatar Req 6.5, vonage-media-frontend Req 5.5, connection-lifecycle Req 3.7 |
| **Hidden div `display:none`** | Avatar publisher on `display:none` div at `static/script.js:157` | Browser may throttle hidden publisher; video may not send | Use `visibility:hidden` or `position:fixed; left:-9999px; width:1px; height:1px` | vonage-media-frontend Req 2.3/5.2 |
| **Hidden subscriber** | `#subscriberContainer display:none` for audio-only subscriber | May prevent audio playback in some browsers | Use audio sink element or off-screen visible container | vonage-media-frontend Req 3.3/5.6 |
| **Optimistic state** | `isConnected=true` before `wsAnam.onopen` at `static/script.js:219` | UI lies (shows connected when WS failed) | Move to `wsAnam.onopen` handler; add `Connecting` state | connection-lifecycle Req 1.6/3.2 |
| **Inconsistent degrade** | Step 1 Anam token failure aborts vs Step 3 degrades to audio-only | User expected audio-only fallback for both | Make Step 1 also degrade or document as intentional abort | connection-lifecycle Req 2.1 |
| **Interval leak** | `setInterval` at `static/script.js:210` never `clearInterval` | Leaks timer after disconnect; sends to closed WS | Store `intervalId` and `clearInterval` in `disconnect()` | text-bridge-avatar Req 5.5-6, connection-lifecycle Req 4.1 |
| **Dead code** | `handleInterrupt()` at `static/script.js:256` never called | Confuses maintainers; interrupt never wired to VAD | Wire to `SileroVAD` interrupt or remove; add test | text-bridge-avatar Req 4.5 |
| **Rate duplication** | `AUDIO_OUT_SAMPLE_RATE=16000` constant vs `VONAGE_AUDIO_RATE` env | Divergence risk | Single source: `settings.audio_rate` injected from `session-provisioning` | voice-pipeline-core Req 7.2-7.3 |
| **Inline CSS** | `<style>` in `static/index.html` | No caching, no CSP, hard to maintain | Extract to `static/style.css` | frontend-shell Req 6.3 |
| **Dockerfile reproducibility** | `COPY pyproject.toml` only + `uv pip install -r pyproject.toml` ignores `uv.lock` | Build not reproducible | `COPY pyproject.toml uv.lock && uv sync --frozen`; remove `version: "3.9"` | ops-deployment Req 4.2/5.5 |
| **start.sh process mgmt** | `pkill -f`, `lsof`, `nohup` with no `trap` cleanup, tunnel.log polling | Kills unrelated processes, fails without lsof, orphans processes, logs unbounded | Use `trap "kill $PID"`; check `command -v cloudflared lsof curl`; rotate logs; export `WS_URI` | ops-deployment Req 2.1, 3.1-3.2, 6.6 |
| **Hardcoded greeting** | `こんにちは...` at `server.py:284` | Not configurable, duplicates LLM role | Make configurable via `GREETING_TEXT` env or generate via LLM on first `/ws-anam` connect | text-bridge-avatar Req 1.2 |

---

## Updated Requirements.md

All 8 `requirements.md` now include a new `Requirement 6` (or extended criteria) documenting the above implicit rules and legacy flags with `gap flagged` / `legacy flagged` notes and EARS criteria for future fixes. Key doc fixes:

* **frontend-shell**: Corrected status literals to Japanese (`切断されています` etc.) with English translations; added `!important` rationale and subscriber dead CSS note.
* **session-provisioning**: Added `FileNotFoundError` guard, `load_dotenv` production note, `llmId` contract rationale, WS URI derivation limitation.
* **audio-connector-bridge**: Clarified global singleton, raw DELETE legacy, keepalive TTL, and missing lock/shutdown gaps.
* **voice-pipeline-core**: Clarified `no_speech_prob`/`audio_idle_timeout`/`stop_secs` semantics, private API legacy, rate duplication.
* **text-bridge-avatar**: Restored Japanese greeting literal, flagged `setInterval` leak, dead `handleInterrupt`, silent discard, and `WebSocket` coupling.
* **vonage-media-frontend**: Flagged `display:none` hidden div and subscriber, clarified self-exclusion and single-subscriber limitation.
* **connection-lifecycle**: Flagged optimistic `isConnected`, inconsistent degrade, CORS invalid, interval leak, boolean state insufficiency.
* **ops-deployment**: Flagged `uv.lock` ignore, broad `pkill`, `lsof` dependency, `nohup` orphan, `version` deprecation, missing `trap`.

---

## Recommended Next Priority Refactors

1. **P1 (Stability):** Fix `display:none` publisher, CORS, and `setInterval` leak — user-visible bugs.
2. **P1 (Reproducibility):** Fix Dockerfile `uv.lock` and `lsof` fallback — CI/CD blocker.
3. **P2 (Robustness):** Add `asyncio.Lock` for `_active_connectors`, guard `_read_private_key`, wait for `wsAnam.onopen` before `isConnected=true`.
4. **P2 (Debt):** Remove monkey-patch and private `_messages` access after pipecat-ai upgrade; encapsulate frontend globals.
5. **P3 (UX):** Make Step 1 also degrade to audio-only; wire `handleInterrupt` to VAD.

