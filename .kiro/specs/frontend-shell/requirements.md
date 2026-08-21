# Requirements Document

## Introduction

Frontend Shell owns the single-page UI and static asset delivery for the AI Avatar Assistant. It integrates the two-pane layout (`static/index.html:33` left: user video `あなた`, right: avatar video `AIアバター`), connection controls (`static/index.html:52` `connectBtn` / `statusEl` / `logEl`), avatar video rendering area (`static/index.html:19` `anam-avatar`) and static delivery (`server.py:135` `StaticFiles` / `server.py:150` `GET /` / `server.py:146` `GET /favicon.ico`) to provide the visual foundation for downstream Vonage/Anam integration.

## Boundary Context (Optional)
- **In scope**: Screen layout and CSS, video element placement, status/log display, HTTP handling for static file delivery
- **Out of scope**: Vonage session connection logic, Anam SDK initialization, LLM integration, audio processing, tunnel/deployment
- **Adjacent expectations**: `session-provisioning` provides `/api/*`, `vonage-media-frontend` injects video into `userVideoContainer`/`anam-avatar`, `connection-lifecycle` controls `connectBtn` state transitions

## Requirements

### Requirement 1: Single-Page Layout

**Objective:** As a user, I want a centered 960px two-pane layout that shows myself and the avatar side-by-side, so that I can perceive the face-to-face conversation context visually

#### Acceptance Criteria
1. When a user accesses `GET /`, the Frontend Shell shall return the `video-row` grid (1fr 1fr) with two `video-panel` elements at `static/index.html:33`
2. When the screen is rendered, the Frontend Shell shall display heading `あなた` (You) with `#userVideoContainer` in the left panel and heading `AIアバター` (AI Avatar) with `#avatarContainer > video#anam-avatar[autoplay][playsinline]` in the right panel — literal Japanese text as in `static/index.html:40,44`
3. The Frontend Shell shall keep `#subscriberContainer` in the DOM with `display:none` at `static/index.html:50`
4. The Frontend Shell shall apply `.container {max-width: 960px; margin: 0 auto; padding:24px}` and the dark theme (`background:#111; color:#eee`) at `static/index.html:11-12`
5. When the viewport width changes, the Frontend Shell shall preserve a square aspect ratio via `video-wrapper::after {padding-bottom:100%}` at `static/index.html:20`
6. When Vonage SDK injects its own video styles, the Frontend Shell shall override with `video {width:100% !important; height:100% !important; object-fit:cover !important; position:absolute !important}` at `static/index.html:19` to prevent layout breakage (implicit rule now explicit)

### Requirement 2: Avatar Video Rendering Area

**Objective:** As a user, I want the Anam avatar video to fill the right pane, so that I can observe facial expressions and lip-sync

#### Acceptance Criteria
1. When `anamStream` is obtained, the Frontend Shell shall provide a rendering area via `anamVideo.srcObject = anamStream; anamVideo.play()` at `static/script.js:84`
2. The Frontend Shell shall apply `video#anam-avatar {width:100%; height:100%; object-fit:cover; border-radius:8px; position:absolute; top:0; left:0}` at `static/index.html:21`
3. While `anamStream` is not yet obtained, the Frontend Shell shall display an empty wrapper with black background (`background:#000`) without throwing an error

### Requirement 3: Connection Controls and Status Display

**Objective:** As a user, I want the connect/disconnect button, current status, and log to be clearly visible, so that I can understand the progress and result of the connection flow

#### Acceptance Criteria
1. When initially displayed, the Frontend Shell shall show `button#connectBtn.connect` with label `接続` (Connect) and green background `#22c55e`, and `#status` with `切断されています` (Disconnected) at `static/index.html:53,55`
2. When `connectBtn` is not clickable, the Frontend Shell shall apply `button:disabled {opacity:.5; cursor:not-allowed}` at `static/index.html:26`
3. When `log(msg)` is called, the Frontend Shell shall append `[time] msg` to `#log` at `static/script.js:20` via `d.textContent` (XSS-safe) and auto-scroll via `scrollTop = scrollHeight`
4. The Frontend Shell shall apply `.log {max-height:180px; overflow-y:auto; font-size:.75rem; color:#666}` at `static/index.html:28`
5. When the status changes, the Frontend Shell shall update `#status` text to one of the four Japanese literals: `切断されています` / `セッション作成中...` / `会話中...` / `接続失敗` as set by `static/script.js:31,44,59,220`

### Requirement 4: Static Delivery and Favicon

**Objective:** As a system operator, I want static assets served correctly from FastAPI, so that the browser can fetch the page and scripts from a single origin

#### Acceptance Criteria
1. When `GET /` is requested, the Frontend Shell shall return `FileResponse("static/index.html")` at `server.py:152`
2. When `GET /static/script.js` etc. is requested, the Frontend Shell shall serve via `StaticFiles(directory="static")` at `server.py:135`
3. When `GET /favicon.ico` is requested, the Frontend Shell shall return `Response(status_code=204)` at `server.py:148` without polluting logs
4. If a static file does not exist, then the Frontend Shell shall return 404 without exposing a stack trace

### Requirement 5: Non-Functional Constraints

**Objective:** As a developer, I want Frontend Shell to be lightweight, secure, and accessible, so that it remains stable even in demo environments

#### Acceptance Criteria
1. The Frontend Shell shall limit external dependencies to two: `opentok.min.js` and `esm.sh/@anam-ai/js-sdk`, requiring no bundler
2. The Frontend Shell shall keep `index.html` within 60 lines (currently 59) and keep CSS inline in `<style>` so no additional build is required
3. If the browser blocks `autoplay`, then the Frontend Shell shall log the exception without swallowing it and continue subsequent processing (audio can play after user interaction)
4. The Frontend Shell shall declare `<html lang="ja">` at `static/index.html:2` to match the Japanese UI literals
5. The Frontend Shell shall set `playsinline` on the `video` element to prevent forced fullscreen on iOS Safari

### Requirement 6: Known Issues and Implicit Rules (Refactoring Candidate)

**Objective:** As a maintainer, I want unnecessary or fragile patterns explicitly flagged for future refactoring, so that negative legacy is not perpetuated

#### Acceptance Criteria
1. When `#subscriberContainer` is styled, the Frontend Shell shall note that `#subscriberContainer video {max-width:100%; border-radius:8px; display:none}` at `static/index.html:30` is redundant because the parent has `display:none` — the rule never renders and shall be removed or changed to audio-only output handling
2. The Frontend Shell shall note that `!important` overrides at `static/index.html:19` are required today due to Vonage SDK injecting inline styles, but shall be refactored to a scoped CSS solution or Shadow DOM to avoid `!important` debt
3. The Frontend Shell shall note that inline `<style>` in `index.html` is intentional for demo zero-build, but for production shall be extracted to `static/style.css` and served via `StaticFiles` to enable caching and CSP
