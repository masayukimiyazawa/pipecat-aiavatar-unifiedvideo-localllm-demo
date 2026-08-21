# Implementation Plan

- [x] 1. Implement health endpoint contract
- [x] 1.1 Ensure `GET /health` 200 `{"ok": true}` fast path (P)
  - Verify `@app.get("/health")` at `155` returns `JSONResponse({"ok": True})` at `157` with 200 and <10ms, no auth, no external calls
  - Test `TestClient GET /health` → 200 `{"ok": true}`; `curl -s http://localhost:8005/health` from `start.sh:53` succeeds within 1s
  - _Requirements: 1.1, 1.2, 1.3, 6.5_
  - _Boundary: HealthEndpoint_

- [ ] 2. Harden tunnel orchestration
- [ ] 2.1 Fix `pkill` broadness and add `CLOUDFLARED_PID` trap (P)
  - Replace `pkill -f "cloudflared tunnel"` at `10` with PID-file or `pgrep -f "cloudflared tunnel --url http://localhost:8005"` narrow; store `CLOUDFLARED_PID=$!` at `14` and add `trap 'kill $CLOUDFLARED_PID 2>/dev/null || true; exit' INT TERM EXIT` at top after `SCRIPT_DIR`
  - Verify `bash -n start.sh` passes and `trap` present
  - _Requirements: 2.1, 6.6_
  - _Boundary: TunnelOrchestration_
- [ ] 2.2 Verify tunnel URL extraction and `WS_URI` suggestion (P)
  - Ensure `grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG"` poll 30s at `19` captures `TUNNEL_URL` and prints `Tunnel URL: $TUNNEL_URL` at `34` and `${TUNNEL_URL}/ws` at `71-72`; document regex assumes lowercase hyphen (implicit rule) and `WS_URI` not auto-exported (gap)
  - Test mock `tunnel.log` with `https://abc-123.trycloudflare.com` → extracted correctly
  - _Requirements: 2.2, 2.3, 2.4, 2.5_
  - _Boundary: TunnelOrchestration_
- [ ] 2.3 Add explicit `cloudflared` check and failure handling
  - Add `command -v cloudflared >/dev/null 2>&1 || { echo "cloudflared not found"; exit 1; }` before `cloudflared tunnel` at `13` to avoid entering health wait; keep `set -e` behavior but make error explicit
  - Observable: `PATH` without `cloudflared` → `start.sh` exits before `Waiting for tunnel URL...`
  - _Requirements: 2.1, 6.3_
  - _Boundary: TunnelOrchestration_

- [ ] 3. Harden server startup management
- [ ] 3.1 Add `lsof` fallback and clean nohup on health failure
  - Keep `lsof -ti:8005` loop at `38` but add fallback `if ! command -v lsof; then echo "lsof missing, skip kill"; else ... fi` with `ss -lpt` alternative comment; on `curl /health` failure at `57` (`tail -n 20 server.log; exit 1`) also `kill $CLOUDFLARED_PID` before exit (gap)
  - Test missing `lsof` → script continues; health failure → tunnel killed
  - _Requirements: 3.1, 3.4, 6.3, 6.6_
  - _Boundary: ServerStartup_
- [ ] 3.2 Verify `nohup uv run` and health poll loop
  - Ensure `cd "$SCRIPT_DIR" && nohup uv run python server.py > "$SERVER_LOG" 2>&1 &` at `48` and `for i in 1..30; curl -s http://localhost:8005/health; echo Server is UP!` at `52`; final `echo Open this URL: $TUNNEL_URL` at `68`
  - Observable: `bash start.sh` with mocked server → `Server is UP!` within 30s
  - _Requirements: 3.2, 3.3, 3.5_
  - _Boundary: ServerStartup_

- [ ] 4. Fix Docker reproducibility and Compose deprecation
- [ ] 4.1 Make Dockerfile use `uv.lock` and add `HEALTHCHECK` (P)
  - Change `COPY pyproject.toml .` at `10` to `COPY pyproject.toml uv.lock .` and `RUN pip install uv && uv pip install --system -r pyproject.toml` at `11` to `RUN uv sync --frozen` or `uv pip install --system -r uv.lock`; add `HEALTHCHECK CMD curl -f http://localhost:8005/health || exit 1` after `EXPOSE 8005` at `14`
  - Verify `docker build` without `uv.lock` fails with `--frozen` (reproducibility)
  - _Requirements: 4.1, 4.2, 4.3, 5.1, 5.2_
  - _Boundary: ContainerImage_
- [ ] 4.2 Fix compose `WS_URI` default and `version` deprecation (P)
  - Remove `version: "3.9"` at `1` (deprecated); keep `env_file: .env` at `8`, `environment: WS_URI=${WS_URI:-ws://localhost:8005/ws}` at `10` but document prod should be `wss://` when tunnel (gap); keep `volumes: ./private.key:/app/private.key:ro` at `12` and `ports: "8005:8005"`
  - Verify `docker compose config` no `version` field and `WS_URI` defaults correctly
  - _Requirements: 4.4, 4.5, 5.3, 6.1, 6.4_
  - _Boundary: ComposeService_

- [ ] 5. Ensure dependency and gitignore contracts
- [ ] 5.1 Verify `pyproject.toml` / `uv.lock` / `.gitignore` triad (P)
  - Ensure `pyproject.toml:5` `requires-python >=3.11` and deps `pipecat-ai[...]`, `vonage`, `vonage-video`, `python-dotenv`, `uvicorn[standard]`, `fastapi`, `anam`; ensure `.gitignore:6` `.env`, `9` `private.key`, `10` `*.log` prevent `tunnel.log`/`server.log` leakage; `uv.lock` committed
  - Observable: `grep -c private.key .gitignore` ==1 and `ls uv.lock` exists
  - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 6.2_
  - _Boundary: DependencyManagement_

- [ ]* 6. Optional E2E deployment test
  - `docker compose up --build -d` → `curl http://localhost:8005/health` 200 within 10s; `bash start.sh` with mocked `cloudflared` → `TUNNEL_URL` printed
  - _Requirements: 1.1, 2.3, 3.3_
