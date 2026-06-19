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
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LLM Chat · Launchpad</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500;600;700&family=Space+Grotesk:wght@400;500;600;700;800&display=swap" rel="stylesheet">
  <style>
    /* ── Brand tokens ── */
    :root {
      --bg:            #101114;
      --bg-deep:       #0a0a0c;
      --surface:       #1A1B1F;
      --surface-hover: #22232A;
      --border:        #2A2B30;
      --border-light:  #3A3B42;
      --text:          #E8E8E8;
      --text-muted:    #B8B8B8;
      --text-dim:      #6B6B73;
      --text-inv:      #101114;
      --lime:          #A8FF00;
      --lime-20:       rgba(168,255,0,.20);
      --lime-10:       rgba(168,255,0,.10);
      --lime-05:       rgba(168,255,0,.05);
      --glow-lime:     0 0 20px rgba(168,255,0,.18), 0 0 60px rgba(168,255,0,.08);
      --magenta:       #FF00F3;
      --magenta-10:    rgba(255,0,243,.10);
      --glow-magenta:  0 0 20px rgba(255,0,243,.18);
      --font-display:  'Space Grotesk', system-ui, sans-serif;
      --font-mono:     'Geist Mono', ui-monospace, monospace;
      --font-body:     'Geist', system-ui, sans-serif;
      --radius:        4px;
      --ease:          cubic-bezier(.2,.7,.2,1);
      --dur:           200ms;
    }

    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

    html, body { height: 100%; }

    body {
      font-family: var(--font-body);
      background: var(--bg);
      color: var(--text);
      display: flex;
      flex-direction: column;
      height: 100vh;
      overflow: hidden;
      -webkit-font-smoothing: antialiased;
    }

    /* scan-line texture */
    body::before {
      content: '';
      position: fixed; inset: 0; z-index: 0; pointer-events: none;
      background-image: repeating-linear-gradient(
        0deg, transparent, transparent 3px,
        rgba(168,255,0,.010) 3px, rgba(168,255,0,.010) 4px
      );
    }

    /* ambient glow orbs */
    .orb {
      position: fixed; border-radius: 50%;
      filter: blur(120px); pointer-events: none; z-index: 0;
    }
    .orb-lime    { width: 600px; height: 600px; top: -20%; left: 20%; background: rgba(168,255,0,.04); }
    .orb-magenta { width: 400px; height: 400px; bottom: -15%; right: -5%; background: rgba(255,0,243,.05); }

    /* ── Top bar ── */
    .topbar {
      position: relative; z-index: 10;
      display: flex; align-items: center; gap: 12px;
      padding: 0 20px;
      height: 52px;
      background: var(--bg-deep);
      border-bottom: 1px solid var(--border);
      flex-shrink: 0;
    }

    .v-mark {
      flex-shrink: 0;
      width: 22px; height: 22px;
      background: var(--magenta);
      clip-path: polygon(50% 0%, 100% 0%, 50% 100%, 0% 0%);
    }

    .topbar-title {
      font-family: var(--font-display);
      font-size: .9rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: .05em;
      color: var(--text);
      flex: 1;
    }
    .topbar-title span { color: var(--lime); }

    .status-pill {
      display: inline-flex; align-items: center; gap: 6px;
      font-family: var(--font-mono);
      font-size: 10px; font-weight: 700;
      text-transform: uppercase; letter-spacing: .1em;
      padding: 4px 10px;
      border-radius: 20px;
      border: 1px solid var(--border-light);
      color: var(--text-dim);
      background: var(--surface);
      transition: all var(--dur) var(--ease);
      cursor: default;
    }
    .status-pill .dot {
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--text-dim);
      transition: background var(--dur) var(--ease);
    }
    .status-pill.ok   { border-color: rgba(168,255,0,.3); color: var(--lime);    }
    .status-pill.ok   .dot { background: var(--lime); box-shadow: 0 0 6px var(--lime); }
    .status-pill.err  { border-color: rgba(255,80,80,.3);  color: #ff6060; }
    .status-pill.err  .dot { background: #ff6060; }

    .api-label {
      font-family: var(--font-mono);
      font-size: 10px; color: var(--text-dim);
      border: 1px solid var(--border);
      padding: 3px 8px; border-radius: var(--radius);
      white-space: nowrap;
      overflow: hidden; text-overflow: ellipsis;
      max-width: 240px;
    }

    /* ── Model chip (shown when healthy) ── */
    .model-chip {
      font-family: var(--font-mono);
      font-size: 10px; font-weight: 600;
      color: var(--lime);
      background: var(--lime-10);
      border: 1px solid rgba(168,255,0,.25);
      padding: 3px 8px; border-radius: var(--radius);
      display: none;
    }
    .model-chip.visible { display: inline-block; }

    /* ── Chat area ── */
    .chat-wrap {
      position: relative; z-index: 1;
      flex: 1; overflow-y: auto;
      padding: 24px 16px;
      display: flex; flex-direction: column; gap: 16px;
      scroll-behavior: smooth;
    }

    /* empty state */
    .empty-state {
      margin: auto;
      text-align: center;
      opacity: .5;
    }
    .empty-state .big-icon {
      font-size: 2.5rem; margin-bottom: 12px;
    }
    .empty-state p {
      font-family: var(--font-mono);
      font-size: 11px; text-transform: uppercase;
      letter-spacing: .14em; color: var(--text-dim);
    }

    /* ── Messages ── */
    .msg {
      display: flex; gap: 10px; max-width: 780px;
      animation: fadeUp .25s var(--ease) both;
    }
    @keyframes fadeUp {
      from { opacity:0; transform: translateY(10px); }
      to   { opacity:1; transform: translateY(0); }
    }

    .msg.user  { align-self: flex-end;  flex-direction: row-reverse; }
    .msg.bot   { align-self: flex-start; }

    .msg-avatar {
      flex-shrink: 0;
      width: 30px; height: 30px;
      border-radius: var(--radius);
      display: flex; align-items: center; justify-content: center;
      font-family: var(--font-mono);
      font-size: 11px; font-weight: 700;
    }
    .msg.user .msg-avatar { background: var(--lime-20); color: var(--lime); border: 1px solid rgba(168,255,0,.3); }
    .msg.bot  .msg-avatar { background: var(--magenta-10); color: var(--magenta); border: 1px solid rgba(255,0,243,.25); }

    .msg-bubble {
      padding: 10px 14px;
      border-radius: var(--radius);
      font-size: .875rem;
      line-height: 1.65;
      white-space: pre-wrap;
      word-break: break-word;
      max-width: calc(100% - 42px);
    }
    .msg.user .msg-bubble {
      background: var(--lime-10);
      border: 1px solid rgba(168,255,0,.18);
      color: var(--text);
    }
    .msg.bot .msg-bubble {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
    }

    /* thinking indicator */
    .thinking .msg-bubble {
      display: flex; align-items: center; gap: 5px;
      padding: 12px 14px;
    }
    .dot-pulse { display: flex; gap: 4px; }
    .dot-pulse span {
      width: 6px; height: 6px; border-radius: 50%;
      background: var(--text-dim);
      animation: pulse 1.2s ease-in-out infinite;
    }
    .dot-pulse span:nth-child(2) { animation-delay: .2s; }
    .dot-pulse span:nth-child(3) { animation-delay: .4s; }
    @keyframes pulse {
      0%,80%,100% { transform: scale(.7); opacity:.4; }
      40%         { transform: scale(1);  opacity:1; }
    }

    /* error bubble */
    .msg-bubble.error {
      border-color: rgba(255,80,80,.3);
      background: rgba(255,80,80,.06);
      color: #ff8080;
    }

    /* ── Input bar ── */
    .input-bar {
      position: relative; z-index: 10;
      padding: 12px 16px 16px;
      background: var(--bg-deep);
      border-top: 1px solid var(--border);
      flex-shrink: 0;
    }

    .input-inner {
      display: flex; gap: 8px; align-items: flex-end;
      max-width: 860px; margin: 0 auto;
    }

    textarea {
      flex: 1;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      color: var(--text);
      font-family: var(--font-body);
      font-size: .875rem;
      line-height: 1.5;
      padding: 10px 14px;
      resize: none;
      min-height: 44px;
      max-height: 160px;
      outline: none;
      transition: border-color var(--dur) var(--ease);
      overflow-y: auto;
    }
    textarea::placeholder { color: var(--text-dim); }
    textarea:focus { border-color: var(--border-light); }

    .send-btn {
      flex-shrink: 0;
      width: 44px; height: 44px;
      background: var(--lime);
      border: none; border-radius: var(--radius);
      color: var(--text-inv);
      cursor: pointer;
      display: flex; align-items: center; justify-content: center;
      transition: box-shadow var(--dur) var(--ease), transform var(--dur) var(--ease), opacity var(--dur);
    }
    .send-btn:hover:not(:disabled) { box-shadow: var(--glow-lime); transform: translateY(-1px); }
    .send-btn:disabled { opacity: .35; cursor: not-allowed; }
    .send-btn svg { width: 18px; height: 18px; }

    .hint {
      font-family: var(--font-mono);
      font-size: 10px; color: var(--text-dim);
      text-align: center;
      margin-top: 6px;
      letter-spacing: .06em;
    }

    /* ── Scrollbar ── */
    .chat-wrap::-webkit-scrollbar { width: 4px; }
    .chat-wrap::-webkit-scrollbar-track { background: transparent; }
    .chat-wrap::-webkit-scrollbar-thumb { background: var(--border-light); border-radius: 2px; }

    /* ── Responsive ── */
    @media (max-width: 600px) {
      .api-label { display: none; }
      .topbar-title { font-size: .8rem; }
    }
  </style>
</head>
<body>
  <div class="orb orb-lime"></div>
  <div class="orb orb-magenta"></div>

  <!-- Top bar -->
  <header class="topbar">
    <div class="v-mark"></div>
    <div class="topbar-title">LLM <span>Launchpad</span> · Chat</div>
    <span class="api-label" id="apiLabel">{{ api_host }}</span>
    <span class="model-chip" id="modelChip"></span>
    <span class="status-pill" id="statusPill">
      <span class="dot"></span>
      <span id="statusText">Connecting…</span>
    </span>
  </header>

  <!-- Chat messages -->
  <div class="chat-wrap" id="chatWrap">
    <div class="empty-state" id="emptyState">
      <div class="big-icon">⚡</div>
      <p>Send a prompt to start</p>
    </div>
  </div>

  <!-- Input -->
  <div class="input-bar">
    <div class="input-inner">
      <textarea id="promptInput" rows="1"
        placeholder="Ask anything…"
        maxlength="4096"></textarea>
      <button class="send-btn" id="sendBtn" disabled title="Send (Enter)">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor"
             stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M5 12h14M13 6l6 6-6 6"/>
        </svg>
      </button>
    </div>
    <p class="hint">Enter to send &nbsp;·&nbsp; Shift+Enter for newline</p>
  </div>

  <script>
  (() => {
    const chatWrap    = document.getElementById('chatWrap');
    const emptyState  = document.getElementById('emptyState');
    const promptInput = document.getElementById('promptInput');
    const sendBtn     = document.getElementById('sendBtn');
    const statusPill  = document.getElementById('statusPill');
    const statusText  = document.getElementById('statusText');
    const modelChip   = document.getElementById('modelChip');

    let busy = false;

    // ── Health poll ────────────────────────────────────────────────────────
    async function pollHealth() {
      try {
        const r = await fetch('/api/health');
        const d = await r.json();
        if (r.ok && d.status === 'ok') {
          statusPill.className = 'status-pill ok';
          statusText.textContent = 'Online';
          if (d.model) {
            modelChip.textContent = d.model.split('/').pop();
            modelChip.classList.add('visible');
          }
          sendBtn.disabled = busy;
        } else {
          setOffline();
        }
      } catch {
        setOffline();
      }
    }

    function setOffline() {
      statusPill.className = 'status-pill err';
      statusText.textContent = 'Offline';
      modelChip.classList.remove('visible');
      sendBtn.disabled = true;
    }

    pollHealth();
    setInterval(pollHealth, 10000);

    // ── Auto-resize textarea ───────────────────────────────────────────────
    promptInput.addEventListener('input', () => {
      promptInput.style.height = 'auto';
      promptInput.style.height = Math.min(promptInput.scrollHeight, 160) + 'px';
    });

    // ── Send on Enter (Shift+Enter = newline) ──────────────────────────────
    promptInput.addEventListener('keydown', e => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        if (!sendBtn.disabled) send();
      }
    });

    sendBtn.addEventListener('click', send);

    // ── Append a message bubble ────────────────────────────────────────────
    function appendMsg(role, text, extraClass = '') {
      emptyState.style.display = 'none';

      const wrap = document.createElement('div');
      wrap.className = `msg ${role}`;

      const avatar = document.createElement('div');
      avatar.className = 'msg-avatar';
      avatar.textContent = role === 'user' ? 'YOU' : 'AI';

      const bubble = document.createElement('div');
      bubble.className = `msg-bubble ${extraClass}`;
      bubble.textContent = text;

      wrap.appendChild(avatar);
      wrap.appendChild(bubble);
      chatWrap.appendChild(wrap);
      chatWrap.scrollTop = chatWrap.scrollHeight;
      return bubble;
    }

    function appendThinking() {
      emptyState.style.display = 'none';
      const wrap = document.createElement('div');
      wrap.className = 'msg bot thinking';
      wrap.id = 'thinkingMsg';

      const avatar = document.createElement('div');
      avatar.className = 'msg-avatar';
      avatar.textContent = 'AI';

      const bubble = document.createElement('div');
      bubble.className = 'msg-bubble';
      bubble.innerHTML = '<div class="dot-pulse"><span></span><span></span><span></span></div>';

      wrap.appendChild(avatar);
      wrap.appendChild(bubble);
      chatWrap.appendChild(wrap);
      chatWrap.scrollTop = chatWrap.scrollHeight;
    }

    function removeThinking() {
      const el = document.getElementById('thinkingMsg');
      if (el) el.remove();
    }

    // ── Core send ──────────────────────────────────────────────────────────
    async function send() {
      const prompt = promptInput.value.trim();
      if (!prompt || busy) return;

      busy = true;
      sendBtn.disabled = true;
      promptInput.value = '';
      promptInput.style.height = 'auto';

      appendMsg('user', prompt);
      appendThinking();

      try {
        const r = await fetch('/api/chat', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt })
        });
        const d = await r.json();
        removeThinking();

        if (r.ok && d.text !== undefined) {
          appendMsg('bot', d.text.trim());
        } else {
          appendMsg('bot', d.error || 'Unexpected response from API.', 'error');
        }
      } catch (err) {
        removeThinking();
        appendMsg('bot', `Network error: ${err.message}`, 'error');
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
