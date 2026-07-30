#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
TUNNEL_LOG="$SCRIPT_DIR/tunnel.log"
SERVER_LOG="$SCRIPT_DIR/server.log"

echo "=== Starting cloudflared tunnel ==="

pkill -f "cloudflared tunnel" 2>/dev/null || true
sleep 1

cloudflared tunnel --url http://localhost:8005 > "$TUNNEL_LOG" 2>&1 &
CLOUDFLARED_PID=$!
echo "cloudflared PID: $CLOUDFLARED_PID"

TUNNEL_URL=""
echo "Waiting for tunnel URL..."
for i in $(seq 1 30); do
    TUNNEL_URL=$(grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' "$TUNNEL_LOG" | head -n 1 || true)
    if [ -n "$TUNNEL_URL" ]; then
        echo "Found URL: $TUNNEL_URL"
        break
    fi
    sleep 1
done

if [ -z "$TUNNEL_URL" ]; then
    echo "Failed to get tunnel URL. Last 10 lines:"
    tail -n 10 "$TUNNEL_LOG"
    exit 1
fi

echo "Tunnel URL: $TUNNEL_URL"

echo "=== Starting server ==="
# Ensure port 8005 is free
for i in $(seq 1 10); do
    pid=$(lsof -ti:8005 2>/dev/null || true)
    if [ -z "$pid" ]; then
        break
    fi
    echo "Killing PID $pid holding port 8005 (attempt $i)..."
    kill -9 "$pid" 2>/dev/null || true
    sleep 1
done

cd "$SCRIPT_DIR" && nohup uv run python server.py > "$SERVER_LOG" 2>&1 &
echo "Server PID: $!"

echo "Waiting for server..."
for i in $(seq 1 30); do
    if curl -s http://localhost:8005/health > /dev/null 2>&1; then
        echo "Server is UP!"
        break
    fi
    if [ $i -eq 30 ]; then
        echo "Server failed to start. Check $SERVER_LOG"
        tail -n 20 "$SERVER_LOG"
        exit 1
    fi
    sleep 1
done

echo ""
echo "=== Done ==="
echo ""
echo "Open this URL in your browser:"
echo "${TUNNEL_URL}"
echo ""
echo "For Vonage Audio Connector, set WS_URI to:"
echo "${TUNNEL_URL}/ws"
echo ""
