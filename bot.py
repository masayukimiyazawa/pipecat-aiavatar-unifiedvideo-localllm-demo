import asyncio
import os

from dotenv import load_dotenv
from fastapi import WebSocket
from loguru import logger

from pipecat.audio.vad.silero import SileroVADAnalyzer
from pipecat.audio.vad.vad_analyzer import VADParams
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.worker import PipelineParams, PipelineWorker
from pipecat.frames.frames import LLMFullResponseEndFrame, TextFrame
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.processors.aggregators.llm_response_universal import (
    LLMAssistantAggregator,
    LLMContextAggregatorPair,
    LLMUserAggregatorParams,
)
from pipecat.runner.types import WebSocketRunnerArguments
from pipecat.services.openai.llm import OpenAILLMService
from pipecat.services.whisper.stt import WhisperSTTServiceMLX, MLXModel
from pipecat.transcriptions.language import Language
from pipecat.serializers.vonage import VonageFrameSerializer
from pipecat.transports.base_transport import BaseTransport
from pipecat.transports.websocket.fastapi import (
    FastAPIWebsocketParams,
    FastAPIWebsocketTransport,
)
from pipecat.workers.runner import WorkerRunner

load_dotenv(override=True)

# Monkey-patch LLMAssistantAggregator to forward frames downstream to TTS.
_original_handle_text = LLMAssistantAggregator._handle_text
async def _forwarding_handle_text(self, frame: TextFrame):
    await _original_handle_text(self, frame)
    await self.push_frame(frame, FrameDirection.DOWNSTREAM)
LLMAssistantAggregator._handle_text = _forwarding_handle_text

_original_handle_llm_end = LLMAssistantAggregator._handle_llm_end
async def _forwarding_handle_llm_end(self, frame):
    await _original_handle_llm_end(self, frame)
    await self.push_frame(frame, FrameDirection.DOWNSTREAM)
LLMAssistantAggregator._handle_llm_end = _forwarding_handle_llm_end

AUDIO_OUT_SAMPLE_RATE: int = 16000

LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_BASE_URL", "http://localhost:1234/v1")
LM_MODEL = os.getenv("LM_MODEL", "")
STT_LANGUAGE = os.getenv("STT_LANGUAGE", "ja")


class LLMTextBridgeProcessor:
    """Forwards LLM text responses to connected browser clients via WebSocket.

    The browser uses this text to drive the Anam.ai JS SDK (TTS + avatar).
    """
    def __init__(self):
        self._clients: set[WebSocket] = set()

    def add_client(self, ws: WebSocket):
        self._clients.add(ws)

    def remove_client(self, ws: WebSocket):
        self._clients.discard(ws)

    async def broadcast_text(self, text: str):
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send_json({"type": "llm_text", "text": text})
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self._clients.discard(ws)

    async def broadcast_end(self):
        disconnected = set()
        for ws in self._clients:
            try:
                await ws.send_json({"type": "llm_end"})
            except Exception:
                disconnected.add(ws)
        for ws in disconnected:
            self._clients.discard(ws)


_text_bridge = LLMTextBridgeProcessor()


def get_text_bridge() -> LLMTextBridgeProcessor:
    return _text_bridge


class LLMTextForwarder(FrameProcessor):
    """Pipecat frame processor that intercepts TextFrame and sends to bridge."""

    def __init__(self, bridge: LLMTextBridgeProcessor, **kwargs):
        super().__init__(**kwargs)
        self._bridge = bridge

    async def process_frame(self, frame, direction):
        await super().process_frame(frame, direction)
        if isinstance(frame, TextFrame):
            await self._bridge.broadcast_text(frame.text)
        if isinstance(frame, LLMFullResponseEndFrame):
            await self._bridge.broadcast_end()
        await self.push_frame(frame, direction)


async def run_bot(
    transport: BaseTransport,
    handle_sigint: bool,
    sample_rate: int,
    text_bridge: LLMTextBridgeProcessor,
):
    llm = OpenAILLMService(
        base_url=LM_STUDIO_BASE_URL,
        api_key="not-needed",
        settings=OpenAILLMService.Settings(
            model=LM_MODEL,
            system_instruction=(
                "You are a helpful voice assistant speaking Japanese. "
                "Respond in natural conversational Japanese. "
                "Keep responses to 2-3 sentences. "
                "Avoid markdown, symbols, or English words."
            ),
        ),
    )

    stt = WhisperSTTServiceMLX(
        settings=WhisperSTTServiceMLX.Settings(
            model=MLXModel.LARGE_V3_TURBO_Q4,
            language=Language(STT_LANGUAGE),
            no_speech_prob=0.3,
        ),
    )

    context = LLMContext()
    context._messages.clear()
    user_aggregator, assistant_aggregator = LLMContextAggregatorPair(
        context,
        user_params=LLMUserAggregatorParams(
            vad_analyzer=SileroVADAnalyzer(
                params=VADParams(
                    confidence=0.7,
                    start_secs=0.3,
                    stop_secs=0.8,
                    min_volume=0.4,
                ),
            ),
            audio_idle_timeout=2.0,
            user_turn_stop_timeout=5.0,
        ),
    )

    text_forwarder = LLMTextForwarder(text_bridge)

    pipeline = Pipeline(
        [
            transport.input(),
            stt,
            user_aggregator,
            llm,
            assistant_aggregator,
            text_forwarder,
            transport.output(),
        ]
    )

    worker = PipelineWorker(
        pipeline,
        params=PipelineParams(
            audio_in_sample_rate=sample_rate,
            audio_out_sample_rate=AUDIO_OUT_SAMPLE_RATE,
            enable_metrics=True,
            enable_usage_metrics=True,
        ),
    )

    @transport.event_handler("on_client_connected")
    async def on_client_connected(_transport, _client):
        logger.info("Client connected")

    @transport.event_handler("on_client_disconnected")
    async def on_client_disconnected(_transport, _client):
        logger.info("Client disconnected")
        await worker.cancel()

    runner = WorkerRunner(handle_sigint=handle_sigint)
    await runner.add_workers(worker)
    await runner.run()


async def bot(
    runner_args: WebSocketRunnerArguments,
    transport: FastAPIWebsocketTransport,
):
    sample_rate = int(os.getenv("VONAGE_AUDIO_RATE", "16000"))
    logger.info(f"Starting bot with sample rate: {sample_rate}")
    await run_bot(transport, runner_args.handle_sigint, sample_rate, _text_bridge)
