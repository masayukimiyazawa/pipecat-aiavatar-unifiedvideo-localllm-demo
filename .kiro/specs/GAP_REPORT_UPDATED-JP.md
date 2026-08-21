# 統合ギャップ分析レポート — Spec と既存コードの比較（更新版）

**日付:** 2026-08-21（更新）  
**スコープ:** `.kiro/specs/{frontend-shell,session-provisioning,audio-connector-bridge,voice-pipeline-core,text-bridge-avatar,vonage-media-frontend,connection-lifecycle,ops-deployment}/{requirements.md,design.md,tasks.md,spec.json}` vs `server.py:1-313, bot.py:1-212, static/index.html:1-59, static/script.js:1-326, start.sh:1-73, Dockerfile:1-17, docker-compose.yml:1-13, pyproject.toml:1-14, tests/`  
**モード:** 既存コードは 100% `server.py/bot.py/static` に存在 — `src/features/[feature]/` ディレクトリは存在しない（design はこれら4ファイルに正しくマッピング）。フェーズは全 Spec で `tasks-generated`。最初のタスク `frontend-shell 1.1,1.2 [x]`、`session-provisioning 1.1[x],1.2[x],1.3[x]`（今サイクルで修正）、`audio-connector-bridge 1.1[x],1.2[x]`（一部回帰あり）、`voice-pipeline-core 1.1[x],1.2[x]`、`text-bridge-avatar 1.1[x],1.2[x]` はすでに完了 — 本レポートは**残りの**タスクを対象とする。

---

## エグゼクティブサマリー（更新）

8つの Spec は引き続き動作するデモコードの事後文書化である。今サイクルの修正（**5件のコード変更**: `static/index.html:30` の不要ルール削除、`server.py:9-12` での `load_dotenv` 一元化 + `server.py:164` の `Request` 削除、`server.py:103,79,132` での `Optional[Vonage]` 再利用 + `lifespan` クリーンアップ、`bot.py:8` の `HasSendJson` Protocol + `140` の `set_messages` ガード、`static/script.js:18,187,224,287` の `wsAnamPingId` + `isConnected` を `onopen` 内へ移動）により、**37件中12件のギャップが解消**。依然として重大な残課題: **(A) テストハーネス不足** は `TestClient`/`playwright` タスクを依然ブロック（`tests/conftest.py:3` + 9件のテストで部分的に解消したが `vonage-media`/`text-bridge` はモックが必要）；**(B) 3 Spec が同一ファイルを編集するホットスポット**（`server.py:71-99,132,233,277` と `static/script.js:29-224,282-316`）は依然3つの PR に分岐；**(C) 再現可能なビルド**（`Dockerfile:10-11` が `uv.lock` を無視）と **広範な `pkill` / `lsof` フォールバック / `trap` 不備**（`start.sh`）は未解決。**(D) Lock の回帰:** `_connector_lock` を追加した後に消失（`audio-connector-bridge` D6 参照）。再利用は依然良好 — 残りタスクの70%はドキュメント/テストであり、機能欠落ではない。

---

## 1. 依存関係 / 前提条件のギャップ（更新）

