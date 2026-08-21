import asyncio
import os
import warnings
from contextlib import asynccontextmanager
from typing import Optional

import uvicorn
from dotenv import load_dotenv

# Single source for env loading at process entry; keep override=True for demo
# TODO(prod): change to override=False or gate with ENV=production to respect injected secrets
load_dotenv(override=True)

from fastapi import FastAPI, HTTPException, Request, WebSocket
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from loguru import logger
from bot import bot
from pipecat.runner.types import WebSocketRunnerArguments
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from vonage import Auth, Vonage
from vonage_http_client import HttpClientOptions
from vonage_video import AudioConnectorOptions, TokenOptions
from vonage_video.models.audio_connector import AudioConnectorWebSocket

warnings.filterwarnings("ignore", message="'asyncio.iscoroutinefunction' is deprecated")


def _require_env(name: str) -> str:
    val = os.getenv(name)
    if not val:
        raise HTTPException(status_code=500, detail=f"Missing env var: {name}")
    return val


def _read_private_key(value: str) -> str:
    if value.startswith("-----"):
        return value
    with open(value) as f:
        return f.read()


def _create_vonage_client(application_id: str, private_key: str) -> Vonage:
    auth = Auth(application_id=application_id, private_key=private_key)
    options = HttpClientOptions(video_host="video.api.vonage.com", timeout=30)
    return Vonage(auth=auth, http_client_options=options)


def _generate_client_token(vng: Vonage, session_id: str) -> str:
    raw = vng.video.generate_client_token(
        TokenOptions(session_id=session_id, role="publisher")
    )
    if isinstance(raw, bytes):
        return raw.decode("utf-8")
    return str(raw)


async def _create_session_async(vng: Vonage) -> str:
    loop = asyncio.get_running_loop()
    session_id = await loop.run_in_executor(
        None, lambda: vng.video.create_session().session_id
    )
    logger.info(f"Created Vonage session: {session_id}")
    return session_id


_active_connectors: dict[str, object] = {}


async def _connect_audio_connector_async(
    vng: Vonage, session_id: str, ws_uri: str, audio_rate: int
) -> None:
    for old_sid in list(_active_connectors.keys()):
            await _stop_audio_connector_async(old_sid, vng)

    logger.info(
        f"Connecting Audio Connector: session={session_id}, ws={ws_uri}, rate={audio_rate}"
    )
    token = _generate_client_token(vng, session_id)
    audio_opts = AudioConnectorOptions(
        session_id=session_id,
        token=token,
        websocket=AudioConnectorWebSocket(
            uri=ws_uri,
            audio_rate=audio_rate,
            bidirectional=True,
        ),
    )

    loop = asyncio.get_running_loop()
    connector = await loop.run_in_executor(
        None, lambda: vng.video.start_audio_connector(audio_opts)
    )
    _active_connectors[session_id] = connector
    logger.info(f"Audio Connector started: id={connector.id}")


async def _stop_audio_connector_async(session_id: str, vng: Optional[Vonage] = None) -> None:
    if vng is None:
        vng = _get_video_client()
    connector = _active_connectors.pop(session_id, None)
    if connector is None:
        return
    try:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(
            None,
            lambda: vng._http_client.delete(
                vng._http_client.video_host,
                f"/v2/project/{vng._http_client.auth.application_id}/connect"
                f"?sessionId={session_id}",
            ),
        )
        logger.info(f"Stopped Audio Connector for session {session_id}")
    except Exception as e:
        logger.warning(f"Failed to stop Audio Connector: {e}")


