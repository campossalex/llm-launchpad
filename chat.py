"""
chat.py — Simple chat interface for the LLM Inference API
Usage: python chat.py [--api-host http://localhost:5001] [--port 8080]
"""
import argparse
import urllib.request
import urllib.error
import json
import os

from flask import Flask, render_template_string, request, jsonify

parser = argparse.ArgumentParser(description="LLM Chat UI")
parser.add_argument("--api-host", default=os.environ.get("LLM_API_HOST", "http://localhost:5001"),
                    help="Base URL of the LLM inference API")
parser.add_argument("--port", type=int, default=int(os.environ.get("CHAT_PORT", 8080)),
                    help="Port to run this chat UI on")
args, _ = parser.parse_known_args()

API_HOST = args.api_host.rstrip("/")

app = Flask(__name__)


# ── Proxy helpers ─────────────────────────────────────────────────────────────

def _api_health():
    try:
        req = urllib.request.Request(f"{API_HOST}/", headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as r:
            return json.loads(r.read().decode()), None
    except Exception as e:
        return None, str(e)


def _api_generate(prompt: str):
    payload = json.dumps({"prompt": prompt}).encode()
    req = urllib.request.Request(
        f"{API_HOST}/v1/generateText",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


# ── Flask routes ──────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template_string(HTML, api_host=API_HOST)


@app.route("/api/health")
def health():
    data, err = _api_health()
    if err:
        return jsonify({"status": "error", "detail": err}), 502
    return jsonify(data)


@app.route("/api/chat", methods=["POST"])
def chat():
    body = request.get_json(force=True)
    prompt = (body.get("prompt") or "").strip()
    if not prompt:
        return jsonify({"error": "prompt is required"}), 400
    try:
        result = _api_generate(prompt)
        return jsonify(result)
    except urllib.error.URLError as e:
        return jsonify({"error": f"Cannot reach LLM API: {e.reason}"}), 502
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ── HTML / CSS / JS ───────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM Launchpad · Chat</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg:           #212121;
      --surface:      #2f2f2f;
      --surface-2:    #3a3a3a;
      --border:       #404040;
      --text:         #ececec;
      --text-muted:   #8e8ea0;
      --text-dim:     #6e6e80;
      --accent:       #10a37f;
      --accent-hover: #0d8f6e;
      --error:        #ef4444;
    }
    [data-theme="light"] {
      --bg:           #ffffff;
      --surface:      #f4f4f4;
      --surface-2:    #e8e8e8;
      --border:       #e0e0e0;
      --text:         #1a1a1a;
      --text-muted:   #6b7280;
      --text-dim:     #9ca3af;
      --accent:       #10a37f;
      --accent-hover: #0d8f6e;
      --error:        #dc2626;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    html, body { height: 100%; }

    body {
      font-family: 'Inter', system-ui, sans-serif;
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* ── Top bar ── */
    .topbar {
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      height: 48px;
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
      background: var(--bg);
    }

    .topbar-model {
      font-size: .875rem;
      font-weight: 600;
      color: var(--text);
      display: flex;
      align-items: center;
      gap: 8px;
    }

    .status-dot {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--text-dim);
      transition: background .2s, box-shadow .2s;
      flex-shrink: 0;
    }
    .status-dot.ok  { background: var(--accent); box-shadow: 0 0 6px rgba(16,163,127,.5); }
    .status-dot.err { background: var(--error); }

    .topbar-left {
      position: absolute;
      left: 16px;
      font-size: .8rem;
      font-weight: 600;
      color: var(--text-muted);
      letter-spacing: .01em;
      white-space: nowrap;
    }

    .topbar-right {
      position: absolute;
      right: 16px;
      display: flex;
      align-items: center;
      gap: 10px;
    }

    .status-label {
      font-size: .75rem;
      color: var(--text-dim);
    }

    .theme-btn {
      width: 30px; height: 30px;
      border-radius: 50%;
      border: 1px solid var(--border);
      background: var(--surface);
      color: var(--text-muted);
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: background .2s, border-color .2s, color .2s;
      flex-shrink: 0;
    }
    .theme-btn:hover { background: var(--surface-2); color: var(--text); }
    .theme-btn svg { width: 15px; height: 15px; }

    /* ── Chat area ── */
    .chat-wrap {
      flex: 1;
      overflow-y: auto;
      padding: 24px 16px 8px;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0;
      scroll-behavior: smooth;
    }

    .chat-wrap::-webkit-scrollbar { width: 6px; }
    .chat-wrap::-webkit-scrollbar-track { background: transparent; }
    .chat-wrap::-webkit-scrollbar-thumb { background: var(--surface-2); border-radius: 3px; }

    /* ── Empty state ── */
    .empty-state {
      margin: auto;
      text-align: center;
      color: var(--text-dim);
    }
    .empty-icon {
      font-size: 2rem;
      margin-bottom: 12px;
    }
    .empty-state h2 {
      font-size: 1.25rem;
      font-weight: 600;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .empty-state p {
      font-size: .875rem;
      color: var(--text-dim);
    }

    /* ── Message rows ── */
    .msg-row {
      width: 100%;
      max-width: 720px;
      padding: 16px 0;
      animation: fadeIn .2s ease both;
    }
    @keyframes fadeIn {
      from { opacity: 0; transform: translateY(6px); }
      to   { opacity: 1; transform: translateY(0); }
    }

    /* User message */
    .msg-row.user {
      display: flex;
      justify-content: flex-end;
    }
    .user-bubble {
      background: var(--surface);
      border-radius: 18px;
      padding: 10px 16px;
      font-size: .9375rem;
      line-height: 1.6;
      white-space: pre-wrap;
      word-break: break-word;
      max-width: 85%;
      color: var(--text);
    }

    /* Assistant message */
    .msg-row.bot {
      display: flex;
      gap: 12px;
      align-items: flex-start;
    }
    .bot-avatar {
      flex-shrink: 0;
      width: 28px; height: 28px;
      border-radius: 50%;
      background: var(--accent);
      display: flex; align-items: center; justify-content: center;
      margin-top: 2px;
      font-size: .7rem;
      font-weight: 600;
      color: white;
      letter-spacing: .02em;
      user-select: none;
    }

    .bot-text {
      font-size: .9375rem;
      line-height: 1.7;
      white-space: pre-wrap;
      word-break: break-word;
      color: var(--text);
      padding-top: 2px;
      flex: 1;
    }
    .bot-text.error { color: var(--error); }

    .response-time {
      font-size: .7rem;
      color: var(--text-dim);
      margin-top: 6px;
      display: flex;
      align-items: center;
      gap: 4px;
    }
    .response-time svg {
      width: 11px; height: 11px;
      opacity: .6;
    }

    /* thinking dots */
    .thinking-dots {
      display: flex;
      gap: 4px;
      padding-top: 6px;
    }
    .thinking-dots span {
      width: 7px; height: 7px;
      border-radius: 50%;
      background: var(--text-dim);
      animation: bounce 1.2s ease-in-out infinite;
    }
    .thinking-dots span:nth-child(2) { animation-delay: .15s; }
    .thinking-dots span:nth-child(3) { animation-delay: .3s; }
    @keyframes bounce {
      0%,60%,100% { transform: translateY(0); opacity: .4; }
      30%          { transform: translateY(-5px); opacity: 1; }
    }

    /* ── Input area ── */
    .input-area {
      flex-shrink: 0;
      padding: 12px 16px 20px;
      background: var(--bg);
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 8px;
    }

    .input-box {
      width: 100%;
      max-width: 720px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 16px;
      display: flex;
      align-items: flex-end;
      padding: 10px 12px 10px 16px;
      gap: 8px;
      transition: border-color .2s;
    }
    .input-box:focus-within { border-color: var(--surface-2); }

    textarea {
      flex: 1;
      background: transparent;
      border: none;
      outline: none;
      color: var(--text);
      font-family: 'Inter', system-ui, sans-serif;
      font-size: .9375rem;
      line-height: 1.5;
      resize: none;
      min-height: 24px;
      max-height: 180px;
      overflow-y: auto;
      padding: 0;
    }
    textarea::placeholder { color: var(--text-dim); }

    .send-btn {
      flex-shrink: 0;
      width: 34px; height: 34px;
      border-radius: 50%;
      border: none;
      background: var(--accent);
      color: white;
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: background .2s, opacity .2s;
    }
    .send-btn:hover:not(:disabled) { background: var(--accent-hover); }
    .send-btn:disabled { opacity: .35; cursor: not-allowed; }
    .send-btn svg { width: 16px; height: 16px; }

    .input-hint {
      font-size: .75rem;
      color: var(--text-dim);
    }

    @media (max-width: 600px) {
      .topbar-right .status-label { display: none; }
    }
  </style>
</head>
<body>

  <!-- Top bar -->
  <header class="topbar">
    <span class="topbar-left">LLM Launchpad</span>
    <div class="topbar-model">
      <span id="modelName">Chat</span>
    </div>
    <div class="topbar-right">
      <span class="status-dot" id="statusDot"></span>
      <span class="status-label" id="statusLabel">Connecting…</span>
      <button class="theme-btn" id="themeBtn" title="Toggle light/dark mode">
        <svg id="themeIcon" viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>
        </svg>
      </button>
    </div>
  </header>

  <!-- Messages -->
  <div class="chat-wrap" id="chatWrap">
    <div class="empty-state" id="emptyState">
      <div class="empty-icon">🚀</div>
      <h2>LLM Launchpad</h2>
      <p>Type a message below to get started.</p>
    </div>
  </div>

  <!-- Input -->
  <div class="input-area">
    <div class="input-box">
      <textarea id="promptInput" rows="1" placeholder="Message…" maxlength="4096"></textarea>
      <button class="send-btn" id="sendBtn" disabled title="Send (Enter)">
        <svg viewBox="0 0 16 16" fill="currentColor">
          <path d="M.5 1.163A1 1 0 0 1 1.97.28l12.868 6.837a1 1 0 0 1 0 1.766L1.969 15.72A1 1 0 0 1 .5 14.836V10.33a1 1 0 0 1 .816-.983L8.5 8 1.316 6.653A1 1 0 0 1 .5 5.67V1.163Z"/>
        </svg>
      </button>
    </div>
    <span class="input-hint">Enter to send &nbsp;·&nbsp; Shift+Enter for new line</span>
  </div>

  <script>
  (() => {
    const chatWrap    = document.getElementById('chatWrap');
    const emptyState  = document.getElementById('emptyState');
    const promptInput = document.getElementById('promptInput');
    const sendBtn     = document.getElementById('sendBtn');
    const statusDot   = document.getElementById('statusDot');
    const statusLabel = document.getElementById('statusLabel');
    const modelName   = document.getElementById('modelName');
    const themeBtn    = document.getElementById('themeBtn');
    const themeIcon   = document.getElementById('themeIcon');
    const html        = document.documentElement;

    let busy = false;

    // ── Theme toggle ───────────────────────────────────────────────────────
    const MOON = `<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>`;
    const SUN  = `<circle cx="12" cy="12" r="5"/><line x1="12" y1="1" x2="12" y2="3"/><line x1="12" y1="21" x2="12" y2="23"/><line x1="4.22" y1="4.22" x2="5.64" y2="5.64"/><line x1="18.36" y1="18.36" x2="19.78" y2="19.78"/><line x1="1" y1="12" x2="3" y2="12"/><line x1="21" y1="12" x2="23" y2="12"/><line x1="4.22" y1="19.78" x2="5.64" y2="18.36"/><line x1="18.36" y1="5.64" x2="19.78" y2="4.22"/>`;

    function applyTheme(theme) {
      html.setAttribute('data-theme', theme);
      themeIcon.innerHTML = theme === 'dark' ? MOON : SUN;
      localStorage.setItem('llm-theme', theme);
    }

    const savedTheme = localStorage.getItem('llm-theme') || 'dark';
    applyTheme(savedTheme);

    themeBtn.addEventListener('click', () => {
      applyTheme(html.getAttribute('data-theme') === 'dark' ? 'light' : 'dark');
    });

    // ── Health poll ────────────────────────────────────────────────────────
    async function pollHealth() {
      try {
        const r = await fetch('/api/health');
        const d = await r.json();
        if (r.ok && d.status === 'ok') {
          statusDot.className = 'status-dot ok';
          statusLabel.textContent = 'Connected';
          if (d.model) modelName.textContent = d.model.split('/').pop();
          if (!busy) sendBtn.disabled = false;
        } else {
          setOffline();
        }
      } catch {
        setOffline();
      }
    }

    function setOffline() {
      statusDot.className = 'status-dot err';
      statusLabel.textContent = 'Offline';
      sendBtn.disabled = true;
    }

    pollHealth();
    setInterval(pollHealth, 10000);

    // ── Auto-grow textarea ─────────────────────────────────────────────────
    promptInput.addEventListener('input', () => {
      promptInput.style.height = 'auto';
      promptInput.style.height = Math.min(promptInput.scrollHeight, 180) + 'px';
    });

    promptInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) send();
      }
    });

    sendBtn.addEventListener('click', send);

    // ── Helpers ───────────────────────────────────────────────────────────
    function appendUser(text) {
      emptyState.style.display = 'none';
      const row = document.createElement('div');
      row.className = 'msg-row user';
      const bubble = document.createElement('div');
      bubble.className = 'user-bubble';
      bubble.textContent = text;
      row.appendChild(bubble);
      chatWrap.appendChild(row);
      chatWrap.scrollTop = chatWrap.scrollHeight;
    }

    function appendBot(text, isError = false, elapsedMs = null) {
      emptyState.style.display = 'none';
      const row = document.createElement('div');
      row.className = 'msg-row bot';

      const avatar = document.createElement('div');
      avatar.className = 'bot-avatar';
      avatar.textContent = 'AI';

      const body = document.createElement('div');
      body.style.flex = '1';

      const textEl = document.createElement('div');
      textEl.className = isError ? 'bot-text error' : 'bot-text';
      textEl.textContent = text;
      body.appendChild(textEl);

      if (elapsedMs !== null && !isError) {
        const timing = document.createElement('div');
        timing.className = 'response-time';
        timing.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"
          stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/></svg>
          ${elapsedMs.toLocaleString()} ms`;
        body.appendChild(timing);
      }

      row.appendChild(avatar);
      row.appendChild(body);
      chatWrap.appendChild(row);
      chatWrap.scrollTop = chatWrap.scrollHeight;
    }

    function showThinking() {
      emptyState.style.display = 'none';
      const row = document.createElement('div');
      row.className = 'msg-row bot';
      row.id = 'thinkingRow';

      const avatar = document.createElement('div');
      avatar.className = 'bot-avatar';
      avatar.textContent = 'AI';

      const dots = document.createElement('div');
      dots.className = 'thinking-dots';
      dots.innerHTML = '<span></span><span></span><span></span>';

      row.appendChild(avatar);
      row.appendChild(dots);
      chatWrap.appendChild(row);
      chatWrap.scrollTop = chatWrap.scrollHeight;
    }

    function removeThinking() {
      const el = document.getElementById('thinkingRow');
      if (el) el.remove();
    }

    // ── Send ──────────────────────────────────────────────────────────────
    async function send() {
      const prompt = promptInput.value.trim();
      if (!prompt || busy) return;

      busy = true;
      sendBtn.disabled = true;
      promptInput.value = '';
      promptInput.style.height = 'auto';

      appendUser(prompt);
      showThinking();

      const t0 = performance.now();
      try {
        const r = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt })
        });
        const d = await r.json();
        const elapsed = Math.round(performance.now() - t0);
        removeThinking();
        if (r.ok && d.text !== undefined) {
          appendBot(d.text.trim(), false, elapsed);
        } else {
          appendBot(d.error || 'Unexpected response.', true);
        }
      } catch (err) {
        removeThinking();
        appendBot(`Network error: ${err.message}`, true);
      } finally {
        busy = false;
        sendBtn.disabled = false;
        promptInput.focus();
        chatWrap.scrollTop = chatWrap.scrollHeight;
      }
    }

    promptInput.focus();
  })();
  </script>
</body>
</html>
"""

if __name__ == "__main__":
    print(f"  LLM Chat UI  →  http://0.0.0.0:{args.port}")
    print(f"  LLM API      →  {API_HOST}")
    app.run(host="0.0.0.0", port=args.port, debug=False)
