# AIアバターアシスタント — Vonage Video + Anam.ai + ローカルLLM

ブラウザ上でAIアバターとリアルタイムに音声＆動画で会話できるデモアプリケーションです。

## アーキテクチャ概要

```
┌──────────────────────────────────────────────────────────────────┐
│                        ブラウザ (static/)                        │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────────┐ │
│  │ ユーザー  │    │  Anam.ai SDK  │    │  /ws-anam WebSocket   │ │
│  │ Webカメラ │    │  (アバター動画) │    │  (LLMテキスト→Anam音声)│ │
│  │ + マイク  │    └──────┬───────┘    └───────────┬────────────┘ │
│  └────┬─────┘           │                         │              │
│       ▼                 ▼                         ▼              │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │         Vonage OpenTok JS SDK (OT.initSession)           │   │
│  │   publish(ユーザーカメラ+マイク) / publish(Anam映像+音声)  │   │
│  │   subscribe(Audio Connector ストリーム)                   │   │
│  └────────────────────────┬─────────────────────────────────┘   │
└───────────────────────────┼─────────────────────────────────────┘
                            │
              ┌─────────────┴─────────────┐
              │   Cloudflare Tunnel        │
              │  (公開HTTPS/WSS URL)       │
              └─────────────┬─────────────┘
                            │
┌───────────────────────────┼─────────────────────────────────────┐
│                   サーバー (FastAPI / Uvicorn)                    │
│                                                                  │
│  ┌─────────────┐     ┌──────────────────────────────────────┐  │
│  │ Vonage Video │     │  /ws (Audio Connector)               │  │
│  │ API (REST)   │     │  ┌────────────────────────────┐     │  │
│  │              │     │  │     Pipecat パイプライン    │     │  │
│  │ • セッション  │     │  │                            │     │  │
│  │ • トークン   │     │  │  音声入力 → STT (Whisper)  │     │  │
│  │ • Audio     │─────┼──→          → LLM (LM Studio) │     │  │
│  │   Connector │     │  │          → テキスト転送     │──┼──┼──→ /ws-anam
│  └─────────────┘     │  │          → 音声出力         │     │  │
│                      │  └────────────────────────────┘     │  │
│                      └──────────────────────────────────────┘  │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │  REST API エンドポイント                                  │  │
│  │  POST /api/anam/session-token  — Anam認証トークン         │  │
│  │  POST /api/vonage/session      — セッション+コネクタ作成   │  │
│  │  GET  /health                  — ヘルスチェック            │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

## 音声 / 映像の流れ

### 音声パス
1. **ユーザー → サーバー**: ブラウザマイク → OTパブリッシャー → Vonageセッション → Audio Connector → WebSocket (`/ws`) → Pipecat STT (`mlx-whisper`)
2. **サーバー → Anamアバター**: STTテキスト → LLM (LM Studio) → LLM応答テキスト → `/ws-anam` WebSocket → Anam.ai JS SDK (TTS + リップシンク)
3. **サーバー → ユーザー (オプショナル)**: LLM応答 → Pipecat音声出力 → WebSocket → Audio Connector → Vonageセッション → ブラウザ購読

Anam.ai SDK が **TTSとアバターアニメーションの両方**を担当します。LLMのテキスト出力は別途WebSocketブリッジ (`/ws-anam`) を介してブラウザに送られ、Anam SDKが音声と顔のアニメーションとしてレンダリングします。

### 映像表示
- **左パネル**: ユーザーのWebカメラ（VonageにOTパブリッシャーとして配信、ローカル表示）
- **右パネル**: AIアバター映像（Anam.ai JS SDKがレンダリング、Anamクラウドからストリーミング）

## パイプライン構成

| 段階           | 技術                                | ファイル        |
|---------------|-------------------------------------|---------------|
| 音声認識(STT)  | `mlx-whisper` (MLX, Apple Silicon)  | `bot.py`      |
| LLM           | LM Studio (ローカル, OpenAI互換)    | `bot.py`      |
| テキスト転送   | WebSocket (`/ws-anam`)              | `server.py`   |
| VAD           | Silero VAD                          | `bot.py`      |
| アバターTTS   | Anam.ai クラウド (ブラウザJS SDK)   | `script.js`   |
| セッション管理 | Vonage Video API                    | `server.py`   |
| 音声中継      | Vonage Audio Connector              | `server.py`   |

## 前提条件

- Python 3.11+
- [LM Studio](https://lmstudio.ai/) がローカルで動作していること（OpenAI互換APIサーバー、`localhost:1234`）
- Apple Silicon Mac（MLXアクセラレーションによるWhisper STT用、必須ではない）
- Vonage Video API アカウント（アプリケーションID + 秘密鍵）
- Anam.ai アカウント（APIキー、アバターID、音声ID）
- [Cloudflared](https://developers.cloudflare.com/cloudflare-one/connections/connect-networks/downloads/) トンネルCLI

## セットアップ

1. **クローンとインストール**
   ```bash
   git clone <repo>
   cd pipecat-aiavatar-unifiedvideo-localllm-demo
   uv sync
   ```

2. **環境設定** — テンプレートをコピーして認証情報を記入:
   ```bash
   cp .env.example .env
   ```
   必要な変数:
   - `VONAGE_APPLICATION_ID` — Vonage Video API アプリケーションID
   - `VONAGE_PRIVATE_KEY` — Vonage アプリケーション秘密鍵のパス
   - `ANAM_API_KEY` — Anam.ai APIキー
   - `ANAM_AVATAR_ID` — Anam アバターID
   - `ANAM_VOICE_ID` — Anam 音声ID
   - `LM_STUDIO_BASE_URL` — デフォルト: `http://localhost:1234/v1`
   - `LM_MODEL` — LM Studio で読み込むモデル名

