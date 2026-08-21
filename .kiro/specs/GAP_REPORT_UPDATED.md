# Consolidated Gap Analysis Report — Specs vs Existing Code (Updated)

**Date:** 2026-08-21 (Update)  
**Scope:** `.kiro/specs/{frontend-shell,session-provisioning,audio-connector-bridge,voice-pipeline-core,text-bridge-avatar,vonage-media-frontend,connection-lifecycle,ops-deployment}/{requirements.md,design.md,tasks.md,spec.json}` vs `server.py:1-313, bot.py:1-212, static/index.html:1-59, static/script.js:1-326, start.sh:1-73, Dockerfile:1-17, docker-compose.yml:1-13, pyproject.toml:1-14, tests/`  
**Mode:** Existing code is 100% in `server.py/bot.py/static` — no `src/features/[feature]/` directory (design correctly maps to these 4 files). Phase `tasks-generated` for all specs. First tasks `frontend-shell 1.1,1.2 [x]`, `session-provisioning 1.1[x],1.2[x],1.3[x]` (fixed this cycle), `audio-connector-bridge 1.1[x],1.2[x]` (partial lock regression), `voice-pipeline-core 1.1[x],1.2[x]`, `text-bridge-avatar 1.1[x],1.2[x]` already completed — this report covers **remaining** tasks.

---

## Executive Summary (Updated)

All 8 specs remain retrospective docs of working demo code. After this cycle's fixes (**5 code changes**: `static/index.html:30` dead rule removed, `server.py:9-12` single `load_dotenv` + `server.py:164` `Request` removal, `server.py:103,79,132` `Optional[Vonage]` reuse + `lifespan` cleanup, `bot.py:8` `HasSendJson` Protocol + `140` `set_messages` guard, `static/script.js:18,187,224,287` `wsAnamPingId` + `isConnected` in `onopen`), **12/37 gaps closed**. Critical remaining: **(A) Missing test harness** still blocks `TestClient`/`playwright` tasks (now partially fixed via `tests/conftest.py:3` + 9 tests passing, but `vonage-media`/`text-bridge` still need mocks); **(B) 3-spec hotspot** (`server.py:71-99,132,233,277` and `static/script.js:29-224,282-316`) still 3 PRs; **(C) Reproducible build** (`Dockerfile:10-11` ignores `uv.lock`) and **broad `pkill` / `lsof` fallback / trap** (`start.sh`) still open. **(D) Lock regression:** `_connector_lock` added then lost (see `audio-connector-bridge` D6). Reuse remains good — 70% remaining tasks are docs/tests, not missing features.

---

## 1. Dependency / Precondition Gaps (Updated)

