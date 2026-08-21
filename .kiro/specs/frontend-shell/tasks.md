# Implementation Plan

- [x] 1. Verify existing shell implementation
- [x] 1.1 Confirm `static/index.html` layout and DOM sinks (P)
  - Parse `static/index.html` with BeautifulSoup; assert `video-row` grid, `userVideoContainer`, `avatarContainer>video#anam-avatar[autoplay][playsinline]`, `#subscriberContainer` hidden, `.container` 960px and dark theme
  - Verify `GET /` returns 200 with `video-row` via `TestClient`; verify `GET /static/script.js` 200 and `GET /favicon.ico` 204
  - Observable: all assertions pass without modifying `index.html`
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 4.1, 4.2, 4.3_
  - _Boundary: IndexHtmlLayout, StaticDelivery_
- [x] 1.2 Verify static delivery and favicon handling (P)
  - Test missing `/static/missing.js` returns 404 without stack trace; verify `StaticFiles(directory="static")` mount at `server.py:135` exists
  - Confirm `FileResponse("static/index.html")` at `server.py:152` and `Response(status_code=204)` at `server.py:148`
  - Observable: `pytest` 4 cases pass
  - _Requirements: 4.1, 4.2, 4.3, 4.4_
  - _Boundary: StaticDelivery_

- [x] 2. Fix redundant subscriber styling regression
- [x] 2.1 Remove ineffective `#subscriberContainer video {display:none}` rule
  - Inspect `static/index.html:30`; confirm parent `#subscriberContainer` has `display:none` making inner video rule redundant
  - Remove or replace rule with audio-only handling comment; keep file <60 lines
  - Verify `GET /` still 200 and rendered HTML no longer contains `#subscriberContainer video {display:none}` unless replaced
  - _Requirements: 6.1_
  - _Boundary: IndexHtmlLayout_
- [x] 2.2 Add regression guard for subscriber container
  - Add unit test asserting `#subscriberContainer` itself has `display:none` and no child video display rule exists after fix
  - Observable: test fails if rule reintroduced
  - _Requirements: 1.3, 6.1_
  - _Boundary: IndexHtmlLayout_

- [ ] 3. Address `!important` debt and avatar sink stability
- [ ] 3.1 Document `!important` justification and scope future fix (P)
  - Add comment in `static/index.html:19` referencing Vonage injection and `requirements-analysis-report.md` legacy; create follow-up issue for Shadow DOM or scoped CSS
  - No functional change; ensure video still covers with `object-fit:cover`
  - Observable: comment present and `GET /` visual regression unchanged
  - _Requirements: 1.6, 6.2_
  - _Boundary: IndexHtmlLayout, AvatarVideoSink_
- [ ] 3.2 Verify avatar sink `playsinline` and fallback
  - Confirm `video#anam-avatar` has `autoplay playsinline` and `background:#000` wrapper; test `anamStream==null` path shows black wrapper without error
  - Observable: Playwright check `anam-avatar` has `playsinline` attribute
  - _Requirements: 2.1, 2.2, 2.3, 5.5_
  - _Boundary: AvatarVideoSink_

- [ ] 4. Prepare production CSS extraction path
- [ ] 4.1 Draft extraction plan without breaking zero-build (P)
  - Create `static/style.css` candidate draft and note in `design.md` Supporting References; keep current inline `<style>` as primary to preserve `5.2` zero-build
  - Verify both inline and extracted would produce identical `video-row` and `.log` rules
  - Observable: draft file exists but not yet served; no behavior change
  - _Requirements: 5.2, 6.3_
  - _Boundary: IndexHtmlLayout_

- [ ] 5. Verify controls and status/log behavior (integration with lifecycle)
- [ ] 5.1 Validate `ControlPanel` DOM and log mechanics (P)
  - Check `button#connectBtn.connect` label `接続`, green `#22c55e`, `#status` `切断されています`, `log(msg)` appends `[time] msg` via `textContent` and auto-scroll
  - Confirm `html lang="ja"` at `2` and `disabled` opacity rule at `26`
  - Observable: DOM parse + Playwright E2E `GET /` shows Connect button green and log auto-scroll on 10 dummy logs
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 5.1, 5.3, 5.4_
  - _Boundary: ControlPanel_

- [ ]* 6. Optional visual regression baseline
  - Capture Playwright screenshot baseline for `GET /` two-pane layout; store under `tests/visual/__snapshots__`
  - _Requirements: 1.1, 3.1_