| # | Spec / タスク | 不足している前提条件 | 現在のコードの根拠 | 提案 |
|---|-------------|----------------------|-----------------------|----------|
| D1 | **すべて** まだ | `playwright` が未導入；`pytest`/`beautifulsoup4`/`httpx` は `uv add --dev` により追加済み（`pyproject.toml` は現在 `pytest 9.1.1`、`beautifulsoup4 4.15` を持つ）、`tests/` は `conftest.py:3` + `test_frontend_shell.py:5` + `test_session_provisioning.py:4` + `test_ops_deployment.py:3`（9件のテスト）で存在 | `tests/` は現在存在（以前はなし）、`pyproject.toml:6` は dev 依存を持つが `vonage-media`/`text-bridge` のタスクは依然 `playwright` を必要とする | `pytest`/`bs4` についてはタスク 0 を完了扱いに維持；`frontend-shell 3.2,5.1` と `vonage-media *5` 向けにフォローアップ `uv add --dev playwright && playwright install` を追加 |
| D2 | `frontend-shell` 3.1,4.1,5.1 | `static/style.css` のドラフトが存在しない；`playwright` 未インストール | `bash ls static/style.css` → 存在せず；`static/index.html:30` は現在コメント（`2.1` で修正済み） | タスク `4.1` で `static/style.css` を `sed -n '9,31p' index.html` によるドラフトとして作成；inline を `design.md:84` 通り一次情報として保持 |
| D3 | `session-provisioning` P1-3 | `private.key` パスの曖昧さ `CWD` vs `/app` | `server.py:37-42` は現在 `try FileNotFound → HTTPException`（`1.1` で修正）だが `Path(__file__).parent` の注記なし | `design.md:242` に追記: 相対パスなら `Path(value)` は `__file__.parent / value` として解決される |
| D4 | `session-provisioning` P1-4 | `WS_URI` のホストヘッダー信頼（`server.py:206` `testserver`→`wss`） | `server.py:208-209` は現在 `ws://`/`wss://` なら else 500 で検証（`1.2` で修正）だが `_derive_ws_uri` が未抽出 | `server.py:203` に純粋関数 `def _derive_ws_uri(host, env_ws_uri)` を抽出して単体テスト可能に；コメント `127.0.0.1→wss` の制限を保持 |
| D5 | `session-provisioning` P1-1 | `aiohttp` が依然ハンドラ内 `server.py:171` `import aiohttp` | `pyproject.toml` は依然 `aiohttp` を省略（推移的 `pipecat-ai→aiohttp 3.14.3` に依存）、`Dockerfile:11` は依然 `uv pip install -r pyproject.toml` | `import aiohttp` を `server.py:7` 先頭にホイスト；`design.md:84` に `aiohttp>=3.14.3` または `httpx` への切り替えを追記 |
| D6 | `audio-connector-bridge` 1.1 | **回帰:** `tasks.md:4 [x]1.1` は `_connector_lock` を追加したと主張するが `server.py:72` は再び単なる `dict` で lock なし（`grep _connector_lock` → 0件ヒット） | `server.py:72` `dict`、`78` `for old_sid in list(...): await _stop(old_sid, vng)` で `async with lock` なし | `72` に `_connector_lock = asyncio.Lock()` を再追加し、`78-99` ブロックを `async with _connector_lock` でラップ（`_stop` の lock ネストなし） |
| D7 | `audio-connector-bridge` 1.2 再利用 | `server.py:103` は現在 `Optional[Vonage]=None` + `if vng is None: _get_video_client()` かつ `79` で `vng` を渡す、`132` `lifespan` は `await _stop(sid)` をループ — `79` については再利用が修正されたが、`lifespan` の `138` は `vng` なしで呼び出し → SID ごとに env を再読み込み | `server.py:138` のフォールバックは依然 `Optional` | `lifespan` でループ前に単一の `vng = _get_video_client()` を作成し `await _stop(sid, vng)` とする |
| D8 | `audio-connector-bridge` レート二重管理 | `server.py:212` vs `242` vs `bot.py:212` は依然 `int(os.getenv("VONAGE_AUDIO_RATE"))` を重複 vs `47` `AUDIO_OUT_SAMPLE_RATE=16000` | `bot.py:38` に TODO コメントは追加されたが `server.py:242` は依然 env を読み込み + `bot.py:212` のフォールバックも読み込み | `voice-pipeline-core 1.1` の注入（`server.py:277` は現在 `await bot(..., sample_rate)` で修正済み）を保持しつつ、`242` の `accept()` 前に `ValueError` ガードを `2.1` に追加 |
| D9 | `voice-pipeline-core` LM Studio | `LM_STUDIO_BASE_URL:49` は `run_bot:112` の前に到達可能である必要 | ヘルスチェックなし | タスク 0 `Depends: session-provisioning` または `tests/test_voice_pipeline_core.py` で `OpenAILLMService` をモック |
| D10 | `voice-pipeline-core` シングルトン | `run_bot:112-116` `text_bridge` は `text-bridge-avatar` 経由 `get_text_bridge:92` | `tasks.md:40` は存在を前提とするが `server.py:278-280` の遅延 import は `design` に記載なし | `tasks.md:40` に `Depends: text-bridge-avatar` を追加 |
| D11 | `voice-pipeline-core` Apple Silicon | `MLXModel.LARGE_V3_TURBO_Q4:134` は OOM | `pyproject.toml:7` | `mlx` が利用不可の場合にモックする旨を注記 |
| D12 | `vonage-media-frontend`  | `1.1[x]` は完了だが `2.1-2.3` は依然 `OT` グローバルのガードなし | `index.html:7` は `script.js:8` より前だが `script.js:97` に `if(!window.OT)` なし | タスク `2.1` で `97` の前に `assert window.OT` を追加 |

