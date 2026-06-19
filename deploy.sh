#!/usr/bin/env bash
# =============================================================================
# deploy.sh — Full EC2 LLM deployment automation
# Usage: bash deploy.sh [--config path/to/deploy.conf]
# Requires: Ubuntu (Deep Learning AMI), NVIDIA GPU, CUDA 11.8+
# =============================================================================
set -euo pipefail

# ── Defaults ─────────────────────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/deploy.conf"

# ── Arg parsing ───────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_FILE="$2"; shift 2 ;;
    -h|--help)
      echo "Usage: bash deploy.sh [--config path/to/deploy.conf]"
      exit 0 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# ── Load config ───────────────────────────────────────────────────────────────
if [[ ! -f "$CONFIG_FILE" ]]; then
  echo "❌  Config file not found: $CONFIG_FILE"
  exit 1
fi
# shellcheck source=/dev/null
source "$CONFIG_FILE"
echo "✅  Loaded config: $CONFIG_FILE"

# ── Resolve EC2 public DNS (IMDSv2) ───────────────────────────────────────────
resolve_public_dns() {
  local token dns
  token=$(curl -sf -X PUT "http://169.254.169.254/latest/api/token" \
    -H "X-aws-ec2-metadata-token-ttl-seconds: 300" --connect-timeout 2) || true
  if [[ -n "$token" ]]; then
    dns=$(curl -sf -H "X-aws-ec2-metadata-token: $token" \
      "http://169.254.169.254/latest/meta-data/public-hostname" --connect-timeout 2) || true
  fi
  echo "${dns:-}"
}

PUBLIC_DNS=$(resolve_public_dns)
if [[ -n "$PUBLIC_DNS" ]]; then
  echo "✅  EC2 public DNS: $PUBLIC_DNS"
else
  echo "⚠️  Could not resolve EC2 public DNS — falling back to 127.0.0.1"
  PUBLIC_DNS="127.0.0.1"
