# LLM Self-Hosting Deployment Scripts

Automated deployment of a self-hosted LLM stack on AWS EC2, based on the article by Chinmay Deshpande. The stack uses **vLLM + LangChain + FastAPI + GPTCache** to serve a HuggingFace model with optional LLM response caching.

---

## File Structure

```
llm-deploy/
├── deploy.conf              ← All configuration lives here
├── deploy.sh                ← Main deployment script (run this)
├── test_api.sh              ← Smoke test against the running API
└── app/
    ├── fastapi_app.py       ← FastAPI app (no cache)
    └── fastapi_app_cached.py← FastAPI app (GPTCache enabled)
```

---

## Prerequisites

| Requirement | Notes |
|---|---|
| AWS EC2 GPU instance | g5.12xlarge recommended |
| Deep Learning AMI | "Deep Learning Base AMI with Single CUDA (Amazon Linux 2023)" or similar |
| ami-015c00898a6352220 | Available in eu-central-1 |
| CUDA 11.8+ | Pre-installed on Deep Learning AMIs |
| Ubuntu | Scripts target Ubuntu; adapt for Amazon Linux if needed |
| Inbound port 80 open | In the EC2 Security Group |

---

## Quick Start

### 1 — Launch EC2

- Instance type: **g5.12xlarge** (or any G4/G5/P3/P4)
- AMI: **Deep Learning Base AMI with Single CUDA (Amazon Linux 2023) 20260609** (Ubuntu)
- Storage: ≥ 150 GB root volume
- Security group: allow SSH (22) and HTTP (80) inbound

### 2 — SSH into the instance

```bash
chmod 400 your-key.pem
ssh -i "your-key.pem" ubuntu@<EC2-PUBLIC-DNS>
```

### 3 — Upload the scripts

From your local machine:

```bash
scp -i "your-key.pem" -r llm-deploy/ ubuntu@<EC2-PUBLIC-DNS>:~/
```

### 4 — Edit the config

```bash
nano ~/llm-deploy/deploy.conf
```

Key settings to review:

| Setting | Default | Description |
|---|---|---|
| `HF_MODEL_ID` | `tiiuae/falcon-7b-instruct` | Any vLLM-compatible HuggingFace model |
| `HF_TOKEN` | _(empty)_ | Required for gated models (Llama 2, etc.) |
| `TENSOR_PARALLEL_SIZE` | `1` | Set to number of GPUs (4 for g5.12xlarge) |
| `MAX_NEW_TOKENS` | `50` | Max generation length |
| `TEMPERATURE` | `0.6` | Sampling temperature |
| `ENABLE_CACHE` | `true` | Enable GPTCache |
| `API_PORT` | `5001` | Internal port FastAPI listens on |
| `ENABLE_NGINX` | `true` | Proxy port 80 → API_PORT |

### 5 — Run the deployment

```bash
cd ~/llm-deploy
bash deploy.sh
```

The script will:
1. Install all Python dependencies (openai, langchain, vllm, gptcache, fastapi, uvicorn)
2. Copy the correct app file to `APP_DIR`
3. Create and enable a **systemd service** that starts on boot
4. Configure **Nginx** as a reverse proxy (port 80 → API_PORT)
5. Start the service

> ⚠️ The first startup will download the model weights from HuggingFace. For Falcon-7B this takes ~10–15 minutes. Watch progress with `sudo journalctl -fu llm-api`.

### 6 — Test the API

```bash
bash test_api.sh
# or against a specific host:
bash test_api.sh --host http://<EC2-PUBLIC-IP>
```

---

## Using a Different Model

Edit `deploy.conf`:

```bash
HF_MODEL_ID="meta-llama/Llama-2-7b-chat-hf"
HF_TOKEN="hf_xxxxxxxxxxxxxxxxxxxx"   # required for gated models
TENSOR_PARALLEL_SIZE=4               # use all 4 GPUs on g5.12xlarge
MAX_NEW_TOKENS=200
TEMPERATURE=0.7
```

Any model supported by vLLM works: Mistral, LLaMA 2/3, Falcon, Phi, Gemma, etc.

---

## Service Management

```bash
sudo systemctl status  llm-api
sudo systemctl stop    llm-api
sudo systemctl start   llm-api
sudo systemctl restart llm-api

# Live logs
sudo journalctl -fu llm-api
tail -f /var/log/llm_api.log
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

**Example with curl:**
```bash
curl -X POST http://<EC2-IP>/v1/generateText \
  -H "Content-Type: application/json" \
  -d '{"prompt": "What is the capital of France?"}'
```

---

## Caching

When `ENABLE_CACHE=true`, GPTCache stores responses keyed by the exact prompt text. Repeated identical prompts skip the LLM entirely, reducing latency from ~600ms to ~4ms.

Cache data is stored in `CACHE_DIR` (default `/home/ubuntu/llm_cache`). To clear the cache:

```bash
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