## 2. 衝突 / 既存 Spec 間の競合（更新）

| # | 衝突内容 | 修正後の現在の状態 | 影響 | 提案 |
|---|-----------|---------------------------|--------|----------|
| C1 | **3つの Spec が `server.py:71-99,132,233,277` を編集** | `1.2` の再利用 + `lifespan` は `audio-connector-bridge` により追加、`1.3` の `Request` 削除は `session-provisioning:164` により、`1.x` の注入は `voice-pipeline-core:196` により — すべて同じファイルだがコメント（`TODO prod`、`Optional`）付き — 依然ホットスポット | 並列 PR でマージ競合 | `audio-connector-bridge:1.2` を `132` lifespan のオーナーとし、他は参照とする；`design.md` に所有マトリクスを追記 |
| C2 | **`static/script.js:29-224,282-316` を3つの Spec が編集** | `connection-lifecycle:1.1` は現在 `18,187,224,287` の `wsAnamPingId` + `isConnected` を `onopen` 内に（修正済み）、`text-bridge-avatar:1.2` は `HasSendJson`（bot 側、衝突なし）、`vonage-media-frontend:1.1[x]` は完了 | `setInterval` リークの重複は `connection-lifecycle` で修正済み（以前は `text-bridge-avatar` 5.1） — 所有権が明確化 | `text-bridge-avatar 5.1` を `clearInterval` の検証のみに、`connection-lifecycle 1.1/4.1` を実装者として保持 |
| C3 | `bot.py:54-110` を共有 | `text-bridge-avatar:1.2` は `bot.py:8,67` を `HasSendJson` Protocol に変更、`voice-pipeline-core:1.2` は `140` を `set_messages` ガードに変更 — 同一ファイルの同一領域 `54-110` だが行が異なり重ならない | 低い競合だが同一 PR | `design.md:32` の分割を明確化: `voice-pipeline-core` は `LLMTextForwarder:96` の挿入 `Pipeline:172` を所有、`text-bridge-avatar` は `LLMTextBridgeProcessor:54` の定義を所有 |
| C4 | `111-118` の生 `raw _http_client.delete` | 依然 `vng._http_client.delete(video_host, f"/v2/.../connect")` で SDK をバイパス、`requirements.md:1.5` で指摘 | SDK 更新で破損 | `server.py:111` に `if hasattr(vng.video,"stop_audio_connector")` ならそちら、なければ raw（タスク `1.3`）を追加 |
| C5 | `148` の `CORSMiddleware` `allow_origins=["*"] allow_credentials=True` | 依然 `server.py:148-154` で無効、`connection-lifecycle` 5.2 のみで指摘、保留中 | ブラウザが拒否 | デモ用として保持しつつコメント `TODO prod: 明示的な origins` を追加（タスク `connection-lifecycle 5.2`） |
| C6 | `158` の `hiddenDiv display:none` vs off-screen | `vonage-media-frontend:2.3` は依然 `hiddenDiv.style.display='none'`（バグとして指摘）、`tasks.md:28` は保持 + TODO と言う（`frontend-shell` は既に `index.html:30` をコメントに修正） | スロットリングリスクは文書化された負債として残存、まだ `position:fixed;left:-9999px` に修正されていない | `2.3a` を TODO（今回 PR） + `2.3b` をフォローアップとして `requirements.md:5.2` 通りに保持 |
| C7 | `50` の `subscriberContainer display:none` | `frontend-shell:2.1-2.2` は現在 `index.html:30` をコメントに修正、親 `50` は `display:none` のまま — `audioOnly:true` として正しい | 衝突なし | `frontend-shell:2.1` のコメントが `vonage-media-frontend 3.3` を参照する形で調整 |

## 3. 粒度 / 実現可能性（残りのタスク）

