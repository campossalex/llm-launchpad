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

# ── Helpers ───────────────────────────────────────────────────────────────────
log()  { echo "[$(date '+%H:%M:%S')] $*"; }
die()  { echo "❌  $*" >&2; exit 1; }
need() { command -v "$1" &>/dev/null || die "Required tool not found: $1"; }

# ── Pre-flight checks ─────────────────────────────────────────────────────────
log "Running pre-flight checks..."
need python3
need pip3
need nvidia-smi  || log "⚠️  nvidia-smi not found — vLLM requires an NVIDIA GPU"

CUDA_VER=$(nvcc --version 2>/dev/null | grep "release" | awk '{print $5}' | tr -d ',') || true
log "CUDA version detected: ${CUDA_VER:-unknown}"

# ── Step 1: Install Python dependencies ───────────────────────────────────────
log "Installing Python dependencies..."
$PIP_BIN install --upgrade pip

$PIP_BIN install \
  "openai==0.28.1" \
  langchain \
  vllm \
  gptcache \
  fastapi \
  uvicorn \
  requests

log "✅  Python dependencies installed."

# ── Step 2: Deploy application files ──────────────────────────────────────────
log "Deploying application to $APP_DIR..."
mkdir -p "$APP_DIR"

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

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "============================================================"
echo " Deployment complete!"
echo " API endpoint : http://<EC2-PUBLIC-IP>/v1/generateText"
echo " Health check : http://<EC2-PUBLIC-IP>/"
echo " Logs         : $LOG_FILE"
echo " Manage       : sudo systemctl {start|stop|restart|status} $SERVICE_NAME"
echo "============================================================"
