import os
import json
import logging
import asyncio
import time
import re
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()

# Vera Engine - Autonomous Local-First Build
# Priority: Ollama (SmollM2-1.7B) -> Fallback: OpenRouter
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VeraEngine")

app = FastAPI()

class ContextPayload(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[Any, Any]

class TickRequest(BaseModel):
    available_triggers: List[str]

# API Keys (Optional Fallback)
OPENROUTER_KEYS = [os.getenv(f"OPENROUTER_KEY_{i}") for i in range(1, 7)]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k] or [os.getenv("OPENROUTER_API_KEY")]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k]

contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
llm_semaphore_local = asyncio.Semaphore(1) # Strict 1 for CPU stability

PRIORITY_MAP = {
    "drop_in_orders": 100, "revenue_drop": 95, "regulation_change": 90,
    "recall_due": 80, "high_churn": 70, "competitor_action": 65, "perf_spike": 60
}

async def call_llm_local(prompt: str, system: str = "") -> Optional[Dict]:
    async with llm_semaphore_local:
        logger.info("Local Inference: SmollM2-1.7B")
        payload = {
            "model": "smollm2:1.7b",
            "prompt": f"System: {system}\nStrict Grounding. No Fabrication. Context: {prompt}\nUser: Return JSON message.",
            "stream": False,
            "format": "json",
            "options": {"num_predict": 120, "temperature": 0.1}
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=25.0)
                if response.status_code == 200:
                    return json.loads(response.json().get('response', '{}'))
            except Exception as e:
                logger.error(f"Local Model Error: {e}")
                return None

async def call_llm_api(prompt: str, system: str = "") -> Optional[Dict]:
    if not OPENROUTER_KEYS: return None
    key = OPENROUTER_KEYS[0] # Simple use for fallback
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    payload = {
        "model": "google/gemini-2.0-flash-exp:free",
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"}
    }
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=10.0)
            return json.loads(res.json()["choices"][0]["message"]["content"])
        except: return None

def prune_message(text: str) -> str:
    text = text.replace("\n", " ").strip()
    if len(text) <= 315: return text
    match = re.findall(r'.*?[.!?]', text)
    res = ""
    for m in match:
        if len(res) + len(m) <= 312: res += m
        else: break
    return res if res else text[:309] + "..."

async def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> dict:
    ident, perf = merchant.get("identity", {}), merchant.get("performance", {})
    owner_name = ident.get("owner_first_name", "Partner")
    m = {k: v for k, v in perf.items() if v and v != "0" and v != 0 and v != "?"}
    payload = trigger.get("payload", {})
    prefix = "Dr." if category.get('slug') == 'dentists' else ""
    lang_pref = ident.get('languages', ['en'])
    hinglish_note = "USE NATURAL HINGLISH (50% English words, 50% Hindi script/transliteration)." if 'hi' in lang_pref else "USE PROFESSIONAL ENGLISH."
    
    grounding = f"Metrics: {json.dumps(m)}. Source: {json.dumps(payload)}." if m else "No metrics. Use curiosity hook."
    sys_prompt = f"""Role: Growth Strategist. Target: {prefix} {owner_name}.
RULES: 1. NO FABRICATION. {grounding} 2. CITATION required. 3. Locality {ident.get('locality')}. {hinglish_note} 4. 280-310 chars.
JSON: {{"body": "...", "cta": "...", "rationale": "..."}}"""

    prompt = f"CONTEXT: {json.dumps({'merchant': ident, 'trigger': trigger})}"
    
    # LOCAL FIRST
    res = await call_llm_local(prompt, system=sys_prompt)
    if not res:
        logger.info("Local failed, trying API fallback...")
        res = await call_llm_api(prompt, system=sys_prompt)
    
    if not res:
        body = f"{prefix} {owner_name}, noticed update in {ident.get('locality')}. Potential growth opportunity found. Review?"
        res = {"body": body, "cta": "Reply YES", "rationale": "Hard Fallback"}
    
    res["body"] = prune_message(res.get("body", ""))
    return res

@app.get("/v1/healthz")
async def healthz():
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("http://127.0.0.1:11434/api/tags")
            if "smollm2:1.7b" in res.text: return {"status": "ok", "local_model": "ready"}
        except: pass
    return {"status": "starting", "message": "Ollama/SmollM2 warming up"}

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = data.payload
    return {"accepted": True}

@app.post("/v1/tick")
async def tick(req: TickRequest):
    tids = sorted(req.available_triggers, key=lambda t: PRIORITY_MAP.get(contexts["trigger"].get(t, {}).get("kind"), 0), reverse=True)
    results = []
    # Local inference is sequential for CPU safety
    for tid in tids[:2]: 
        res = await process_trigger(tid)
        if res: results.append(res)
    return {"actions": results}

async def process_trigger(trigger_id: str):
    trigger = contexts["trigger"].get(trigger_id, {})
    if not trigger: return None
    merchant = contexts["merchant"].get(trigger.get("merchant_id"), {})
    category = contexts["category"].get(merchant.get("category_slug", ""), {"slug": "general"})
    composed = await compose(category, merchant, trigger)
    return {
        "conversation_id": f"conv_{trigger_id}", "merchant_id": trigger.get("merchant_id"),
        "trigger_id": trigger_id, "body": composed["body"], "cta": composed["cta"]
    }

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    return {"action": "send", "body": "Understood. Proceed?", "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8086)))