| # | Spec / タスク | 粒度の問題 | 実現可能性の修正 |
|---|-------------|-------------------|-----------------|
| G1 | `frontend-shell` 3.1 `(P)` + 完了した 2.1 と同一ファイル `index.html:19,30` | 並列 `(P)` は以前無効だったが `2.1/2.2` は現在 `[x]` 完了、`3.1` は `19` を編集し `30` ではない — 現在は `4.1`（ドラフト）と並列化可能だが `3.1` + `4.1` は両方 `style.css` ドラフト vs コメント | `3.1` は `2.1` の後に直列として保持（すでに完了）、`4.1` を `3.2` と並列に |
| G2 | `frontend-shell` 4.1 `static/style.css` ドラフト | 依然 `sed` による diff は CSS パーサーなしでは検証不可 | 観測可能条件を `bash sed -n '9,31p' index.html > style.css && diff -q` に変更 |
| G3 | `frontend-shell` 5.1 `ControlPanel` 10件のログ | 依然 `page.evaluate(()=>log())` が必要だが `TestClient` は `esm.sh` の ESM を実行不可 | `5.1a` を静的 DOM（JSなし） `beautifulsoup` と `5.1b` を Playwright E2E（`playwright` が必要）に分割 |
| G4 | `session-provisioning` 2.1 `aiohttp` モック | `import aiohttp` は依然ハンドラ内 `171` で `respx` のパッチを複雑化 | `import aiohttp` を `server.py:1` にホイストし、`2.1a` 成功、`2.1b` 401、`2.1c` KeyError ガード `191` に分割 |
| G5 | `audio-connector-bridge` 1.1 回帰 | 以前 `[x]` とマークされたがコードから lock が消失 → 誤った完了 | `tasks.md:4` `1.1` を `[ ]` に戻し、`1.1a` で lock 作成、`1.1b` で `_stop` をネストせずに `78-99` をラップ |
| G6 | `audio-connector-bridge` 2.1 | `ValueError` ガード + serializer/transport を混在 | `2.1a` を transport の検証、`2.1b` を `accept` 前の `ValueError` に分割 |
| G7 | `voice-pipeline-core` 2.1/2.2 `mlx` メモリ | `LARGE_V3_TURBO_Q4` は CI で OOM | `WhisperSTTServiceMLX.Settings` のインスタンス化のみをモック |
| G8 | `text-bridge-avatar` 5.1 interval | `static/script.js:18,224,287` は現在 `wsAnamPingId` の保存 + `disconnect` での `clearInterval` が修正済み（connection-lifecycle 1.1 による）だが `onclose:207-213` では未クリア | `5.1b` で `onclose` でも `clearInterval` を追加 |
| G9 | `vonage-media-frontend` 2.3 | スタイル + track の null + `videoSource:null` vs `audioSource:false` を束ねている | `2.3a` をスタイル TODO、`2.3b` を track 抽出、`2.3c` を opts に分割 |
| G10 | `connection-lifecycle` 2.1 5つのモック | 依然 `fetch`/`OT`/`WS` を1タスクに | `2.1a` を fetch、`2.1b` を OT、`2.1c` を WS に分割 |
| G11 | `ops-deployment` 2.1 PID + trap を束ねている | `pkill` → PID ファイル vs `trap` の2つの異なる編集 | `2.1a` を PID ファイル、`2.1b` を trap に分割 |

## 4. 既存資産の再利用（更新）

| # | Spec | 修正後に正しく再利用されているもの | 依然見逃されているもの |
|---|------|----------------------------------|--------------|
| R1 | `frontend-shell` | `tests/conftest.py:3` + `TestClient(app)` が現在 `1.1,1.2,2.2,5.1` で再利用されている（以前はタスクごとに inline） | `3.1/4.1` は依然それぞれ `index.html:19,30` を個別に編集予定 — まとめるべき |
| R2 | `session-provisioning` | `server.py:30,37,44,50,59` のヘルパーを再利用するのは現在正しい；`12` の `load_dotenv` は `server.py:8-12` の単一ソース（bot の依存は削除済み） | `design.md:129-137` は依然 `EnvHelper` クラス vs 関数を発明 — 関数のままにする |
| R3 | `audio-connector-bridge` | `server.py:9` の `VonageFrameSerializer:242` + `FastAPIWebsocketTransport:249` を再利用；`_stop` の `vng` 再利用は `103` で現在正しい | `bot.py:29` の重複した `VonageFrameSerializer` import は未使用 — 提案通り削除すべき |
| R4 | `voice-pipeline-core` | `bot.py:8` の `HasSendJson` Protocol + `140` の `set_messages` ガードは現在 public API を再利用 | `bot.py:249` の `VonageFrameSerializer` import は依然 `bot.py` で未使用（`server.py` のみ） |
| R5 | `text-bridge-avatar` | `bot.py:67` の `LLMTextBridgeProcessor:67` `set[HasSendJson]` は現在 `fastapi.WebSocket` から分離 | `server.py:297` の `HasSendJson` は実行時依然 `WebSocket` — `MockWS` テストで構造的互換性を検証済み |
| R6 | `vonage-media-frontend` | `131` の `createAndPublish:131` ヘルパーは user `145` + avatar `160` で再利用 | 依然 `connect()` 内のクロージャ（`5.5` で指摘）；`export function createAndPublish(session, container, opts)` としてホイスティングすべき |
| R7 | `ops-deployment` | `server.py:158` の `GET /health:158` は `start.sh:53` + 将来の `HEALTHCHECK` で再利用 | ポーリングループ `seq 1 30` は依然 `start.sh:19-26` vs `52-63` で重複 — `wait_for_*()` に抽出 |

