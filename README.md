# LLM Launchpad

Automated deployment of a self-hosted LLM stack on AWS EC2. The stack uses **vLLM + FastAPI** to serve any HuggingFace model, with optional GPTCache response caching, an Nginx reverse proxy, HTTPS support, and a built-in **Chat UI**.

---

## File Structure

```
llm-launchpad/
├── deploy.conf               ← All configuration lives here
├── deploy.sh                 ← Main deployment script (run this)
├── chat.py                   ← Flask chat UI (port 8080)
├── test_api.sh               ← Smoke test against the running API
└── app/
    ├── fastapi_app.py        ← FastAPI app (no cache)
    └── fastapi_app_cached.py ← FastAPI app (GPTCache enabled)
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| AWS EC2 GPU instance | g5.12xlarge recommended |
| Deep Learning AMI | "Deep Learning Base AMI with Single CUDA (Amazon Linux 2023)" |
| CUDA 11.8+ | Pre-installed on Deep Learning AMIs |
| Inbound ports open | 22 (SSH), 5001 (API), 8080 (Chat UI), 443 (HTTPS optional) |

---

## Quick Start

### 1 — Launch EC2

- Instance type: **g5.12xlarge** (or any G4/G5/P3/P4)
- AMI: **Deep Learning Base AMI with Single CUDA (Amazon Linux 2023)**
- Storage: ≥ 150 GB root volume
- Security group: allow SSH (22), port 5001, and port 8080 inbound

### 2 — SSH into the instance

```bash
chmod 400 your-key.pem
ssh -i "your-key.pem" ec2-user@<EC2-PUBLIC-DNS>
```

### 3 — Upload the scripts

From your local machine:

```bash
scp -i "your-key.pem" -r llm-launchpad/ ec2-user@<EC2-PUBLIC-DNS>:~/
```

### 4 — Edit the config

```bash
nano ~/llm-launchpad/deploy.conf
```

### 5 — Run the deployment

```bash
cd ~/llm-launchpad
bash deploy.sh
```

The script will:
1. Resolve the EC2 public DNS automatically via IMDSv2
2. Create a Python 3.9 virtual environment and install all dependencies
3. Copy the correct app file and `chat.py` to `APP_DIR`
4. Create and enable a **systemd service** (`llm-api`) that starts on boot
5. Configure **Nginx** as a reverse proxy (port 80 → API_PORT) if enabled
6. Start the **Chat UI** service (`llm-chat`) on port 8080 if enabled

> ⚠️ The first startup downloads the model weights from HuggingFace. For Falcon-7B this takes ~10–15 minutes. Watch progress with `sudo journalctl -fu llm-api`.

### 6 — Test the API

```bash
bash test_api.sh
# or against a specific host:
bash test_api.sh --host http://<EC2-PUBLIC-DNS>:5001
```

---

## Configuration Reference

All settings live in `deploy.conf`.

### Model

| Setting | Default | Description |
|---|---|---|
| `HF_MODEL_ID` | `tiiuae/falcon-7b-instruct` | Any vLLM-compatible HuggingFace model |
| `HF_TOKEN` | _(empty)_ | Required for gated models (Llama 2, etc.) |
| `TRUST_REMOTE_CODE` | `true` | Required for most HF models |

### Generation

| Setting | Default | Description |
|---|---|---|
| `MAX_NEW_TOKENS` | `512` | Max tokens to generate per response |
| `TEMPERATURE` | `0.6` | Sampling temperature (higher = more creative) |
| `TENSOR_PARALLEL_SIZE` | `1` | Set to number of GPUs (e.g. `4` for g5.12xlarge) |

### API Server

| Setting | Default | Description |
|---|---|---|
| `API_HOST` | `0.0.0.0` | Interface FastAPI binds to |
| `API_PORT` | `5001` | Port FastAPI listens on |
| `APP_DIR` | `/home/ec2-user/llm-launchpad` | Directory where app files are deployed |
| `LOG_FILE` | `/var/log/llm_api.log` | API service log file |

### Caching

| Setting | Default | Description |
|---|---|---|
| `ENABLE_CACHE` | `false` | `true` = use GPTCache, `false` = no cache |
| `CACHE_TYPE` | `map` | `map` (in-process) or `redis` |
| `CACHE_DIR` | `/home/ubuntu/llm_cache` | Where cache data is stored |

### Nginx

| Setting | Default | Description |
|---|---|---|
| `ENABLE_NGINX` | `false` | Proxy port 80 → `API_PORT` |
| `NGINX_SERVER_NAME` | `_` | `_` matches any hostname, or set your domain |

### HTTPS / SSL

| Setting | Default | Description |
|---|---|---|
| `ENABLE_HTTPS` | `false` | Enable SSL on port 443 |
| `SSL_MODE` | `selfsigned` | `selfsigned` or `letsencrypt` |
| `CERTBOT_EMAIL` | _(empty)_ | Required when `SSL_MODE=letsencrypt` |
| `SSL_CERT_DIR` | `/etc/ssl/llm-api` | Cert/key directory (self-signed only) |

### Systemd Service

| Setting | Default | Description |
|---|---|---|
| `SERVICE_NAME` | `llm-api` | Name of the systemd service |
| `SERVICE_USER` | `ec2-user` | User the service runs as |

### Chat UI

| Setting | Default | Description |
|---|---|---|
| `LAUNCH_CHAT` | `false` | `true` = install Flask and start the chat UI service |
| `CHAT_PORT` | `8080` | Port the chat interface listens on |
| `CHAT_LOG_FILE` | `/var/log/llm_chat.log` | Chat UI service log file |

---

## Chat UI

When `LAUNCH_CHAT=true`, `deploy.sh` installs Flask and starts a second systemd service (`llm-chat`) that serves a web-based chat interface on port 8080.

```
http://<EC2-PUBLIC-DNS>:8080
```

**Features:**
- Sends prompts to `POST /v1/generateText` via a server-side proxy
- Shows response time in milliseconds for each reply
- Dark / light mode toggle (preference saved in `localStorage`)
- Live API health indicator in the top bar (polls every 10 s)
- Model name displayed once the API is reachable

**Run manually:**

```bash
python3 chat.py --api-host http://localhost:5001 --port 8080
```

**Service management:**

```bash
sudo systemctl status  llm-chat
sudo systemctl stop    llm-chat
sudo systemctl start   llm-chat
sudo systemctl restart llm-chat

