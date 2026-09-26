import os
import json
import logging
import asyncio
import re
import httpx
from typing import Optional
from dotenv import load_dotenv

from llama_cpp import Llama, LlamaGrammar

load_dotenv()
logger = logging.getLogger("VeraArchitect")

LOCAL_MAX_TOKENS = 250
_local_model_instance = None
_local_model_loaded = False

try:
    _schema = {"type":"object","properties":{"body":{"type":"string"},"cta":{"type":"string"},"rationale":{"type":"string"}},"required":["body","cta","rationale"]}
    JSON_GRAMMAR = LlamaGrammar.from_json_schema(json.dumps(_schema))
except Exception:
    JSON_GRAMMAR = None

def get_local_model():
    global _local_model_instance, _local_model_loaded, LOCAL_MAX_TOKENS
    if _local_model_loaded:
        return _local_model_instance
    
    _local_model_loaded = True
    try:
        LOCAL_7B_P95 = float(os.getenv("LOCAL_7B_P95", "999.0")) 
        if LOCAL_7B_P95 <= 14.0:
            local_repo = "bartowski/Qwen2.5-7B-Instruct-GGUF"
            local_file = "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
            LOCAL_MAX_TOKENS = 150
            logger.info(f"Using 7b for local tier since p95 latency ({LOCAL_7B_P95}s) is within 14s budget.")
        else:
            local_repo = "Qwen/Qwen2.5-3B-Instruct-GGUF"
            local_file = "qwen2.5-3b-instruct-q4_k_m.gguf"
            LOCAL_MAX_TOKENS = 250
            logger.info(f"7b p95 {LOCAL_7B_P95}s exceeds 14s budget, using 3b instead.")
            
        _local_model_instance = Llama.from_pretrained(repo_id=local_repo, filename=local_file, n_ctx=2048, n_threads=os.cpu_count(), verbose=False)
    except Exception as e:
        logger.warning(f"Failed to load local model: {e}")
        _local_model_instance = None
        
    return _local_model_instance

def clean_json(text: str) -> Optional[dict]:
    try:
        cleaned = re.sub(r'```json\n?|\n?```', '', text).strip()
        return json.loads(cleaned)
    except:
        return None

async def call_nvidia(prompt: str, system: str, timeout: float) -> Optional[dict]:
    key = os.getenv("NVIDIA_API_KEY")
    if not key: return None
    payload = {
        "model": "z-ai/glm-5.3",
        "messages": [{"role": "system", "content": system + "\n\nRETURN JSON ONLY."}, {"role": "user", "content": prompt}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }
    async with httpx.AsyncClient() as client:
        res = await client.post("https://integrate.api.nvidia.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=timeout)
        res.raise_for_status()
        return clean_json(res.json()["choices"][0]["message"]["content"])

async def call_groq(prompt: str, system: str, timeout: float) -> Optional[dict]:
    key = os.getenv("GROQ_API_KEY")
    if not key: return None
    payload = {
        "model": "openai/gpt-oss-20b",
        "messages": [{"role": "system", "content": system + "\n\nRETURN JSON ONLY."}, {"role": "user", "content": prompt}],
        "temperature": 0.3,
        "response_format": {"type": "json_object"}
    }
    async with httpx.AsyncClient() as client:
        res = await client.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json=payload, timeout=timeout)
        res.raise_for_status()
        return clean_json(res.json()["choices"][0]["message"]["content"])

async def call_gemini(prompt: str, system: str, timeout: float) -> Optional[dict]:
    key = os.getenv("GEMINI_API_KEY")
    if not key: return None
    payload = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"}
    }
    async with httpx.AsyncClient() as client:
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent"
        res = await client.post(url, headers={"x-goog-api-key": key}, json=payload, timeout=timeout)
        res.raise_for_status()
        return clean_json(res.json()["candidates"][0]["content"]["parts"][0]["text"])

async def call_local(prompt: str, system: str, deadline: float = None) -> Optional[dict]:
    model = get_local_model()
    if not model: return None
    
    def run_inference():
        kwargs = {
            "messages": [{"role": "system", "content": system + "\n\nRETURN JSON ONLY."}, {"role": "user", "content": prompt}],
            "temperature": 0.2,
            "max_tokens": LOCAL_MAX_TOKENS,
            "stream": True,
        }
        if JSON_GRAMMAR:
            kwargs["grammar"] = JSON_GRAMMAR
        else:
            kwargs["response_format"] = {"type": "json_object"}
            
        res_text = ""
        try:
            for chunk in model.create_chat_completion(**kwargs):
                if deadline and time.time() > deadline:
                    logger.warning("Local tier exceeded deadline mid-generation. Aborting thread.")
                    return None
                delta = chunk["choices"][0].get("delta", {})
                if "content" in delta and delta["content"]:
                    res_text += delta["content"]
        except Exception as e:
            logger.warning(f"Local stream aborted: {e}")
            return None
        return res_text
        
    loop = asyncio.get_event_loop()
    text = await loop.run_in_executor(None, run_inference)
    if not text: return None
    return clean_json(text)