---

## Spec 間のクリティカルパス（更新）

**Wave 1 完了:** `frontend-shell 1.1,1.2,2.1,2.2 [x]`、`session-provisioning 1.1[x],1.2[x],1.3[x]`、`ops-deployment 1.1[x]`（`tests/` ハーネス経由）  
**Wave 2 残り:** `audio-connector-bridge 1.1` **回帰** → lock を修正、その後 `1.2` の再利用/`lifespan` はすでに `[x]` だが lock が必要、`1.3` の raw DELETE、`2.1-3.1` → `voice-pipeline-core 2.1,2.2,3.1` → `text-bridge-avatar 2.1,5.1`（`onclose` での interval 分割） → `vonage-media-frontend 2.1-2.3` → `connection-lifecycle 1.2`（Step1 の degrade） + `5.2` の CORS コメント

**共有リスク:** `static/script.js:29-224,282-316` および `server.py:72,103,132,233,277` は依然3つの Spec のホットスポット — ファイルごとに単一 PR または所有マトリクスを引き続き推奨。

---

## 具体的な修正チェックリスト（更新、まだファイル書き込みなし）

**`frontend-shell/tasks.md`:** `1.1,1.2,2.1,2.2` は現在 `[x]`；`3.1` は `index.html:19` にコメント `/* Vonage OT injects ... !important required */` を追加し `wc -l 59` を維持；`3.2` の観測可能条件を `BeautifulSoup` の `has attr playsinline` に変更；`4.1` は `sed` による diff で `static/style.css` を作成；`5.1` は `5.1a` DOM のみ + `5.1b` Playwright に分割；`6` は `*` の任意として保持。

**`session-provisioning/tasks.md`:** `import aiohttp` を先頭にホイスト；`242` に `Path(__file__).parent` の注記を追加；`OSError` ガードはすでに `37-42` で完了。

**`audio-connector-bridge/tasks.md`:** `1.1` を `[ ]` に戻す（回帰）、`1.2` は `[x]` を保持するが `vng` の再利用は検証済み、`1.3` は `hasattr` プローブ付きで raw フォールバックを保持；`2.1` は `accept` 前の `ValueError` に分割；`2.2` は `ws://` 警告を追加。

**`voice-pipeline-core/tasks.md`:** `1.2` は現在 `[x]`（ガード完了）；`2.1,2.2,3.1` はモックを使った検証テストを保持；`tests/test_voice_pipeline_core.py` で順序 `Pipeline[1]==stt` などを追加。

**`text-bridge-avatar/tasks.md`:** `1.1[x],1.2[x]` は完了；`5.1` は `224` での代入 vs `287` での `clear` + `207` の `onclose` に `clearInterval` を追加、に分割。

**`vonage-media-frontend/tasks.md`:** `script.js:158` の `display:none` → off-screen に TODO を追加、`createAndPublish` をモジュールスコープにホイスティング。

**`connection-lifecycle/tasks.md`:** `1.1[x]` は完了（`isConnected` は `onopen:187` 内）；`1.2` は依然 `[ ]`（Step1 の `43` の `return` を継続に degrade）；`4.1` の interval は現在 `[x]` 完了だが `5.2` の CORS は依然 `*` としてフラグ。

**`ops-deployment/tasks.md`:** `1.1[x]` は完了；`2.1` は依然広範な `pkill`；`Dockerfile:10-11` は依然 `COPY pyproject.toml` のみ。

**`design.md` 全体:** `server.py:37` に `Path` 解決、`Dockerfile:15` の後に `HEALTHCHECK --interval=10s`、`compose` から `version: "3.9"` を削除、を追加。
