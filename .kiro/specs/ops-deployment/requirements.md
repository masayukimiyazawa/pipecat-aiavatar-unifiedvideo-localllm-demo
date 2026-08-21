# Requirements Document

## Introduction

Ops Deployment owns the operational layer: health check, Cloudflare Tunnel, server startup management, Dockerization, and dependency management. It integrates `GET /health` at `server.py:155`, `cloudflared tunnel --url :8005` and tunnel URL polling at `start.sh:8`, port release and `uv run python server.py` startup plus `curl /health` wait at `start.sh:36`, `python:3.13-slim` and `uv pip install` at `Dockerfile:1`, `WS_URI` propagation and `private.key` volume at `docker-compose.yml:1`, and `pipecat-ai[mlx-whisper,openai,silero,websocket]>=1.4.0` dependencies at `pyproject.toml:1` to achieve public exposure via `https://*.trycloudflare.com` in both local and container environments.

## Boundary Context (Optional)
- **In scope**: `GET /health`, tunnel startup and URL acquisition, port conflict resolution, server startup and health wait, Docker build/run, dependency declaration
- **Out of scope**: Vonage/Anam token issuance, voice pipeline, text delivery, OT/Anam SDK operations, screen layout
- **Adjacent expectations**: `session-provisioning` requires `VONAGE_*`/`ANAM_*` and references `WS_URI`, `audio-connector-bridge` references `VONAGE_AUDIO_RATE`, `frontend-shell` does not depend on `GET /health` success (independent health)

## Requirements

### Requirement 1: Health Check

**Objective:** As an operator, I want to verify server liveness via HTTP, so that startup scripts and load balancers can determine health

#### Acceptance Criteria
1. When `GET /health` is called, the Ops Deployment shall return `{"ok": True}` as 200 JSON at `server.py:157`
2. When `GET /health` is called frequently, the Ops Deployment shall respond within 10ms without authentication or external API calls
3. The Ops Deployment shall make `GET /health` usable both for `curl -s http://localhost:8005/health` at `start.sh:53` and external monitoring in `docker-compose` — no auth, no rate limit

### Requirement 2: Cloudflare Tunnel Startup

**Objective:** As a developer, I want to expose the local server via `https://*.trycloudflare.com`, so that Vonage Audio Connector can reach it via `wss://`

#### Acceptance Criteria
1. When `bash start.sh` is executed, the Ops Deployment shall stop existing tunnels via `pkill -f "cloudflared tunnel" 2>/dev/null || true; sleep 1` (`start.sh:10`) — note: `pkill -f "cloudflared tunnel"` is overly broad and may kill unrelated `cloudflared` processes (legacy flagged; should use PID file or `cloudflared tunnel delete`)
2. When stopped, the Ops Deployment shall start in background via `cloudflared tunnel --url http://localhost:8005 > "$TUNNEL_LOG" 2>&1 &` and record PID (`start.sh:13`) — `CLOUDFLARED_PID` is logged but never used for cleanup (gap flagged; should trap EXIT and kill PID)
3. When within 30 seconds after start, the Ops Deployment shall poll `grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG"` every second and take the first match as `TUNNEL_URL` (`start.sh:19`) — regex assumes lowercase alphanum and hyphen only; future `trycloudflare` domains with other chars will fail (implicit rule now explicit)
4. If URL is not found within 30 seconds, then the Ops Deployment shall output `tail -n 10 "$TUNNEL_LOG"` and exit with `exit 1` (`start.sh:28`)
5. When `TUNNEL_URL` is obtained, the Ops Deployment shall output `Tunnel URL: $TUNNEL_URL` and `echo "${TUNNEL_URL}/ws"` as the recommended `WS_URI` value (`start.sh:34`, `71`) — note: `WS_URI` is printed but not exported unless user manually sets env (gap flagged; should auto-export or write to `.env`)

### Requirement 3: Server Startup Management

**Objective:** As a developer, I want port conflicts auto-resolved and the server started, so that manual `kill` is not needed on re-run

#### Acceptance Criteria
1. When entering the server startup phase in `start.sh`, the Ops Deployment shall obtain occupying PID via `lsof -ti:8005` at `start.sh:38` and if present attempt `kill -9` up to 10 times at 1-second intervals — note: `lsof` may not be installed in Docker/minimal images (gap flagged; should use `fuser` or `ss` fallback)
2. When the port is free, the Ops Deployment shall start via `cd "$SCRIPT_DIR" && nohup uv run python server.py > "$SERVER_LOG" 2>&1 &` (`start.sh:48`) — `nohup` leaves orphaned process on script exit; should use `exec` or `systemd` (legacy flagged)
3. When within 30 seconds after start, the Ops Deployment shall poll `curl -s http://localhost:8005/health` every second and on success output `Server is UP!` (`start.sh:52`)
4. If health does not succeed within 30 seconds, then the Ops Deployment shall output `tail -n 20 "$SERVER_LOG"` and exit with `exit 1` (`start.sh:57`) — existing tunnel is not cleaned up on this exit (gap flagged)
5. When startup succeeds, the Ops Deployment shall output `Open this URL in your browser:` and `echo "$TUNNEL_URL"` (`start.sh:68`)