| # | Spec / Task | Missing Prerequisite | Current Code Evidence | Proposal |
|---|-------------|----------------------|-----------------------|----------|
| D1 | **ALL** still | `playwright` missing; `pytest`/`beautifulsoup4`/`httpx` now added via `uv add --dev` (`pyproject.toml` now has `pytest 9.1.1`, `beautifulsoup4 4.15`), `tests/` exists with `conftest.py:3` + `test_frontend_shell.py:5` + `test_session_provisioning.py:4` + `test_ops_deployment.py:3` (9 tests) | `tests/` now exists (was absent), `pyproject.toml:6` now has dev deps, but `vonage-media`/`text-bridge` tasks still need `playwright` | Keep Task 0 completed for `pytest`/`bs4`; add follow-up `uv add --dev playwright && playwright install` for `frontend-shell 3.2,5.1` and `vonage-media *5` |
| D2 | `frontend-shell` 3.1,4.1,5.1 | `static/style.css` draft absent; `playwright` not installed | `bash ls static/style.css` → absent; `static/index.html:30` now comment (fixed `2.1`) | Task `4.1` create `static/style.css` as `sed -n '9,31p' index.html` draft; keep inline primary per `design.md:84` |
| D3 | `session-provisioning` P1-3 | `private.key` path ambiguous `CWD` vs `/app` | `server.py:37-42` now `try FileNotFound → HTTPException` (fixed `1.1`), but no `Path(__file__).parent` note | `design.md:242` add `Path(value).is_absolute ? value : Path(__file__).parent / value` note |
| D4 | `session-provisioning` P1-4 | `WS_URI` host-header trust (`server.py:206` `testserver`→`wss`) | `server.py:208-209` now validates `ws://`/`wss://` else 500 (fixed `1.2`), but `_derive_ws_uri` not extracted | Extract pure `def _derive_ws_uri(host, env_ws_uri)` at `server.py:203` for unit test; keep comment `127.0.0.1→wss` limitation |
| D5 | `session-provisioning` P1-1 | `aiohttp` still inside handler `server.py:171` `import aiohttp` | `pyproject.toml` still omits `aiohttp` (relies on transitive `pipecat-ai→aiohttp 3.14.3`), `Dockerfile:11` still `uv pip install -r pyproject.toml` | Hoist `import aiohttp` to `server.py:7` top; `design.md:84` add `aiohttp>=3.14.3` or switch to `httpx` |
| D6 | `audio-connector-bridge` 1.1 | **Regression:** `tasks.md:4 [x]1.1` claims `_connector_lock` added, but `server.py:72` is again plain `dict` no lock ( `grep _connector_lock` → 0 hits) | `server.py:72` `dict`, `78` `for old_sid in list(...): await _stop(old_sid, vng)` without `async with lock` | Re-add `72 _connector_lock = asyncio.Lock()` and wrap `78-99` block in `async with _connector_lock` (no nesting of `_stop` lock) |
| D7 | `audio-connector-bridge` 1.2 reuse | `server.py:103` now `Optional[Vonage]=None` + `if vng is None: _get_video_client()` and `79` passes `vng`, `132` `lifespan` loops `await _stop(sid)` — reuse fixed for `79`, but `lifespan` at `138` calls `_stop(sid)` without `vng` → re-reads env per SID | `server.py:138` fallback still `Optional` | `lifespan` create single `vng = _get_video_client()` before loop and `await _stop(sid, vng)` |
| D8 | `audio-connector-bridge` rate double-source | `server.py:212` vs `242` vs `bot.py:212` still duplicate `int(os.getenv("VONAGE_AUDIO_RATE"))` vs `47` `AUDIO_OUT_SAMPLE_RATE=16000` | `bot.py:38` TODO comment added, but `server.py:242` still reads env + `bot.py:212` fallback still reads | Keep `voice-pipeline-core 1.1` injection (`server.py:277` now `await bot(..., sample_rate)` fixed), but add `ValueError` guard before `accept()` at `242` per 2.1 |
| D9 | `voice-pipeline-core` LM Studio | `LM_STUDIO_BASE_URL:49` must be reachable for `run_bot:112` | No health check | Add Task 0 `Depends: session-provisioning` or mock `OpenAILLMService` in `tests/test_voice_pipeline_core.py` |
| D10 | `voice-pipeline-core` singleton | `run_bot:112-116` `text_bridge` from `text-bridge-avatar` via `get_text_bridge:92` | `tasks.md:40` assumes exists, but `server.py:278-280` lazy import inside `lifespan` not in `design` | Add `Depends: text-bridge-avatar` to `tasks.md:40` |
| D11 | `voice-pipeline-core` Apple Silicon | `MLXModel.LARGE_V3_TURBO_Q4:134` OOM | `pyproject.toml:7` | Add mock note `when mlx unavailable` |
| D12 | `vonage-media-frontend`  | `1.1[x]` done, but `2.1-2.3` still `OT` global guard missing | `index.html:7` before `script.js:8` but `script.js:97` no `if(!window.OT)` | Add `assert window.OT` before `97` in task `2.1` |

## 2. Collision / Existing Spec Conflicts (Updated)

| # | Collision | Current State After Fixes | Impact | Proposal |
|---|-----------|---------------------------|--------|----------|
| C1 | **3-spec edit `server.py:71-99,132,233,277`** | `1.2` reuse + `lifespan` added by `audio-connector-bridge`, `1.3` `Request` removal by `session-provisioning:164`, `1.x` injection by `voice-pipeline-core:196` all touch same file but with comments (`TODO prod`, `Optional`) — still hotspot | Merge conflict if parallel PRs | Keep `audio-connector-bridge:1.2` as owner of `132` lifespan, others reference; add ownership matrix to `design.md` |
| C2 | **`static/script.js:29-224,282-316` 3 specs** | `connection-lifecycle:1.1` now owns `18,187,224,287` `wsAnamPingId` + `isConnected` in `onopen` (fixed), `text-bridge-avatar:1.2` owns `HasSendJson` (bot side, no collision), `vonage-media-frontend:1.1[x]` done | Duplicate `setInterval` leak now fixed in `connection-lifecycle` (previously `text-bridge-avatar` 5.1) — ownership clarified | Keep `text-bridge-avatar 5.1` as verification-only `clearInterval` assert, `connection-lifecycle 1.1/4.1` as implementer |
| C3 | `bot.py:54-110` shared | `text-bridge-avatar:1.2` changed `bot.py:8,67` to `HasSendJson` Protocol, `voice-pipeline-core:1.2` changed `140` to `set_messages` guard — same file, same region `54-110` but no overlap (different lines) | Low conflict but same PR | Clarify `design.md:32` split: `voice-pipeline-core` owns `LLMTextForwarder:96` insertion `Pipeline:172`, `text-bridge-avatar` owns `LLMTextBridgeProcessor:54` definition |
| C4 | `raw _http_client.delete` at `111-118` | Still `vng._http_client.delete(video_host, f"/v2/.../connect")` bypass SDK, `requirements.md:1.5` flagged | Breaks on SDK bump | Add `if hasattr(vng.video,"stop_audio_connector")` else raw in `server.py:111` (task `1.3`) |
| C5 | `CORSMiddleware` at `148` `allow_origins=["*"] allow_credentials=True` | Still `server.py:148-154` invalid, flagged only in `connection-lifecycle` 5.2, pending | Browser rejects | Keep demo but add comment `TODO prod: explicit origins` (task `connection-lifecycle 5.2`) |
| C6 | `hiddenDiv display:none` at `158` vs off-screen | `vonage-media-frontend:2.3` still `hiddenDiv.style.display='none'` (bug flagged), `tasks.md:28` says keep + TODO ( `frontend-shell` already fixed its `index.html:30` to comment) | Throttling risk retained as documented debt, not yet fixed to `position:fixed;left:-9999px` | Keep `2.3a` TODO (this PR) + `2.3b` follow-up per `requirements.md:5.2` |
| C7 | `subscriberContainer display:none` at `50` | `frontend-shell:2.1-2.2` now fixed `index.html:30` to comment, parent `50` remains `display:none` — correct per `audioOnly:true` | No collision now | Coordinate `frontend-shell:2.1` comment references `vonage-media-frontend 3.3` |