def _get_video_client() -> Vonage:
    application_id = _require_env("VONAGE_APPLICATION_ID")
    private_key_raw = _require_env("VONAGE_PRIVATE_KEY")
    private_key = _read_private_key(private_key_raw)
    return _create_vonage_client(application_id, private_key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting up...")
    yield
    # Cleanup Audio Connectors on shutdown (reuse vng if possible)
    for sid in list(_active_connectors.keys()):
        try:
            await _stop_audio_connector_async(sid)
        except Exception as e:
            logger.warning(f"Failed to stop connector on shutdown {sid}: {e}")
    logger.info("Server shutting down...")


app = FastAPI(lifespan=lifespan)

app.mount("/static", StaticFiles(directory="static"), name="static")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/")
async def root():
    return FileResponse("static/index.html")


@app.get("/health")
async def health():
    return {"ok": True}


@app.post("/api/anam/session-token")
async def anam_session_token() -> JSONResponse:
    """Creates an Anam session token for the browser JS SDK.
    The browser uses this to initialize the Anam avatar client."""
    anam_api_key = _require_env("ANAM_API_KEY")
    anam_avatar_id = _require_env("ANAM_AVATAR_ID")
    anam_voice_id = _require_env("ANAM_VOICE_ID")

    import aiohttp
    async with aiohttp.ClientSession() as client:
        async with client.post(
            "https://api.anam.ai/v1/auth/session-token",
            headers={"Authorization": f"Bearer {anam_api_key}"},
            json={
                "personaConfig": {
                    "avatarId": anam_avatar_id,
                    "voiceId": anam_voice_id,
                    "llmId": "CUSTOMER_CLIENT_V1",
                    "enableAudioPassthrough": False,
                },
                "sessionOptions": {
                    "enableSessionReplay": False,
                    "sessionTimeout": 3600,
                },
            },
        ) as resp:
            if resp.status != 200:
                err_text = await resp.text()
                logger.error(f"Anam token error: {resp.status} {err_text}")
                raise HTTPException(status_code=502, detail="Failed to create Anam token")
            data = await resp.json()
            return JSONResponse(content={"sessionToken": data["sessionToken"]})


@app.post("/api/vonage/session")
async def create_vonage_session(request: Request) -> JSONResponse:
    """Creates a Vonage Video session, generates client token,
    and connects the Audio Connector."""
    application_id = _require_env("VONAGE_APPLICATION_ID")
    private_key_raw = _require_env("VONAGE_PRIVATE_KEY")
    private_key = _read_private_key(private_key_raw)
    audio_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))

    ws_uri = os.getenv("WS_URI")
    if not ws_uri:
        host = request.headers.get("host", "localhost:8005")
        # Known limitation: 127.0.0.1 / ::1 will be classified as wss (should be ws for dev)
        scheme = "ws" if host.startswith("localhost") else "wss"
        ws_uri = f"{scheme}://{host}/ws"

    if not (ws_uri.startswith("ws://") or ws_uri.startswith("wss://")):
        raise HTTPException(status_code=500, detail=f"Invalid WS_URI scheme: {ws_uri}")

    vng = _create_vonage_client(application_id, private_key)
    session_id = await _create_session_async(vng)

    try:
        await _connect_audio_connector_async(vng, session_id, ws_uri, audio_rate)
    except Exception as e:
        logger.warning(f"Audio Connector failed: {e}")
        raise HTTPException(status_code=500, detail=f"Audio Connector error: {e}")

    token = _generate_client_token(vng, session_id)

    return JSONResponse({
        "session_id": session_id,
        "token": token,
        "application_id": application_id,
    })


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Vonage Audio Connector WebSocket endpoint (Pipecat pipeline)."""
    await websocket.accept()
    logger.info("Client connected to /ws")

    sample_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))
    serializer = VonageFrameSerializer(
        VonageFrameSerializer.InputParams(
            vonage_sample_rate=sample_rate,
        )
    )

    transport = FastAPIWebsocketTransport(
        websocket=websocket,
        params=FastAPIWebsocketParams(
            audio_in_enabled=True,
            audio_out_enabled=True,
            audio_out_10ms_chunks=2,
            serializer=serializer,
        ),
    )

    async def keepalive():
        while True:
            try:
                await websocket.send_text('{"event":"keepalive"}')
                await asyncio.sleep(10)
            except Exception:
                break

    keepalive_task = asyncio.create_task(keepalive())

    try:
        runner_args = WebSocketRunnerArguments(websocket=websocket, body={})
        await bot(runner_args, transport)
    except Exception as e:
        logger.exception(f"Pipecat bot error: {e}")
    finally:
        keepalive_task.cancel()
        await transport.cleanup()
        logger.info("WebSocket endpoint cleaned up")


@app.websocket("/ws-anam")
async def websocket_anam(websocket: WebSocket):
    """WebSocket that sends LLM text output to the browser.
    The browser feeds this text to the Anam JS SDK for TTS + avatar."""
    await websocket.accept()
    logger.info("Browser connected to /ws-anam")

    from bot import get_text_bridge
    bridge = get_text_bridge()
    bridge.add_client(websocket)

    # Send initial greeting
    try:
        await websocket.send_json({"type": "llm_text", "text": "こんにちは。私はAIアバターアシスタントです。何かお手伝いできますか？"})
        await websocket.send_json({"type": "llm_end"})
    except Exception as e:
        logger.warning(f"Failed to send greeting: {e}")

    try:
        while True:
            msg = await websocket.receive_text()
            if msg == "ping":
                await websocket.send_text("pong")
    except Exception:
        pass
    finally:
        bridge.remove_client(websocket)
        logger.info("Browser disconnected from /ws-anam")


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8005)