### Requirement 4: Dockerization

**Objective:** As an operator, I want to run the server reproducibly in a container, so that environment differences are absorbed

#### Acceptance Criteria
1. When `docker build` is executed, the Ops Deployment shall execute `FROM python:3.13-slim-bookworm` and `apt-get install build-essential curl` at `Dockerfile:1` — note: `python:3.13` does not match `pyproject.toml` `requires-python >=3.11` but satisfies it; should pin to `3.11` or `3.13` explicitly (gap flagged)
2. When installing dependencies, the Ops Deployment shall resolve `pyproject.toml` via `pip install uv && uv pip install --system -r pyproject.toml` at `Dockerfile:11` — note: this ignores `uv.lock` for reproducibility (bug flagged; shall copy `uv.lock` and run `uv sync --frozen` or `uv pip install --system -r uv.lock`)
3. When the container starts, the Ops Deployment shall start the server via `EXPOSE 8005` and `CMD ["uv","run","python","server.py"]` (`Dockerfile:15`) — `EXPOSE` is documentation only; no healthcheck is defined (gap flagged; should add `HEALTHCHECK CMD curl -f http://localhost:8005/health`)
4. When `docker compose up` is executed, the Ops Deployment shall apply `env_file: .env` and `environment: WS_URI=${WS_URI:-ws://localhost:8005/ws}` and `volumes: ./private.key:/app/private.key:ro` at `docker-compose.yml:8`
5. When `WS_URI` is unset, the Ops Deployment shall default to `ws://localhost:8005/ws` so Vonage Audio Connector can connect from within the container —note: `ws://` without TLS will be rejected by Vonage in production; should default to `wss` when tunnel URL is used (gap flagged)

### Requirement 5: Dependency Management

**Objective:** As a developer, I want Python dependencies managed reproducibly via `uv`, so that the same versions are used locally and in containers

#### Acceptance Criteria
1. When `uv sync` is executed, the Ops Deployment shall resolve `requires-python >=3.11` and `dependencies` (`pipecat-ai[mlx-whisper,openai,runner,silero,websocket,whisper]>=1.4.0`, `vonage>=3.3.1`, `vonage-video`, `python-dotenv`, `uvicorn[standard]`, `fastapi`, `anam`) at `pyproject.toml:5` based on `uv.lock`
2. The Ops Deployment shall commit `uv.lock` and use the same lock in `Dockerfile` for reproducibility — current `Dockerfile:10` only copies `pyproject.toml` (bug flagged)
3. If `VONAGE_PRIVATE_KEY` points to file `private.key`, then the Ops Deployment shall ensure `private.key` is not committed via `.gitignore:9`
4. The Ops Deployment shall exclude `.env` and `*.log` from commits via `.gitignore:6,10` — `tunnel.log` and `server.log` will otherwise leak tunnel URLs
5. When `docker-compose.yml` at `docker-compose.yml:1` declares `version: "3.9"`, the Ops Deployment shall note that `version` is deprecated in Compose spec v2 and shall be removed (legacy flagged)

### Requirement 6: Non-Functional, Security, and Constraints

**Objective:** As a system, I want the operational layer secure and observable, so that public URL and private key leakage are prevented while failures are detectable

#### Acceptance Criteria
1. The Ops Deployment shall mount `private.key` with permission `ro` (read-only) to prohibit overwriting from within the container
2. The Ops Deployment shall gitignore `TUNNEL_LOG` and `SERVER_LOG` as `*.log` via `.gitignore` to prevent accidental commit of tunnel URLs or stack traces
3. When `cloudflared` is not installed, the Ops Deployment shall have `start.sh` fail immediately with `cloudflared: command not found` due to `set -e` without entering `GET /health` wait — no explicit check is present (gap flagged; should add `command -v cloudflared || exit`)
4. If `VONAGE_AUDIO_RATE` differs between container and host, then the Ops Deployment shall prioritize propagation via `environment` in `docker-compose.yml` and reflect host `.env` value into the container
5. The Ops Deployment shall expose `GET /health` without authentication while other `POST /api/*` return 500 on missing env, separating health from business API responsibilities
6. The Ops Deployment shall note that `start.sh` never cleans up `cloudflared` or `uv run` server on exit or SIGINT — shall add `trap "kill $CLOUDFLARED_PID $SERVER_PID; exit" INT TERM EXIT` (legacy flagged)