## 3. Granularity / Feasibility (Remaining Tasks)

| # | Spec / Task | Granularity Issue | Feasibility Fix |
|---|-------------|-------------------|-----------------|
| G1 | `frontend-shell` 3.1 `(P)` + done 2.1 same file `index.html:19,30` | Parallel `(P)` previously invalid, but `2.1/2.2` now `[x]` done, `3.1` edits `19` not `30` — now parallelizable with `4.1` (draft) but `3.1` + `4.1` both create `style.css` draft vs comment | Keep `3.1` sequential after `2.1` (already done), make `4.1` parallel with `3.2` |
| G2 | `frontend-shell` 4.1 `static/style.css` draft | Still `sed` diff not verifiable via CSS parser | Change observable to `bash sed -n '9,31p' index.html > style.css && diff -q` |
| G3 | `frontend-shell` 5.1 `ControlPanel` 10-log | Still needs `page.evaluate(()=>log())` but `TestClient` cannot exec ESM `esm.sh` | Split `5.1a` static DOM (no JS) `beautifulsoup` and `5.1b` Playwright E2E (requires `playwright`) |
| G4 | `session-provisioning` 2.1 `aiohttp` mocks | `import aiohttp` still inside handler at `171` complicates `respx` patching | Hoist `import aiohttp` to `server.py:1` (as D5) and split `2.1a` success, `2.1b` 401, `2.1c` KeyError guard `191` |
| G5 | `audio-connector-bridge` 1.1 regression | Marked `[x]` earlier but code lost lock → false completion | Revert `tasks.md:4` `1.1` to `[ ]`, split `1.1a` lock creation, `1.1b` wrap `78-99` without nesting `_stop` |
| G6 | `audio-connector-bridge` 2.1 | Mixes `ValueError` guard + serializer/transport | Split `2.1a` transport assert and `2.1b` pre-accept `ValueError` |
| G7 | `voice-pipeline-core` 2.1/2.2 `mlx` memory | `LARGE_V3_TURBO_Q4` OOM on CI | Mock `WhisperSTTServiceMLX.Settings` instantiation only |
| G8 | `text-bridge-avatar` 5.1 interval | `static/script.js:18,224,287` now fixed `wsAnamPingId` store + `clearInterval` in `disconnect` (connection-lifecycle 1.1), but `onclose:207-213` still not cleared | Add `5.1b` `clearInterval` in `onclose` as well |
| G9 | `vonage-media-frontend` 2.3 | Bundles style + track null + `videoSource:null` vs `audioSource:false` | Split `2.3a` style TODO, `2.3b` track extraction, `2.3c` opts |
| G10 | `connection-lifecycle` 2.1 5 mocks | Still `fetch`/`OT`/`WS` in one task | Split `2.1a` fetch, `2.1b` OT, `2.1c` WS |
| G11 | `ops-deployment` 2.1 lumps PID + trap | `pkill` → PID file vs `trap` two edits | Split `2.1a` PID-file, `2.1b` trap |

## 4. Reuse of Existing Assets (Updated)