# Live logs
sudo journalctl -fu llm-chat
tail -f /var/log/llm_chat.log
```

---

## Using a Different Model

Edit `deploy.conf`:

```bash
HF_MODEL_ID="meta-llama/Llama-2-7b-chat-hf"
HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxx"   # required for gated models
TENSOR_PARALLEL_SIZE=4               # use all 4 GPUs on g5.12xlarge
MAX_NEW_TOKENS=1024
TEMPERATURE=0.7
```

Any model supported by vLLM works: Mistral, LLaMA 2/3, Falcon, Phi, Gemma, etc.

---

## Enabling HTTPS (manual / quick test)

For a quick test with a self-signed certificate (no domain required):

```bash
# 1. Generate self-signed cert
sudo mkdir -p /etc/ssl/llm-api
sudo openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/llm-api/key.pem \
  -out    /etc/ssl/llm-api/cert.pem \
  -subj   "/CN=$(curl -sf http://169.254.169.254/latest/meta-data/public-hostname)"

# 2. Write nginx config
sudo tee /etc/nginx/conf.d/llm-api.conf > /dev/null <<'EOF'
server {
    listen 80;
    server_name _;
    return 301 https://$host$request_uri;
}
server {
    listen 443 ssl;
    server_name _;
    ssl_certificate     /etc/ssl/llm-api/cert.pem;
    ssl_certificate_key /etc/ssl/llm-api/key.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;
    ssl_ciphers         HIGH:!aNULL:!MD5;
    location / {
        proxy_pass         http://127.0.0.1:5001;
        proxy_http_version 1.1;
        proxy_set_header   Host              $host;
        proxy_set_header   X-Real-IP         $remote_addr;
        proxy_set_header   X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;
    }
}
EOF

# 3. Reload nginx
sudo nginx -t && sudo systemctl reload nginx
```

> Make sure port 443 is open in your EC2 Security Group. Browsers will show a certificate warning for self-signed certs — click through for testing.

---

## Service Management

```bash
# LLM API
sudo systemctl status  llm-api
sudo systemctl stop    llm-api
sudo systemctl start   llm-api
sudo systemctl restart llm-api
sudo journalctl -fu    llm-api
tail -f /var/log/llm_api.log

# Chat UI
sudo systemctl status  llm-chat
sudo systemctl stop    llm-chat
sudo systemctl start   llm-chat
sudo systemctl restart llm-chat
sudo journalctl -fu    llm-chat
tail -f /var/log/llm_chat.log
```

---

## API Reference

### `GET /`
Health check.
```json
{ "status": "ok", "model": "tiiuae/falcon-7b-instruct" }
```

### `POST /v1/generateText`
Generate text from a prompt.

**Request:**
```json
{ "prompt": "Explain quantum computing in simple terms." }
```

**Response:**
```json
{ "text": "Quantum computing uses quantum bits (qubits)..." }
```

**Example:**
```bash
curl -X POST http://<EC2-PUBLIC-DNS>:5001/v1/generateText \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

---

## Caching

When `ENABLE_CACHE=true`, GPTCache stores responses keyed by prompt text. Repeated identical prompts skip the LLM entirely.

```bash
# Clear the cache
sudo systemctl stop llm-api
rm -rf /home/ubuntu/llm_cache/*
sudo systemctl start llm-api
```

---

## Expected Latency (g5.12xlarge, Falcon-7B)

| Scenario | Latency |
|---|---|
| First call (cold, no cache) | ~600 ms |
| Repeated call (GPTCache hit) | ~3–5 ms |
| Response time shown in Chat UI | per-request ms indicator |

## TO DOS

- Test caching layer
- Terraform support
- Review Ubuntu support

