import { createClient } from 'https://esm.sh/@anam-ai/js-sdk@latest';
import { AnamEvent } from 'https://esm.sh/@anam-ai/js-sdk@latest/dist/module/types';

const logEl = document.getElementById('log');
const statusEl = document.getElementById('status');
const connectBtn = document.getElementById('connectBtn');
const userVideoContainer = document.getElementById('userVideoContainer');
const anamVideo = document.getElementById('anam-avatar');
const subscriberContainer = document.getElementById('subscriberContainer');

let session = null;
let anamPublisher = null;
let userPublisher = null;
let subscriber = null;
let anamClient = null;
let anamStream = null;
let wsAnam = null;
let wsAnamPingId = null;
let isConnected = false;

function log(msg) {
  const d = document.createElement('div');
  d.textContent = `[${new Date().toLocaleTimeString()}] ${msg}`;
  logEl.appendChild(d);
  logEl.scrollTop = logEl.scrollHeight;
}

function setStatus(s) { statusEl.textContent = s; }

async function connect() {
  connectBtn.disabled = true;
  setStatus('セッション作成中...');

  // --- Step 1: Get Anam session token ---
  log('Anam セッショントークンを取得中...');
  let anamToken;
  try {
    const atResp = await fetch('/api/anam/session-token', { method: 'POST' });
    if (!atResp.ok) throw new Error(`Anam token error: ${await atResp.text()}`);
    const atData = await atResp.json();
    anamToken = atData.sessionToken;
    log('Anam トークン取得成功');
  } catch (e) {
    log(`Anam トークンエラー: ${e.message}`);
    setStatus('接続失敗');
    connectBtn.disabled = false;
    return;
  }

  // --- Step 2: Create Vonage session ---
  log('Vonage セッションを作成中...');
  let vonageData;
  try {
    const vResp = await fetch('/api/vonage/session', { method: 'POST' });
    if (!vResp.ok) throw new Error(`Vonage error: ${await vResp.text()}`);
    vonageData = await vResp.json();
    log(`Vonage セッション: ${vonageData.session_id.slice(0, 8)}...`);
  } catch (e) {
    log(`Vonage エラー: ${e.message}`);
    setStatus('接続失敗');
    connectBtn.disabled = false;
    return;
  }

  // --- Step 3: Initialize Anam avatar ---
  log('Anam アバターを初期化中...');
  try {
    anamClient = createClient(anamToken, {
      disableInputAudio: true,
    });

    anamClient.addListener(AnamEvent.SESSION_READY, () => {
      log('Anam アバター準備完了');
    });

    anamClient.addListener(AnamEvent.CONNECTION_CLOSED, () => {
      log('Anam 接続切断');
    });

    // Get Anam's media stream (video + audio from Anam cloud rendering)
    const streams = await anamClient.stream();
    anamStream = streams[0];

    // Display avatar locally
    anamVideo.srcObject = anamStream;
    anamVideo.play();
    log('Anam アバター表示開始');
  } catch (e) {
    log(`Anam 初期化エラー: ${e.message}`);
    // Continue without Anam (audio-only mode)
  }

  // --- Step 4: Connect to Vonage session ---
  log('Vonage セッションに接続中...');
  const { application_id, session_id, token } = vonageData;

  try {
    session = OT.initSession(application_id, session_id);

    session.on('streamCreated', (event) => {
      try {
        if (!session || !session.connection) return;
        if (event.stream.connection.connectionId === session.connection.connectionId) return;
        if (subscriber) return;
        subscriber = session.subscribe(
          event.stream,
          subscriberContainer,
          { audioOnly: true, enableAudio: true },
          (err) => {
            if (err) log(`購読エラー: ${err.message}`);
            else log('音声購読開始');
          }
        );
      } catch (e) {
        log(`ストリーム処理エラー: ${e.message}`);
      }
    });

    session.on('streamDestroyed', () => {
      subscriber = null;
    });

    await new Promise((resolve, reject) => {
      session.connect(token, (err) => {
        if (err) reject(err);
        else resolve();
      });
    });
    log('Vonage セッション接続完了');

    // Helper: create publisher and wait for publish to complete
    function createAndPublish(container, opts) {
      return new Promise((resolve, reject) => {
        const pub = OT.initPublisher(container, opts, (err) => {
          if (err) { reject(err); return; }
          session.publish(pub, (err) => {
            if (err) { reject(err); return; }
            resolve(pub);
          });
        });
      });
    }

    // Publish 1: User's webcam + audio (preview shown in left panel)
    try {
      userPublisher = await createAndPublish(userVideoContainer, { videoSource: true, audioSource: true });
      log('ユーザー配信完了');
    } catch (e) {
      log(`ユーザー配信エラー: ${e.message}`);
    }

    // Publish 2: Anam avatar (video + TTS audio for recording, hidden preview)
    if (anamStream) {
      const anamVideoTrack = anamStream.getVideoTracks()[0];
      const anamAudioTrack = anamStream.getAudioTracks()[0];
      if (anamVideoTrack || anamAudioTrack) {
        const hiddenDiv = document.createElement('div');
        hiddenDiv.style.display = 'none';
        document.body.appendChild(hiddenDiv);
        try {
          anamPublisher = await createAndPublish(hiddenDiv, {
            videoSource: anamVideoTrack || null,
            audioSource: anamAudioTrack || false,
          });
          log('アバター配信完了');
        } catch (e) {
          log(`アバター配信エラー: ${e.message}`);
        }
      }
    }

  } catch (e) {
    log(`Vonage 接続エラー: ${e.message}`);
    setStatus('接続失敗');
    connectBtn.disabled = false;
    return;
  }

  // --- Step 5: Connect Anam text WebSocket ---
  log('Anam テキスト WebSocket に接続中...');
  try {
    const wsProto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    wsAnam = new WebSocket(`${wsProto}//${window.location.host}/ws-anam`);

    wsAnam.onopen = () => {
      log('Anam WS 接続完了');
      isConnected = true;
      setStatus('会話中...');
      connectBtn.textContent = '切断';
      connectBtn.className = 'disconnect';
      connectBtn.disabled = false;
    };

    wsAnam.onmessage = (event) => {
      try {
        const msg = JSON.parse(event.data);
        if (msg.type === 'llm_text') {
          handleLLMText(msg.text);
        } else if (msg.type === 'llm_end') {
          handleLLMEnd();
        }
      } catch (e) {
        // ignore
      }
    };

    wsAnam.onclose = () => {
      log('Anam WS 切断');
      if (!isConnected) {
        setStatus('接続失敗');
        connectBtn.disabled = false;
      }
    };

    wsAnam.onerror = (e) => {
      log(`Anam WS エラー: ${e.type}`);
      if (!isConnected) {
        setStatus('接続失敗');
        connectBtn.disabled = false;
      }
    };

    // Keepalive ping — store ID to clear on disconnect
    wsAnamPingId = setInterval(() => {
      if (wsAnam && wsAnam.readyState === WebSocket.OPEN) {
        wsAnam.send('ping');
      }
    }, 15000);
  } catch (e) {
    log(`Anam WS 接続エラー: ${e.message}`);
    setStatus('接続失敗');
    connectBtn.disabled = false;
  }
}

