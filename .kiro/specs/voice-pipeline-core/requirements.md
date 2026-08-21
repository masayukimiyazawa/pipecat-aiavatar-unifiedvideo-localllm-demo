# Requirements Document

## Introduction

Voice Pipeline Core is the core of voice interaction via Pipecat. `run_bot` at `bot.py:112` integrates `SileroVADAnalyzer` (`bot.py:8`), `WhisperSTTServiceMLX` (`bot.py:132` MLX `LARGE_V3_TURBO_Q4` Japanese), `OpenAILLMService` (`bot.py:118` LM Studio), `LLMContext`/`LLMContextAggregatorPair` (`bot.py:140`) and `Pipeline`/`PipelineWorker`/`WorkerRunner` (`bot.py:160`/`bot.py:172`) as a 7-stage pipeline. The `LLMAssistantAggregator` monkey-patch at `bot.py:34` forwards LLM text downstream to `text-bridge-avatar`. The goal is to convert user utterances into 2-3 sentence natural Japanese responses.

## Boundary Context (Optional)
- **In scope**: Creation, connection, and parameters for VAD/STT/LLM/Context Aggregator/Pipeline/Worker/Runner, monkey-patch, fixed sample rate 16000, `handle_sigint` control, client connection events
- **Out of scope**: Vonage audio relay itself (`/ws` Transport in `audio-connector-bridge`), text fan-out (`text-bridge-avatar` Bridge), Vonage/Anam token issuance, frontend rendering
- **Adjacent expectations**: `audio-connector-bridge` injects `transport` and `sample_rate`, `text-bridge-avatar` injects the `text_bridge` singleton, `session-provisioning` supplies `LM_STUDIO_BASE_URL`/`LM_MODEL`/`STT_LANGUAGE`

## Requirements

### Requirement 1: Speech Recognition (STT)

**Objective:** As a user, I want Japanese utterances accurately transcribed to text, so that the LLM can understand intent

#### Acceptance Criteria
1. When `run_bot` is called, the Voice Pipeline Core shall create `WhisperSTTServiceMLX(Settings(model=MLXModel.LARGE_V3_TURBO_Q4, language=Language(STT_LANGUAGE), no_speech_prob=0.3))` (`bot.py:132`)
2. When `STT_LANGUAGE` is unset, the Voice Pipeline Core shall default to `ja` (`bot.py:51`)
3. If the audio contains silent segments, then the Voice Pipeline Core shall discard silence with `no_speech_prob=0.3` — frames with `no_speech_prob` above 0.3 are treated as non-speech (implicit threshold now explicit)
4. The Voice Pipeline Core shall fix the STT model to `LARGE_V3_TURBO_Q4` and not switch via env — `LARGE_V3_TURBO_Q4` is chosen for Apple Silicon memory/performance balance (24GB+ recommended); `LARGE_V3` would OOM on 16GB (rationale now explicit)
5. If audio sample rate is not 16000, then the Voice Pipeline Core shall rely on `VonageFrameSerializer` resampling; direct STT input at 8000/48000 without serializer is not supported (edge case now explicit)

### Requirement 2: Voice Activity Detection (VAD)

**Objective:** As a system, I want speech segments accurately detected to control timing of LLM submission, so that interruptions and silent submissions are prevented

#### Acceptance Criteria
1. When `LLMContextAggregatorPair` is created, the Voice Pipeline Core shall set `SileroVADAnalyzer(VADParams(confidence=0.7, start_secs=0.3, stop_secs=0.8, min_volume=0.4))` to `user_params.vad_analyzer` (`bot.py:145`)
2. When VAD detects speech start, the Voice Pipeline Core shall aggregate the user turn based on `LLMUserAggregatorParams(audio_idle_timeout=2.0, user_turn_stop_timeout=5.0)` (`bot.py:153`) — `audio_idle_timeout` is silence before aggregator flushes, `user_turn_stop_timeout` is max turn length
3. While the user is speaking, the Voice Pipeline Core shall delay LLM submission until `stop_secs=0.8` elapses and ignore low volume below `min_volume=0.4` — prevents mid-sentence cutoff for Japanese particles (implicit rule now explicit)
4. If noise below `confidence` 0.7 is detected, then the Voice Pipeline Core shall not treat it as speech and shall not pass to STT — tuned for Japanese speech to reduce false triggers from background noise

### Requirement 3: LLM Dialogue Generation

**Objective:** As a user, I want a natural Japanese response of 2-3 sentences returned, so that conversation with the avatar does not stall

#### Acceptance Criteria
1. When `run_bot` creates the LLM, the Voice Pipeline Core shall use `OpenAILLMService(base_url=LM_STUDIO_BASE_URL, api_key="not-needed", Settings(model=LM_MODEL, system_instruction="You are a helpful voice assistant speaking Japanese. Respond in natural conversational Japanese. Keep responses to 2-3 sentences. Avoid markdown, symbols, or English words."))` (`bot.py:118`)
2. When `LM_STUDIO_BASE_URL` is unset, the Voice Pipeline Core shall default to `http://localhost:1234/v1` (`bot.py:49`)
3. When the LLM generates a response, the Voice Pipeline Core shall stream in `TextFrame` units and emit `LLMFullResponseEndFrame` on completion — each `TextFrame.text` is a partial chunk, not a full sentence
4. If `LM_MODEL` is empty string at `bot.py:50`, then the Voice Pipeline Core shall delegate to LM Studio's default loaded model — empty string is passed as-is to `OpenAILLMService`; if LM Studio has no default, it will 404 (edge case now explicit)
5. If LM Studio is unreachable, then the Voice Pipeline Core shall surface the exception to `bot()` caller; no retry or fallback model is attempted (negative legacy: should add retry/backoff)

