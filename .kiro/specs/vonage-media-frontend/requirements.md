# Requirements Document

## Introduction

Vonage Media Frontend owns browser-side Vonage Video media control. It integrates `OT.initSession` / `session.connect` / `session.on('streamCreated'/'streamDestroyed')` at `static/script.js:97` and `createAndPublish` at `static/script.js:131` (Promise-wrapped `OT.initPublisher` + `session.publish`) for dual publishers (user cam+mic and Anam MediaStream) and subscriber (`audioOnly:true`), multiplexing user and avatar video/audio in a single Vonage session using `application_id`/`session_id`/`token` issued by `session-provisioning`.

## Boundary Context (Optional)
- **In scope**: OT session creation/connection, dual publishers, subscriber, hidden div for avatar publish, stream event handling
- **Out of scope**: Anam SDK init/TTS (`text-bridge-avatar`), REST issuance (`session-provisioning`), screen layout (`frontend-shell`), overall 5-step orchestration state transitions (`connection-lifecycle`)
- **Adjacent expectations**: `session-provisioning` supplies `application_id/session_id/token`, `text-bridge-avatar` supplies `anamStream`, `frontend-shell` provides DOM `userVideoContainer`/`anam-avatar`/`subscriberContainer`, `audio-connector-bridge` receives audio via Audio Connector in the same session

## Requirements

### Requirement 1: Vonage Session Connection

**Objective:** As a browser, I want to connect to a Vonage session with publisher privileges, so that I can send and receive audio/video

#### Acceptance Criteria
1. When `vonageData` (`application_id`, `session_id`, `token`) is obtained, the Vonage Media Frontend shall execute `session = OT.initSession(application_id, session_id)` (`static/script.js:97`)
2. When `session.on('streamCreated')` fires, the Vonage Media Frontend shall exclude own streams via `if (!session || !session.connection) return` and `if (event.stream.connection.connectionId === session.connection.connectionId) return` (`static/script.js:100`) — prevents self-subscription (implicit rule now explicit)
3. When the stream is not own and `subscriber` is not yet created, the Vonage Media Frontend shall execute `session.subscribe(event.stream, subscriberContainer, {audioOnly:true, enableAudio:true}, callback)` and on success log `Audio subscription started`, on failure log `Subscribe error: {msg}` (`static/script.js:104`)
4. When an exception occurs inside the `streamCreated` handler, the Vonage Media Frontend shall log `Stream processing error: {msg}` without propagating (`static/script.js:113`) — prevents one bad stream from breaking the session
5. When `session.on('streamDestroyed')` fires, the Vonage Media Frontend shall reset `subscriber = null` (`static/script.js:118`) — allows future `streamCreated` to resubscribe (implicit rule now explicit)
6. When `session.connect(token)` is called, the Vonage Media Frontend shall promisify via `new Promise((resolve,reject)=> session.connect(token, err=> err?reject:resolve))` and on success log `Vonage session connected` (`static/script.js:122`)

### Requirement 2: Dual Publishers (User + Avatar)

**Objective:** As a browser, I want to publish both user camera/mic and avatar MediaStream to the same session, so that recording and unified management are possible

#### Acceptance Criteria
1. When a user publisher is needed, the Vonage Media Frontend shall call `createAndPublish(userVideoContainer, {videoSource:true, audioSource:true})`, save to `userPublisher`, and on success log `User publish complete`, on failure log `User publish error: {msg}` (`static/script.js:145`)
2. When `createAndPublish` is called, the Vonage Media Frontend shall execute `OT.initPublisher(container, opts, err=> {...})` and on `err` `reject`, on success `session.publish(pub, err=> err?reject:resolve)` (`static/script.js:131`)
3. When `anamStream` exists and `getVideoTracks()[0]` or `getAudioTracks()[0]` exists, the Vonage Media Frontend shall append a hidden div to `document.body` via `document.createElement('div')` at `static/script.js:156` — currently `hiddenDiv.style.display='none'` (bug flagged: `display:none` may cause browser to throttle/Suspend MediaStream publishing; should use `visibility:hidden` or off-screen `position:fixed; left:-9999px`)
4. When the hidden div is created, the Vonage Media Frontend shall generate `anamPublisher` via `createAndPublish(hiddenDiv, {videoSource: anamVideoTrack || null, audioSource: anamAudioTrack || false})` at `static/script.js:160` — note: `videoSource: null` creates audio-only publisher; `audioSource: false` disables audio (implicit rule now explicit)
5. If `anamStream` is null, then the Vonage Media Frontend shall skip avatar publish and continue with user publish only
6. If both `getVideoTracks`/`getAudioTracks` are empty at `static/script.js:155`, then the Vonage Media Frontend shall not call `createAndPublish` — prevents empty publisher error