3. **LM Studio を起動**
   - モデルを読み込む
   - 推論サーバーをポート1234で起動

## 実行方法

### 自動起動（推奨）

```bash
bash start.sh
```

以下の処理が自動で実行されます:
1. Cloudflare トンネルを起動し、ローカルサーバーを公開URLで公開
2. Uvicorn サーバーをポート8005で起動
3. ブラウザで開くURLを表示

### 手動起動

```bash
# Cloudflare トンネルを起動
cloudflared tunnel --url http://localhost:8005 &

# サーバーを起動
uv run python server.py
```

## 接続方法

1. 表示されたURLをブラウザで開く
2. **接続** ボタンをクリック
3. カメラとマイクの許可を与える
4. AIアバターが挨拶: 「こんにちは。私はAIアバターアシスタントです。何かお手伝いできますか？」
5. 話しかける — システムが音声認識 → LLM → アバター応答を自動処理

## プロジェクト構成

```
├── server.py          # FastAPIサーバー: REST API, WebSocketエンドポイント
├── bot.py             # Pipecat パイプライン: STT → LLM → テキスト転送
├── pyproject.toml     # Python 依存関係
├── start.sh           # トンネル + サーバー起動スクリプト
├── .env               # 設定 (認証情報)
├── private.key        # Vonage アプリケーション秘密鍵
├── static/
│   ├── index.html     # シングルページUI
│   └── script.js      # フロントエンドロジック: OT, Anam SDK, WebSocketブリッジ
└── README-JP.md
```

## 技術的判断

- **Option A（採用）**: Anamの映像+音声をブラウザの `MediaStream` 経由でVonageに配信 — Experience ComposerはサーバーにGPUがないためWebGLアバターレンダリング不可のため不採用
- **`createAndPublish()` ヘルパー**: `OT.initPublisher` + `session.publish` をPromiseでラップし、ストリームの存在を確認してから処理を進める
- **テキストブリッジ**: LLMテキスト出力を別WebSocket (`/ws-anam`) でブラウザに送信し、Anam SDKでTTS処理 — LLM推論とアバターレンダリングを分離
