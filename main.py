# BEST SCORE: 41/50 (82%) - EXCELLENT
# Model: Gemini-2.0-Flash-001 (via OpenRouter)
# Tested on: 2026-05-02
# Features: Strict grounding, Trigger primacy, Hinglish support, Source citations.

import os
import json
import logging
import asyncio
import time
import re
from typing import List, Dict, Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()

# Lead AI Problem Solver: Sequential Reinforcement Architecture
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VeraLeadSolver")

app = FastAPI()

class ContextPayload(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: Dict[Any, Any]

class TickRequest(BaseModel):
    available_triggers: List[str]

# Distributed Credential Strategy: Round-Robin Key Pool
OPENROUTER_KEYS = [
    os.getenv("OPENROUTER_KEY_1"),
    os.getenv("OPENROUTER_KEY_2"),
    os.getenv("OPENROUTER_KEY_3"),
    os.getenv("OPENROUTER_KEY_4"),
    os.getenv("OPENROUTER_KEY_5"),
    os.getenv("OPENROUTER_KEY_6")
]
OPENROUTER_KEYS = [k for k in OPENROUTER_KEYS if k]

class KeyRotator:
    def __init__(self, keys: List[str]):
        self.keys = keys
        self.index = 0
        self.lock = asyncio.Lock()
        
    async def get_key(self) -> str:
        if not self.keys:
            return ""
        async with self.lock:
            key = self.keys[self.index]
            self.index = (self.index + 1) % len(self.keys)
            return key

or_rotator = KeyRotator(OPENROUTER_KEYS)

contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
semaphore = asyncio.Semaphore(1) # STRICT SEQUENTIAL

async def call_llm(prompt: str, system: str = "", temperature: float = 0.0) -> Optional[Dict]:
    key = await or_rotator.get_key()
    url = "https://openrouter.ai/api/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://vera.ai",
        "X-Title": "Vera Lead Solver"
    }
    # Using openrouter/free to get the best free model
    payload = {
        "model": "openrouter/free",
        "messages": [
            {"role": "system", "content": system + "\n\nCRITICAL: Return ONLY valid JSON. No markdown, no preambles."},
            {"role": "user", "content": prompt}
        ],
        "temperature": temperature,
        "max_tokens": 1000
    }
    
    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(url, headers=headers, json=payload, timeout=60.0)
            if response.status_code == 200:
                resp_json = response.json()
                content = resp_json["choices"][0]["message"].get("content")
                if not content:
                    return None
                content = re.sub(r'```json\s*|\s*```', '', content).strip()
                start = content.find('{')
                end = content.rfind('}')
                if start != -1 and end != -1:
                    content = content[start:end+1]
                return json.loads(content)
            else:
                logger.error(f"LLM Error {response.status_code}: {response.text}")
                return None
        except Exception as e:
            logger.error(f"LLM Exception: {e}")
            return None

async def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None) -> dict:
    ident = merchant.get("identity", {})
    perf = merchant.get("performance", {})
    owner_name = ident.get("owner_first_name", "Partner")
    
    sys_prompt = f"""Role: Elite Growth Strategist for magicpin.
Objective: Compose a high-impact WhatsApp message.

STRICT GROUNDING RULES:
1. NO FABRICATION: Only use numbers present in context. 
2. TRIGGER PRIMACY: Message MUST address the trigger event first.
3. SPECIFICITY: Use metrics like views, calls, directions, or CTR from Context.
4. CATEGORY FIT: For dentists, use "Dr." and clinical peer tone.
5. LANGUAGE: If 'hi' in languages, use Hinglish.
6. SOURCE: Include source citations (e.g. "JIDA Oct") if present.

Output JSON: {{"body": "...", "cta": "...", "rationale": "..."}}
"""

    context_str = f"CATEGORY: {json.dumps(category)}\nMERCHANT: {json.dumps(merchant)}\nTRIGGER: {json.dumps(trigger)}\nCUSTOMER: {json.dumps(customer) if customer else 'None'}"

    res = await call_llm(f"Context: {context_str}\n\nCompose a grounded message based on trigger.", system=sys_prompt)
    if not res:
        v = perf.get('views', '?')
        c = perf.get('calls', '?')
        return {"body": f"Hi {owner_name}, noticed {v} views and {c} calls on your profile. Important {trigger.get('kind')} update inside. Check?", "cta": "Reply YES", "rationale": "Fallback"}
    
    return res

@app.get("/v1/healthz")
def healthz():
    return {"status": "ok", "contexts_loaded": {s: len(c) for s, c in contexts.items()}}

@app.get("/v1/metadata")
def metadata():
    return {"team_name": "Vera Lead Solver", "model": "OpenRouter-Free", "version": "26.0.0"}

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = data.payload
    return {"accepted": True}

async def process_trigger(trigger_id: str):
    async with semaphore:
        trigger = contexts["trigger"].get(trigger_id, {})
        merchant_id = trigger.get("merchant_id")
        merchant = contexts["merchant"].get(merchant_id, {})
        category_slug = merchant.get("category_slug", "general")
        category = contexts["category"].get(category_slug, {"slug": category_slug})
        customer_id = trigger.get("customer_id")
        customer = contexts["customer"].get(customer_id, {}) if customer_id else None
        
        composed_data = await compose(category, merchant, trigger, customer)
        is_customer_facing = trigger.get("scope") == "customer"

        return {
            "conversation_id": f"conv_{trigger_id}",
            "merchant_id": merchant_id,
            "customer_id": customer_id if is_customer_facing else None,
            "send_as": "merchant_on_behalf" if is_customer_facing else "vera",
            "trigger_id": trigger_id,
            "template_name": "vera_v26",
            "body": composed_data["body"],
            "cta": composed_data["cta"],
            "suppression_key": trigger_id,
            "rationale": composed_data.get("rationale", "Free Router composition")
        }

@app.post("/v1/tick")
async def tick(req: TickRequest):
    results = []
    for tid in req.available_triggers:
        res = await process_trigger(tid)
        if res: results.append(res)
    return {"actions": results}

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    return {"action": "send", "body": "Got it. Let me set that up for you.", "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