### Requirement 3: Subscriber Audio Subscription

**Objective:** As a browser, I want to subscribe to server audio via Audio Connector (Pipecat `transport.output`), so that future server TTS audio can be played

#### Acceptance Criteria
1. When a stream from another participant (Audio Connector) is created, the Vonage Media Frontend shall subscribe to `subscriberContainer` with `audioOnly:true, enableAudio:true` — `audioOnly:true` prevents creating a video element for audio-only stream
2. While `subscriber` exists, the Vonage Media Frontend shall guard with `if (subscriber) return` at `static/script.js:103` to avoid double subscription on new `streamCreated` events — only the first remote stream is subscribed (implicit rule now explicit; additional remote streams will be ignored, which is intentional for 1:1 demo but shall be documented as limitation)
3. When `subscriber` audio arrives, the Vonage Media Frontend shall play via browser audio output without showing video (no video element due to `audioOnly:true`) — note: `subscriberContainer` at `static/index.html:50` has `display:none`, so audio must play without visible video; if Vonage requires visible element for audio, this is a bug (flagged)
4. If `session.subscribe` fails with `OT` error (e.g., `OT_NOT_CONNECTED`), then the Vonage Media Frontend shall log `Subscribe error: {msg}` and not retry (negative legacy: should add retry with backoff)

### Requirement 4: Error Handling and Degradation

**Objective:** As a user, I want remaining functionality to continue even if one media publish fails, so that conversation can be attempted when either camera or avatar fails

#### Acceptance Criteria
1. If `userPublisher` `createAndPublish` fails, then the Vonage Media Frontend shall only log and proceed to avatar publish — does not abort session (degradation now explicit)
2. If `anamPublisher` `createAndPublish` fails, then the Vonage Media Frontend shall only log and proceed to ws-anam connection
3. If `session.connect` fails, then the Vonage Media Frontend shall log `Vonage connection error: {msg}` and execute `setStatus('Connection failed')` and `connectBtn.disabled=false` then `return` (`static/script.js:171`) — note: `vonage-media-frontend` currently delegates status update to `connection-lifecycle`; duplicated responsibility (gap flagged)
4. The Vonage Media Frontend shall propagate `OT.initPublisher` errors via `reject(err)` to the Promise and aggregate via `try/catch` — no retry is attempted (negative legacy)
5. If the browser denies camera/mic permission at `static/script.js:145`, then the Vonage Media Frontend shall log `User publish error: {msg}` via `OT.initPublisher` error callback and keep session connected — permission denial does not disconnect session (implicit rule now explicit)

### Requirement 5: Security, Constraints, and Non-Functional

**Objective:** As a system, I want Vonage media multiplexed securely and observably, so that privilege escalation and resource leaks are prevented

#### Acceptance Criteria
1. The Vonage Media Frontend shall use `token` with `role` fixed to `publisher` (`server.py:52`) and shall not attempt publish with `subscriber` privilege
2. The Vonage Media Frontend shall keep `anamPublisher` hidden div without visible duplicate video — shall use non-display-none technique after refactoring (see Requirement 2, criterion 3)
3. When `disconnect()` is called, the Vonage Media Frontend shall attempt sequentially `try { if (anamPublisher) session.unpublish(anamPublisher)}` and `unpublish(userPublisher)` and `session.disconnect()` with each `catch` swallowing exceptions (`static/script.js:282`) — order matters: unpublish before disconnect
4. The Vonage Media Frontend shall not log the full `session_id`; only the truncated form `slice(0,8)...` shall be logged (`static/script.js:56`) — security now explicit
5. The Vonage Media Frontend shall note that `createAndPublish` at `static/script.js:131` is defined inside `connect()` closure, recreating the function per connection — shall be hoisted to module scope to avoid reallocation (legacy flagged)
6. The Vonage Media Frontend shall note that `subscriberContainer` at `static/index.html:50` with `display:none` may prevent audio playback in some browsers — subscriber should publish to a visible but off-screen element or audio-only sink (gap flagged)
