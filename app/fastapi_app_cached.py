"""
FastAPI LLM inference server — GPTCache enabled.
Generated from deploy.conf at deployment time by deploy.sh.
"""
import hashlib
import os
from typing import Any

import langchain
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from gptcache import Cache
from gptcache.manager.factory import manager_factory
from gptcache.processor.pre import get_prompt
from langchain.cache import GPTCache
from langchain.llms import VLLM

# ── Config from environment (injected by deploy.sh) ─────────────────────────
MODEL_ID          = os.environ.get("HF_MODEL_ID", "tiiuae/falcon-7b-instruct")
TRUST_REMOTE_CODE = os.environ.get("TRUST_REMOTE_CODE", "true").lower() == "true"
MAX_NEW_TOKENS    = int(os.environ.get("MAX_NEW_TOKENS", 50))
TEMPERATURE       = float(os.environ.get("TEMPERATURE", 0.6))
TENSOR_PARALLEL   = int(os.environ.get("TENSOR_PARALLEL_SIZE", 1))
API_HOST          = os.environ.get("API_HOST", "0.0.0.0")
API_PORT          = int(os.environ.get("API_PORT", 5001))
CACHE_DIR         = os.environ.get("CACHE_DIR", "/home/ubuntu/llm_cache")

os.makedirs(CACHE_DIR, exist_ok=True)


# ── GPTCache initializer ────────────────────────────────────────────────────
def get_hashed_name(name: str) -> str:
    return hashlib.sha256(name.encode()).hexdigest()


def init_gptcache(cache_obj: Cache, llm_name: str) -> None:
    hashed = get_hashed_name(llm_name)
    cache_obj.init(
        pre_embedding_func=get_prompt,
        data_manager=manager_factory(
            manager="map",
            data_dir=os.path.join(CACHE_DIR, f"map_cache_{hashed}"),
        ),
    )


langchain.llm_cache = GPTCache(init_gptcache)

# ── LLM ─────────────────────────────────────────────────────────────────────
app = FastAPI(title="LLM Inference API (cached)")

llm = VLLM(
    model=MODEL_ID,
    trust_remote_code=TRUST_REMOTE_CODE,
    max_new_tokens=MAX_NEW_TOKENS,
    temperature=TEMPERATURE,
    tensor_parallel_size=TENSOR_PARALLEL,
)


@app.get("/")
def health() -> dict[str, Any]:
    return {"status": "ok", "model": MODEL_ID, "cache": "gptcache/map"}


@app.post("/v1/generateText")
async def generate_text(request: Request) -> Response:
    body   = await request.json()
    prompt = body.get("prompt", "")
    output = llm(prompt)
    return JSONResponse({"text": output})


if __name__ == "__main__":
    uvicorn.run(app, host=API_HOST, port=API_PORT)
