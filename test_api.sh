#!/usr/bin/env bash
# =============================================================================
# test_api.sh — Quick smoke test for the LLM inference API
# Usage: bash test_api.sh [--config deploy.conf] [--host http://localhost:5001]
# =============================================================================
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_FILE="${SCRIPT_DIR}/deploy.conf"
HOST=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --config) CONFIG_FILE="$2"; shift 2 ;;
    --host)   HOST="$2";        shift 2 ;;
    *) echo "Unknown argument: $1"; exit 1 ;;
  esac
done

# Load config for port if no explicit host given
if [[ -f "$CONFIG_FILE" ]]; then
  source "$CONFIG_FILE"
fi

HOST="${HOST:-http://localhost:${API_PORT:-5001}}"
PROMPT="Who is the president of the United States?"

echo "============================================================"
echo " LLM API Smoke Test"
echo " Target : $HOST"
echo " Prompt : $PROMPT"
echo "============================================================"

# ── Health check ──────────────────────────────────────────────────────────────
echo ""
echo "1. Health check (GET /)..."
HEALTH=$(curl -sf "${HOST}/" || echo "FAILED")
echo "   Response: $HEALTH"

# ── Inference (first call — cold) ─────────────────────────────────────────────
echo ""
echo "2. First inference call (cold)..."
START=$(date +%s%N)
RESPONSE=$(curl -sf -X POST "${HOST}/v1/generateText" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"${PROMPT}\"}" || echo "FAILED")
END=$(date +%s%N)
LATENCY_MS=$(( (END - START) / 1000000 ))
echo "   Latency : ${LATENCY_MS} ms"
echo "   Response: $RESPONSE"

# ── Inference (second call — should hit cache if enabled) ─────────────────────
echo ""
echo "3. Second inference call (cached if ENABLE_CACHE=true)..."
START=$(date +%s%N)
RESPONSE2=$(curl -sf -X POST "${HOST}/v1/generateText" \
  -H "Content-Type: application/json" \
  -d "{\"prompt\": \"${PROMPT}\"}" || echo "FAILED")
END=$(date +%s%N)
LATENCY2_MS=$(( (END - START) / 1000000 ))
echo "   Latency : ${LATENCY2_MS} ms"
echo "   Response: $RESPONSE2"

echo ""
echo "============================================================"
echo " Done. Cold: ${LATENCY_MS}ms  |  Second: ${LATENCY2_MS}ms"
echo "============================================================"