### Requirement 4: Context Aggregation and Conversation History

**Objective:** As a system, I want to maintain conversation history while separating user/assistant turns, so that context-aware responses are possible

#### Acceptance Criteria
1. When `run_bot` is initialized, the Voice Pipeline Core shall create `LLMContext()` and start with empty history via `context._messages.clear()` at `bot.py:141` — note: `_messages` is a private API (legacy flagged); should use `context.set_messages([])` if available
2. When the pipeline is running, the Voice Pipeline Core shall create `user_aggregator` and `assistant_aggregator` via `LLMContextAggregatorPair(context, user_params)`
3. When a user utterance is finalized by STT, the Voice Pipeline Core shall have `user_aggregator` add the user message to `LLMContext`
4. When an LLM response completes, the Voice Pipeline Core shall have `assistant_aggregator` add the assistant message to `LLMContext`
5. The Voice Pipeline Core shall note that `LLMContext` is in-memory per `run_bot` invocation (per `/ws` connection) and is lost on `worker.cancel` — no persistence across reconnects (implicit rule now explicit)

### Requirement 5: Pipeline Assembly and Execution

**Objective:** As a developer, I want the 7-element pipeline stably executed with metrics enabled, so that audio input flows consistently to text output

#### Acceptance Criteria
1. When assembling the pipeline, the Voice Pipeline Core shall strictly follow `Pipeline([transport.input(), stt, user_aggregator, llm, assistant_aggregator, text_forwarder, transport.output()])` order (`bot.py:160`) — `text_forwarder` must be after `assistant_aggregator` to capture downstream-forced frames
2. When creating the Worker, the Voice Pipeline Core shall use `PipelineWorker(pipeline, PipelineParams(audio_in_sample_rate=sample_rate, audio_out_sample_rate=16000, enable_metrics=True, enable_usage_metrics=True))` (`bot.py:172`) — metrics are always enabled for future `ops-deployment` monitoring
3. When `transport` fires `on_client_connected`, the Voice Pipeline Core shall log `Client connected` (`bot.py:184`)
4. When `transport` fires `on_client_disconnected`, the Voice Pipeline Core shall log `Client disconnected` then execute `await worker.cancel()` (`bot.py:188`) — this cancels the pipeline even if `handle_sigint` is False (edge case now explicit)
5. When a Runner is needed, the Voice Pipeline Core shall create `WorkerRunner(handle_sigint)` and execute `add_workers(worker)` → `run()` (`bot.py:191`) — `handle_sigint` is passed from `WebSocketRunnerArguments` at `server.py:261`

### Requirement 6: LLM Text Downstream Forwarding Monkey-patch

**Objective:** As a system, I want LLM streaming text to reach downstream `LLMTextForwarder`, so that text can be delivered to the avatar side

#### Acceptance Criteria
1. When the module is loaded, the Voice Pipeline Core shall save `_original_handle_text` at `bot.py:35` and replace `LLMAssistantAggregator._handle_text` with `_forwarding_handle_text` that executes `await self.push_frame(frame, DOWNSTREAM)` after `await _original_handle_text(self, frame)` at `bot.py:36`
2. When `LLMFullResponseEndFrame` is processed, the Voice Pipeline Core shall similarly add `push_frame(DOWNSTREAM)` via `_forwarding_handle_llm_end` (`bot.py:41`)
3. The Voice Pipeline Core shall note that this monkey-patch relies on private methods `_handle_text`/`_handle_llm_end` — it will break on pipecat-ai minor version bump and shall be replaced with a proper `FrameProcessor` or upstream fix that enables downstream forwarding natively (negative legacy flagged)
4. If a future Pipecat version forwards downstream by default, then the Voice Pipeline Core shall remove the monkey-patch and rely on native behavior

### Requirement 7: Error Handling, Non-Functional, and Constraints

**Objective:** As an operator, I want the pipeline to stop and restart safely even under exceptions and resource constraints, so that long demos remain stable

#### Acceptance Criteria
1. If any of STT/LLM/VAD throws, then the Voice Pipeline Core shall propagate the exception to `PipelineWorker` and have `WorkerRunner` terminate the keepalive loop via `transport.cleanup()` on the `/ws` side — no per-component retry is attempted
2. When `sample_rate` cannot be obtained via `int(os.getenv("VONAGE_AUDIO_RATE","16000"))` at `bot.py:200`, the Voice Pipeline Core shall treat as 500 and not start the pipeline — note: this re-reads env independently from `server.py:233`; should be injected to avoid divergence (legacy flagged)
3. The Voice Pipeline Core shall fix `AUDIO_OUT_SAMPLE_RATE` to constant `16000` (`bot.py:47`) to match the Vonage side rate — duplication with `VONAGE_AUDIO_RATE` env is intentional but shall be unified to single source
4. If LM Studio returns an error (e.g., model not loaded), then the Voice Pipeline Core shall delegate retries to Pipecat defaults and log only `base_url` without `api_key`
5. The Voice Pipeline Core shall keep `enable_metrics` and `enable_usage_metrics` always `True` so future monitoring expansion in `ops-deployment` is not blocked
6. The Voice Pipeline Core shall note that `load_dotenv(override=True)` at `bot.py:32` duplicates `server.py:25` — env should be loaded once at process start, not per module (legacy flagged)