fi

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
die()  { echo "❌  $*" >&2; exit 1; }
need() { command -v "$1" &>/dev/null || die "Required tool not found: $1"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
log "Running pre-flight checks..."
nvidia-smi &>/dev/null || log "⚠️  nvidia-smi not found — vLLM requires an NVIDIA GPU"

CUDA_VER=$(nvcc --version 2>/dev/null | grep "release" | awk '{print $5}' | tr -d ',') || true
log "CUDA version detected: ${CUDA_VER:-unknown}"

# Require Python 3.9 — this is the version proven to work with vllm==0.3.3
PYTHON39=$(command -v python3.9 2>/dev/null || true)
[[ -n "$PYTHON39" ]] || die "Python 3.9 not found. Install it with: sudo dnf install python3.9 python3.9-devel"
log "Python 3.9 found: $PYTHON39"

# ── Step 1: Create venv and install Python dependencies ───────────────────────
log "Installing Python dependencies..."

mkdir -p "$APP_DIR"
VENV_DIR="${APP_DIR}/venv"
PYTHON_BIN="${VENV_DIR}/bin/python"
PIP_BIN="${VENV_DIR}/bin/pip"

# Always wipe and rebuild the venv for a clean install
log "Removing existing virtual environment..."
rm -rf "$VENV_DIR"
log "Creating Python 3.9 virtual environment..."
"$PYTHON39" -m venv "$VENV_DIR"

# Verify the venv is Python 3.9 before installing anything
ACTUAL_VER=$("$PYTHON_BIN" --version 2>&1)
log "Venv Python: ${ACTUAL_VER}"
echo "${ACTUAL_VER}" | grep -q "3.9" || die "Venv is not Python 3.9 (got: ${ACTUAL_VER})"

"$PIP_BIN" install --upgrade pip

# Pinned versions — proven working combination on Python 3.9
# Do NOT change these versions without testing:
#   vllm==0.3.3         last version supporting Python 3.9
#   transformers==4.40.2 compatible with vllm 0.3.3 and Falcon 7B
#   openai==0.28.1      required by langchain at this version
"$PIP_BIN" install \
  "vllm==0.3.3" \
  "transformers==4.40.2" \
  "openai==0.28.1" \
  langchain \
  fastapi \
  uvicorn \
  requests \
  flask

# Smoke test — abort if imports fail before touching systemd
log "Verifying imports..."
"$PYTHON_BIN" -c "from vllm import LLM, SamplingParams; import uvicorn, fastapi; print('✅ imports OK')" \
  || die "Import check failed — aborting deployment"

log "✅  Python dependencies installed."

# ── Step 2: Deploy application files ──────────────────────────────────────────
log "Deploying application to $APP_DIR..."

# Choose app file based on cache setting
if [[ "$ENABLE_CACHE" == "true" ]]; then
  APP_SRC="${SCRIPT_DIR}/app/fastapi_app_cached.py"
  APP_FILE="fastapi_app_cached.py"
  log "Cache enabled — using GPTCache app."
else
  APP_SRC="${SCRIPT_DIR}/app/fastapi_app.py"
  APP_FILE="fastapi_app.py"
  log "Cache disabled — using plain app."
fi

cp "$APP_SRC" "${APP_DIR}/${APP_FILE}"

# Deploy chat UI
cp "${SCRIPT_DIR}/chat.py" "${APP_DIR}/chat.py"

# Create cache directory if needed
if [[ "$ENABLE_CACHE" == "true" ]]; then
  mkdir -p "$CACHE_DIR"
  log "Cache directory: $CACHE_DIR"
fi

log "✅  App files deployed."

# ── Step 3: Create systemd service ────────────────────────────────────────────
log "Creating systemd service: $SERVICE_NAME..."

SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

# Build environment block
ENV_BLOCK="Environment=\"HF_MODEL_ID=${HF_MODEL_ID}\"
Environment=\"TRUST_REMOTE_CODE=${TRUST_REMOTE_CODE}\"
Environment=\"MAX_NEW_TOKENS=${MAX_NEW_TOKENS}\"
Environment=\"TEMPERATURE=${TEMPERATURE}\"
Environment=\"TENSOR_PARALLEL_SIZE=${TENSOR_PARALLEL_SIZE}\"
Environment=\"API_HOST=${API_HOST}\"
Environment=\"API_PORT=${API_PORT}\"
Environment=\"CACHE_DIR=${CACHE_DIR}\""

if [[ -n "$HF_TOKEN" ]]; then
  ENV_BLOCK="${ENV_BLOCK}
Environment=\"HUGGING_FACE_HUB_TOKEN=${HF_TOKEN}\""
fi

sudo tee "$SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=LLM Inference API (vLLM + FastAPI)
After=network.target

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
${ENV_BLOCK}
ExecStart=${PYTHON_BIN} ${APP_DIR}/${APP_FILE}
Restart=on-failure
RestartSec=10
StandardOutput=append:${LOG_FILE}
StandardError=append:${LOG_FILE}

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable "$SERVICE_NAME"
log "✅  Systemd service created and enabled."

# ── Step 4: Configure Nginx reverse proxy ─────────────────────────────────────
if [[ "$ENABLE_NGINX" == "true" ]]; then
  log "Configuring Nginx reverse proxy (80 → $API_PORT)..."

  need nginx || { sudo apt-get install -y nginx; }

  sudo tee "/etc/nginx/sites-available/${SERVICE_NAME}" > /dev/null <<EOF
server {
    listen 80;
    server_name ${NGINX_SERVER_NAME};

    location / {
        proxy_pass         http://127.0.0.1:${API_PORT};
        proxy_http_version 1.1;
        proxy_set_header   Host              \$host;
        proxy_set_header   X-Real-IP         \$remote_addr;
        proxy_set_header   X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_read_timeout 120s;
    }
}
EOF

  sudo ln -sf \
    "/etc/nginx/sites-available/${SERVICE_NAME}" \
    "/etc/nginx/sites-enabled/${SERVICE_NAME}" 2>/dev/null || true

  sudo nginx -t && sudo systemctl reload nginx
  log "✅  Nginx configured."
fi

# ── Step 5: Start the service ─────────────────────────────────────────────────
log "Starting $SERVICE_NAME..."
sudo systemctl start "$SERVICE_NAME"
sleep 3

if systemctl is-active --quiet "$SERVICE_NAME"; then
  log "✅  Service is running."
else
  log "⚠️  Service may have failed. Check logs:"
  log "    sudo journalctl -u $SERVICE_NAME -n 50 --no-pager"
  log "    tail -f $LOG_FILE"
fi

# ── Step 6: Start chat UI (optional) ──────────────────────────────────────────
CHAT_SERVICE_NAME="llm-chat"

if [[ "${LAUNCH_CHAT:-false}" == "true" ]]; then
  log "Deploying chat UI service on port ${CHAT_PORT:-8080}..."

  CHAT_SERVICE_FILE="/etc/systemd/system/${CHAT_SERVICE_NAME}.service"

  sudo tee "$CHAT_SERVICE_FILE" > /dev/null <<EOF
[Unit]
Description=LLM Chat UI (Flask)
After=network.target ${SERVICE_NAME}.service

[Service]
Type=simple
User=${SERVICE_USER}
WorkingDirectory=${APP_DIR}
Environment="LLM_API_HOST=http://${PUBLIC_DNS}:${API_PORT}"
Environment="CHAT_PORT=${CHAT_PORT:-8080}"
ExecStart=${PYTHON_BIN} ${APP_DIR}/chat.py
Restart=on-failure
RestartSec=5
StandardOutput=append:${CHAT_LOG_FILE:-/var/log/llm_chat.log}
StandardError=append:${CHAT_LOG_FILE:-/var/log/llm_chat.log}

[Install]
WantedBy=multi-user.target
EOF

  sudo systemctl daemon-reload
  sudo systemctl enable "$CHAT_SERVICE_NAME"
  sudo systemctl start "$CHAT_SERVICE_NAME"
  sleep 2

  if systemctl is-active --quiet "$CHAT_SERVICE_NAME"; then
    log "✅  Chat UI is running on port ${CHAT_PORT:-8080}."
  else
    log "⚠️  Chat UI may have failed. Check logs:"
    log "    sudo journalctl -u $CHAT_SERVICE_NAME -n 50 --no-pager"
    log "    tail -f ${CHAT_LOG_FILE:-/var/log/llm_chat.log}"
  fi
else
  log "ℹ️  Chat UI skipped (LAUNCH_CHAT=${LAUNCH_CHAT:-false}). Set LAUNCH_CHAT=true in deploy.conf to enable."
fi

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Deployment complete!"
echo " API endpoint : http://${PUBLIC_DNS}:${API_PORT}/v1/generateText"
echo " Health check : http://${PUBLIC_DNS}:${API_PORT}/"
echo " Logs         : $LOG_FILE"
echo " Manage       : sudo systemctl {start|stop|restart|status} $SERVICE_NAME"
if [[ "${LAUNCH_CHAT:-false}" == "true" ]]; then
echo " Chat UI      : http://${PUBLIC_DNS}:${CHAT_PORT:-8080}"
echo " Chat logs    : ${CHAT_LOG_FILE:-/var/log/llm_chat.log}"
echo " Manage chat  : sudo systemctl {start|stop|restart|status} $CHAT_SERVICE_NAME"
fi
echo "============================================================"