| # | Spec | Now Reused Correctly After Fixes | Still Missed |
|---|------|----------------------------------|--------------|
| R1 | `frontend-shell` | `tests/conftest.py:3` + `TestClient(app)` now reused across `1.1,1.2,2.2,5.1` (was per-task inline) | `3.1/4.1` still each plan to edit `index.html:19,30` separately — should batch |
| R2 | `session-provisioning` | Reuse `server.py:30,37,44,50,59` helpers now correct; `12` `load_dotenv` single source `server.py:8-12` (bot deps removed) | `design.md:129-137` still invents `EnvHelper` class vs functions — keep functions |
| R3 | `audio-connector-bridge` | `server.py:9` `VonageFrameSerializer:242` + `FastAPIWebsocketTransport:249` reused; `_stop` reuse `vng` via `103` now correct | `bot.py:29` duplicate `VonageFrameSerializer` import dead — should delete as per proposal |
| R4 | `voice-pipeline-core` | `HasSendJson` Protocol at `bot.py:8` + `set_messages` guard at `140` now reuse public API | `bot.py:249` `VonageFrameSerializer` import still unused in `bot.py` (was `server.py` only) |
| R5 | `text-bridge-avatar` | `LLMTextBridgeProcessor:67` `set[HasSendJson]` now decoupled from `fastapi.WebSocket` | `server.py:297` `HasSendJson` still `WebSocket` at runtime — structural compatibility verified via `MockWS` test |
| R6 | `vonage-media-frontend` | `createAndPublish:131` helper reused for user `145` + avatar `160` | Still closure inside `connect()` (flagged `5.5`); hoist to `export function createAndPublish(session, container, opts)` |
| R7 | `ops-deployment` | `GET /health:158` reused by `start.sh:53` + future `HEALTHCHECK` | Polling loops `seq 1 30` still duplicated `start.sh:19-26` vs `52-63` — extract `wait_for_*()` |

---

## Cross-Spec Critical Path (Updated)

**Wave 1 Completed:** `frontend-shell 1.1,1.2,2.1,2.2 [x]`, `session-provisioning 1.1[x],1.2[x],1.3[x]`, `ops-deployment 1.1[x]` (via `tests/` harness)  
**Wave 2 Remaining:** `audio-connector-bridge 1.1` **regression** → fix lock, then `1.2` reuse/`lifespan` already `[x]` but needs lock, `1.3` raw DELETE, `2.1-3.1` → `voice-pipeline-core 2.1,2.2,3.1` → `text-bridge-avatar 2.1,5.1` (interval `onclose` split) → `vonage-media-frontend 2.1-2.3` → `connection-lifecycle 1.2` (Step1 degrade) + `5.2` CORS comment

**Shared risk:** `static/script.js:29-224,282-316` and `server.py:72,103,132,233,277` remain 3-spec hotspots — single PR per file or ownership matrix still recommended.

---

## Concrete Patch Checklist (Updated, No File Writes Yet)

**`frontend-shell/tasks.md`:** `1.1,1.2,2.1,2.2` now `[x]`; `3.1` add comment at `index.html:19` (`/* Vonage OT injects ... !important required */`) keeping `wc -l 59`; `3.2` change observable to `BeautifulSoup` `has attr playsinline`; `4.1` create `static/style.css` via `sed` diff; `5.1` split `5.1a` DOM only + `5.1b` Playwright; `6` keep `*` optional.

**`session-provisioning/tasks.md`:** Fix hoist `import aiohttp` to top; add `Path(__file__).parent` note `242`; keep `OSError` guard already done `37-42`.

**`audio-connector-bridge/tasks.md`:** Revert `1.1` to `[ ]` (regression), `1.2` keep `[x]` but add `vng` reuse verified, `1.3` keep raw fallback with `hasattr` probe; `2.1` split pre-accept `ValueError`; `2.2` add `ws://` warning.

**`voice-pipeline-core/tasks.md`:** `1.2` now `[x]` (guard done); `2.1,2.2,3.1` keep verification tests with mocks; add `tests/test_voice_pipeline_core.py` for order `Pipeline[1]==stt` etc.

**`text-bridge-avatar/tasks.md`:** `1.1[x],1.2[x]` done; `5.1` split `assign at 224` vs `clear at 287` + `207` `onclose` add `clearInterval`.

**`vonage-media-frontend/tasks.md`:** Add TODO at `script.js:158` `display:none` → off-screen, hoist `createAndPublish` to module scope.

**`connection-lifecycle/tasks.md`:** `1.1[x]` done (`isConnected` in `onopen:187`); `1.2` still `[ ]` (degrade Step1 `return` at `43` to continue); `4.1` interval now `[x]` done, but `5.2` CORS still `*` flagged.

**`ops-deployment/tasks.md`:** `1.1[x]` done; `2.1` still broad `pkill`; `Dockerfile:10-11` still `COPY pyproject.toml` only.

**`design.md` global:** Add `Path` resolution `server.py:37`, `HEALTHCHECK --interval=10s` after `Dockerfile:15`, remove `version: "3.9"` from compose.