// --- Anam text streaming ---
let currentTalkStream = null;

function handleLLMText(text) {
  if (!anamClient) {
    log(`LLM: ${text}`);
    return;
  }
  try {
    if (!currentTalkStream) {
      currentTalkStream = anamClient.createTalkMessageStream();
    }
    currentTalkStream.streamMessageChunk(text, false);
  } catch (e) {
    log(`Anam stream error: ${e.message}`);
  }
}

function handleLLMEnd() {
  if (!currentTalkStream) return;
  try {
    if (currentTalkStream.isActive()) {
      currentTalkStream.endMessage();
    }
  } catch (e) {
    // ignore
  }
  currentTalkStream = null;
}

function handleInterrupt() {
  if (currentTalkStream) {
    try {
      if (currentTalkStream.isActive()) {
        currentTalkStream.endMessage();
      }
    } catch (e) {
      // ignore
    }
    currentTalkStream = null;
  }
  if (anamClient) {
    anamClient.interruptPersona();
  }
}

// --- Disconnect ---
function disconnect() {
  try {
    isConnected = false;

    if (wsAnamPingId) {
      clearInterval(wsAnamPingId);
      wsAnamPingId = null;
    }
    if (wsAnam) {
      try { wsAnam.close(); } catch (e) {}
      wsAnam = null;
    }

    if (session) {
      try { if (anamPublisher) { session.unpublish(anamPublisher); } } catch (e) {}
      try { if (userPublisher) { session.unpublish(userPublisher); } } catch (e) {}
      try { session.disconnect(); } catch (e) {}
      subscriber = null;
      session = null;
    }

    if (anamStream) {
      anamStream.getTracks().forEach(t => t.stop());
      anamStream = null;
    }
    if (anamClient) {
      try { anamClient.stopStreaming(); } catch (e) {}
      anamClient = null;
    }

    currentTalkStream = null;

    setStatus('切断されています');
    connectBtn.textContent = '接続';
    connectBtn.className = 'connect';
    log('切断完了');
  } catch (e) {
    log('切断エラー: ' + e.message);
  }
}

// --- Event listeners ---
connectBtn.addEventListener('click', () => {
  if (isConnected) disconnect();
  else connect();
});

log('準備完了。接続ボタンをクリックしてください。');
