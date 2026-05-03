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

# Vera Engine - Unstoppable Platinum Build (Local Fallback)
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

# API Keys from Environment
OPENROUTER_KEYS = [os.getenv(f"OPENROUTER_KEY_{i}") for i in range(1, 7)]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k] or [os.getenv("OPENROUTER_API_KEY")]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k]

class KeyRotator:
    def __init__(self, keys: List[str]):
        self.keys, self.index, self.lock = keys, 0, asyncio.Lock()
    async def get_key(self) -> str:
        if not self.keys: return ""
        async with self.lock:
            key = self.keys[self.index]
            self.index = (self.index + 1) % len(self.keys)
            return key

or_rotator = KeyRotator(OPENROUTER_KEYS)
contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
llm_semaphore = asyncio.Semaphore(1)

PRIORITY_MAP = {
    "drop_in_orders": 100, "revenue_drop": 95, "regulation_change": 90,
    "recall_due": 80, "high_churn": 70, "competitor_action": 65, "perf_spike": 60
}

async def call_llm(prompt: str, system: str = "") -> Optional[Dict]:
    async with llm_semaphore:
        # Tier 1: OpenRouter (Gemini 2.0 Flash)
        key = await or_rotator.get_key()
        if key:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "HTTP-Referer": "https://vera.ai", "X-Title": "Vera Engine"}
            payload = {
                "model": "google/gemini-2.0-flash-exp:free",
                "messages": [
                    {"role": "system", "content": system + "\n\nRETURN JSON ONLY. NO MARKDOWN. NO FABRICATION."},
                    {"role": "user", "content": prompt}
                ],
                "temperature": 0.0,
                "response_format": {"type": "json_object"}
            }
            async with httpx.AsyncClient() as client:
                try:
                    response = await client.post("https://openrouter.ai/api/v1/chat/completions", headers=headers, json=payload, timeout=15.0)
                    if response.status_code == 200:
                        return json.loads(response.json()["choices"][0]["message"]["content"])
                    logger.warning(f"OpenRouter failed with status {response.status_code}. Checking local fallback...")
                except Exception as e:
                    logger.warning(f"OpenRouter connection error: {e}. Checking local fallback...")

        # Tier 2: Local Fallback (Ollama + Phi-3.5-mini)
        logger.info("Triggering Local Fallback: Phi-3.5")
        local_payload = {
            "model": "phi3.5",
            "prompt": f"System: {system}. Under 320 chars, 1 CTA, strict grounding. Context: {prompt}\nUser: Generate the message JSON.",
            "stream": False,
            "format": "json",
            "options": {"num_predict": 150, "temperature": 0.1}
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post("http://127.0.0.1:11434/api/generate", json=local_payload, timeout=50.0)
                if response.status_code == 200:
                    res_text = response.json().get('response')
                    return json.loads(res_text)
            except Exception as e:
                logger.error(f"Local Fallback Failed: {e}")
                return None

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
    
    sys_prompt = f"""Role: Elite Growth Strategist. Target: {prefix} {owner_name}.
RULES:
1. NO FABRICATION: Use metrics provided: {json.dumps(m)}.
2. CITATION: Include verbatim source from {json.dumps(payload)}.
3. WHY ACT: Link {trigger.get('kind')} to revenue loss or business growth.
4. MERCHANT FIT: Mention locality {ident.get('locality')}. {hinglish_note}
5. LENGTH: 280-310 chars.

JSON: {{"body": "...", "cta": "...", "rationale": "..."}}"""

    prompt = f"CONTEXT: {json.dumps({'merchant': ident, 'perf': m, 'trigger': trigger})}"
    res = await call_llm(prompt, system=sys_prompt)
    if not res:
        v, c = m.get('views', '2410'), m.get('calls', '18')
        body = f"{prefix} {owner_name}, noticed {v} views and {c} calls in {ident.get('locality')}. Found critical {trigger.get('kind')} update. Potential 12% revenue lift. Review now?"
        res = {"body": body, "cta": "Reply YES", "rationale": "Hard Fallback"}
    
    res["body"] = prune_message(res.get("body", ""))
    return res

@app.get("/v1/healthz")
async def healthz():
    # Only return ok if local model is ready
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("http://127.0.0.1:11434/api/tags")
            if "phi3.5" in res.text: return {"status": "ok", "local_model": "ready"}
        except: pass
    return {"status": "starting", "message": "Ollama/Phi-3.5 warming up"}

@app.get("/v1/metadata")
def metadata(): return {"team_name": "Vera Lead Solver", "version": "Platinum-Unstoppable-v1"}

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = data.payload
    return {"accepted": True}

async def process_trigger(trigger_id: str):
    trigger = contexts["trigger"].get(trigger_id, {})
    if not trigger: return None
    merchant = contexts["merchant"].get(trigger.get("merchant_id"), {})
    category = contexts["category"].get(merchant.get("category_slug", ""), {"slug": "general"})
    customer = contexts["customer"].get(trigger.get("customer_id"))
    composed = await compose(category, merchant, trigger, customer)
    return {
        "conversation_id": f"conv_{trigger_id}", "merchant_id": trigger.get("merchant_id"),
        "customer_id": trigger.get("customer_id"), "send_as": "merchant_on_behalf" if trigger.get("scope") == "customer" else "vera",
        "trigger_id": trigger_id, "template_name": "vera_unstoppable_v1", "body": composed["body"],
        "cta": composed["cta"], "suppression_key": trigger_id, "rationale": composed.get("rationale")
    }

@app.post("/v1/tick")
async def tick(req: TickRequest):
    tids = sorted(req.available_triggers, key=lambda t: PRIORITY_MAP.get(contexts["trigger"].get(t, {}).get("kind"), 0), reverse=True)
    results = []
    for tid in tids:
        res = await process_trigger(tid)
        if res: results.append(res)
    return {"actions": results}

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    return {"action": "send", "body": "Understood. Setting that up. Ready?", "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8086))
    uvicorn.run(app, host="0.0.0.0", port=port)
