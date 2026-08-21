# Implementation Plan

- [x] 1. Isolate pipeline configuration and remove legacy env coupling
- [x] 1.1 Inject `sample_rate` instead of re-reading env (P)
  - Change `bot(runner_args, transport)` at `196` to accept `sample_rate: int | None` from `audio-connector-bridge` server `sample_rate` and pass through to `run_bot`; remove `int(os.getenv("VONAGE_AUDIO_RATE","16000"))` duplication at `200` and keep only one source (injected)
  - Verify `bot` still logs `Starting bot with sample rate: {rate}` and `PipelineParams(audio_in_sample_rate=rate)` matches `VonageFrameSerializer`
  - _Requirements: 7.2, 5.2_
  - _Boundary: Execution_
  - _Depends: audio-connector-bridge 2.1_
- [x] 1.2 Single `load_dotenv` and private API fix
  - Remove `load_dotenv(override=True)` from `bot.py:32` (keep only in `server.py:25` at process entry); replace `context._messages.clear()` at `141` with `context.set_messages([])` if available or guard with `hasattr` fallback and add comment
  - Observable: `grep load_dotenv bot.py` returns 0; `TestClient` still passes `_messages` cleared check
  - _Requirements: 4.1, 7.6_
  - _Boundary: ContextAggregation, Execution_

- [ ] 2. Implement STT and VAD per tuned parameters
- [ ] 2.1 Create `WhisperSTTServiceMLX` with `LARGE_V3_TURBO_Q4` and silence gate (P)
  - Ensure `WhisperSTTServiceMLX(Settings(model=LARGE_V3_TURBO_Q4, language=Language(STT_LANGUAGE or ja), no_speech_prob=0.3))` at `132`; test empty `STT_LANGUAGE` defaults to `ja` and silence `no_speech_prob>0.3` discarded
  - Verify 16000 input required; non-16000 via serializer still transcribed
  - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5_
  - _Boundary: STTService_
- [ ] 2.2 Create Silero VAD with Japanese-tuned params (P)
  - Ensure `SileroVADAnalyzer(VADParams(confidence=0.7, start_secs=0.3, stop_secs=0.8, min_volume=0.4))` at `145` and `LLMUserAggregatorParams(audio_idle_timeout=2.0, user_turn_stop_timeout=5.0)` at `153`
  - Test `stop_secs` delay prevents particle cutoff (e.g., `ね`/`よ`); `min_volume` filters low noise
  - _Requirements: 2.1, 2.2, 2.3, 2.4_
  - _Boundary: VADService_

- [ ] 3. Implement LLM and context aggregation
- [ ] 3.1 Wire `OpenAILLMService` to LM Studio
  - Ensure `OpenAILLMService(base_url=LM_STUDIO_BASE_URL or http://localhost:1234/v1, api_key="not-needed", model=LM_MODEL, system_instruction="You are a helpful...")` at `118`; handle empty `LM_MODEL` delegates to LM Studio default; unreachable → no retry, surfaced to `bot()` caller
  - Validate `LM_STUDIO_BASE_URL` unset defaults correctly and streaming emits `TextFrame` then `LLMFullResponseEndFrame`
  - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_
  - _Boundary: LLMService_
- [ ] 3.2 Provide `LLMContext` per connection
  - Ensure `LLMContext()` + cleared history at `140-141` and `LLMContextAggregatorPair(context, user_params)` at `142` creates `user_aggregator`/`assistant_aggregator`; note in-memory per `/ws` not persisted across `worker.cancel`
  - Test two concurrent `run_bot` have independent contexts
  - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5_
  - _Boundary: ContextAggregation_

- [ ] 4. Assemble and run pipeline with monkey-patch
- [ ] 4.1 Enforce 7-stage order and metrics
  - Ensure `Pipeline([transport.input(), stt, user_aggregator, llm, assistant_aggregator, text_forwarder, transport.output()])` at `160` strict order and `PipelineWorker(... PipelineParams(audio_in_sample_rate=sample_rate, audio_out_sample_rate=16000, enable_metrics=True, enable_usage_metrics=True))` at `172`
  - Observable: unit assert order and `enable_metrics` true
  - _Requirements: 5.1, 5.2, 7.5_
  - _Boundary: PipelineAssembly_
- [ ] 4.2 Preserve `on_client_connected/disconnected` handlers and `WorkerRunner`
  - Ensure `transport.event_handler("on_client_connected")` logs `Client connected` at `184` and `on_client_disconnected` logs then `await worker.cancel()` at `188-189`; `WorkerRunner(handle_sigint)` at `191` via `WebSocketRunnerArguments.handle_sigint`
  - Test disconnect → `worker.cancel` called even if `handle_sigint` false
  - _Requirements: 5.3, 5.4, 5.5_
  - _Boundary: Execution_
- [ ] 4.3 Keep monkey-patch with deprecation note
  - Keep ` _forwarding_handle_text/_llm_end` at `34-45` that `push_frame(DOWNSTREAM)` after original; add comment that if future pipecat forwards natively, remove patch
  - Verify `TextFrame` reaches `LLMTextForwarder` after patch
  - _Requirements: 6.1, 6.2, 6.3, 6.4_
  - _Boundary: MonkeyPatch_

- [ ] 5. Fix constants and error propagation
- [ ] 5.1 Unify `AUDIO_OUT_SAMPLE_RATE` and `VONAGE_AUDIO_RATE`
  - Keep `AUDIO_OUT_SAMPLE_RATE=16000` at `47` canonical; add note duplication with env is intentional but should be unified to injected `sample_rate`; ensure pipeline out rate equals Vonage serializer rate
  - Verify `grep AUDIO_OUT_SAMPLE_RATE bot.py` still 16000 and matches `PipelineParams`
  - _Requirements: 7.3, 7.4_
  - _Boundary: Execution_

- [ ]* 6. Pipeline E2E and memory check
  - Mock `transport` → `run_bot` with `Whisper` mocked 16k PCM → verify `TextFrame` streaming and `LLMFullResponseEndFrame`; check `LARGE_V3_TURBO_Q4` memory <8GB
  - _Requirements: 1.1, 3.3, 5.1_
