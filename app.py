import os
import json
import logging
import asyncio
import time
import re
import random
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, Request
from pydantic import BaseModel
import httpx
from dotenv import load_dotenv

load_dotenv()

# Vera Engine - Autonomous 5-Tier Reliability Build
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VeraEngine")

app = FastAPI()

# --- Pydantic Schemas (Elastic) ---
class ContextPayload(BaseModel):
    scope: Optional[str] = None
    context_id: Optional[str] = None
    version: Optional[int] = None
    payload: Dict[Any, Any] = {}

class TickRequest(BaseModel):
    available_triggers: List[str] = []

# --- Key Rotation Logic ---
class KeyRotator:
    def __init__(self, provider: str):
        self.provider = provider
        self.keys = []
        # Scan for PROVIDER_KEY_1, PROVIDER_KEY_2, etc.
        for i in range(1, 11):
            key = os.getenv(f"{provider.upper()}_KEY_{i}")
            if key: self.keys.append(key)
        # Fallback to generic PROVIDER_API_KEY
        if not self.keys:
            key = os.getenv(f"{provider.upper()}_API_KEY")
            if key: self.keys.append(key)
        
        self.index = 0
        self.lock = asyncio.Lock()

    async def get_key(self) -> Optional[str]:
        if not self.keys: return None
        async with self.lock:
            key = self.keys[self.index]
            return key

    async def rotate(self):
        async with self.lock:
            if self.keys:
                self.index = (self.index + 1) % len(self.keys)
                logger.info(f"Rotated key for {self.provider}. New index: {self.index}")

# Initialize Rotators
rotators = {
    "openrouter": KeyRotator("openrouter"),
    "gemini": KeyRotator("gemini"),
    "groq": KeyRotator("groq"),
    "deepseek": KeyRotator("deepseek")
}

contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
llm_semaphore_local = asyncio.Semaphore(1)

PRIORITY_MAP = {
    "drop_in_orders": 100, "revenue_drop": 95, "regulation_change": 90,
    "recall_due": 80, "high_churn": 70, "competitor_action": 65, "perf_spike": 60
}

# --- Hierarchical Inference Engine ---
async def call_llm_chain(prompt: str, system: str = "") -> Optional[Dict]:
    json_suffix = "\n\nRETURN JSON ONLY: {\"body\": \"...\", \"cta\": \"...\", \"rationale\": \"...\"}"
    full_system = system + json_suffix

    # Tier 1: OpenRouter
    res = await call_tier_1_openrouter(prompt, full_system)
    if res: return res

    # Tier 2: Gemini REST
    res = await call_tier_2_gemini(prompt, full_system)
    if res: return res

    # Tier 3: Groq
    res = await call_tier_3_groq(prompt, full_system)
    if res: return res

    # Tier 4: DeepSeek
    res = await call_tier_4_deepseek(prompt, full_system)
    if res: return res

    # Tier 5: Local Fallback
    res = await call_tier_5_local(prompt, system) # Local has own prompt format
    return res

async def call_tier_1_openrouter(prompt: str, system: str) -> Optional[Dict]:
    rot = rotators["openrouter"]
    key = await rot.get_key()
    if not key: return None
    
    models = ["poolside/laguna-m.1:free", "tencent/hy3:free", "google/gemini-2.0-flash-exp:free"]
    async with httpx.AsyncClient() as client:
        for model in models:
            try:
                res = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {key}",
                        "HTTP-Referer": "https://huggingface.co/spaces",
                        "X-Title": "Vera Engine Platinum"
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    },
                    timeout=7.0
                )
                if res.status_code == 200:
                    return json.loads(res.json()["choices"][0]["message"]["content"])
                if res.status_code in [401, 429]: await rot.rotate()
            except: continue
    return None

async def call_tier_2_gemini(prompt: str, system: str) -> Optional[Dict]:
    rot = rotators["gemini"]
    key = await rot.get_key()
    if not key: return None
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash-exp:generateContent?key={key}"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post(url, json={
                "contents": [{"parts": [{"text": f"System: {system}\n\nUser: {prompt}"}]}]
            }, timeout=7.0)
            if res.status_code == 200:
                text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                # Clean potential markdown
                text = re.sub(r'```json\n?|\n?```', '', text).strip()
                return json.loads(text)
            if res.status_code in [401, 429]: await rot.rotate()
        except: pass
    return None

async def call_tier_3_groq(prompt: str, system: str) -> Optional[Dict]:
    rot = rotators["groq"]
    key = await rot.get_key()
    if not key: return None
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post("https://api.groq.com/openai/v1/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }, timeout=7.0)
            if res.status_code == 200:
                return json.loads(res.json()["choices"][0]["message"]["content"])
            if res.status_code in [401, 429]: await rot.rotate()
        except: pass
    return None

async def call_tier_4_deepseek(prompt: str, system: str) -> Optional[Dict]:
    rot = rotators["deepseek"]
    key = await rot.get_key()
    if not key: return None
    async with httpx.AsyncClient() as client:
        try:
            res = await client.post("https://api.deepseek.com/chat/completions",
                headers={"Authorization": f"Bearer {key}"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                    "response_format": {"type": "json_object"}
                }, timeout=7.0)
            if res.status_code == 200:
                return json.loads(res.json()["choices"][0]["message"]["content"])
            if res.status_code in [401, 429]: await rot.rotate()
        except: pass
    return None

async def call_tier_5_local(prompt: str, system: str) -> Optional[Dict]:
    async with llm_semaphore_local:
        logger.info("Local Fallback: Llama 3.2 (3B)")
        payload = {
            "model": "llama3.2",
            "prompt": f"System: {system}\nStrict Grounding. No Fabrication. Context: {prompt}\nUser: Return JSON message.",
            "stream": False,
            "format": "json",
            "options": {"num_predict": 80, "temperature": 0.1}
        }
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=90.0)
                if response.status_code == 200:
                    return json.loads(response.json().get('response', '{}'))
            except Exception as e:
                logger.error(f"Local Model Error: {e}")
                return None

# --- Utilities ---
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
    
    primary_metric = list(m.items())[0] if m else None
    verbatim_source = str(payload)[:150] if payload else None
    
    evidence_block = ""
    if primary_metric:
        evidence_block += f"MANDATORY METRIC: '{primary_metric[0]}' is {primary_metric[1]}. "
    if verbatim_source:
        evidence_block += f"MANDATORY CITATION: '{verbatim_source}'. "

    beats = category.get("seasonal_beats", [])
    trends = category.get("trend_signals", [])
    knowledge_anchor = ""
    if beats: knowledge_anchor = f"INDUSTRY CONTEXT: {beats[0].get('note', '')}. "
    elif trends: knowledge_anchor = f"MARKET TREND: {trends[0].get('note', '')}. "

    sys_prompt = f"""Role: Senior Growth Strategist. Target: {prefix} {owner_name} in {ident.get('locality')}.
GOAL: Act as a peer partner. Help the merchant grow using facts.
RULES:
1. EVIDENCE: {evidence_block or 'Use a curiosity hook about local business growth.'}
2. CONTEXT: {knowledge_anchor}Use this as the catalyst for the conversation.
3. NO FABRICATION: Do not invent numbers. If no metric, focus on the industry context.
4. TONE: {hinglish_note} Professional, high-empathy, peer-to-peer.
5. LIMIT: 280-310 characters."""

    prompt = f"CONTEXT: {json.dumps({'merchant': ident, 'trigger': trigger})}"
    
    # Run the 5-tier chain
    res = await call_llm_chain(prompt, system=sys_prompt)
    
    if not res:
        body = f"{prefix} {owner_name}, noticed update in {ident.get('locality')}. Potential growth opportunity found. Review?"
        res = {"body": body, "cta": "Reply YES", "rationale": "Hard Fallback"}
    
    res["body"] = prune_message(res.get("body", ""))
    return res

# --- Endpoints ---
@app.on_event("startup")
async def startup_event():
    logger.info("Performing Multi-Tier API Connectivity Audit...")
    for name, rot in rotators.items():
        key = await rot.get_key()
        status = "FOUND" if key else "MISSING"
        logger.info(f"Provider {name}: {status} ({len(rot.keys)} keys loaded)")

@app.get("/v1/healthz")
async def healthz():
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("http://127.0.0.1:11434/api/tags")
            if "llama3.2" in res.text: return {"status": "ok"}
        except: pass
    return {"status": "starting"}

@app.get("/v1/metadata")
async def metadata():
    model_status = "unready"
    async with httpx.AsyncClient() as client:
        try:
            res = await client.get("http://127.0.0.1:11434/api/tags")
            if "llama3.2" in res.text: model_status = "ready"
        except: pass
    return {
        "team_name": "Vera Lead Solver", 
        "version": "5.0",
        "engine": "5-Tier-Hierarchical-Engine",
        "local_model": model_status
    }

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = data.payload
    return {"accepted": True}

@app.post("/v1/tick")
async def tick(req: TickRequest):
    tids = sorted(req.available_triggers, key=lambda t: PRIORITY_MAP.get(contexts["trigger"].get(t, {}).get("kind"), 0), reverse=True)
    results = []
    for tid in tids[:1]: 
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

AUTO_REPLY_PATTERNS = [
    r"thank you for contacting", r"we are currently away", r"this is an automated message",
    r"business hours", r"get back to you shortly", r"auto-reply", r"canned response"
]

HOSTILE_PATTERNS = [
    r"stop", r"spam", r"useless", r"abuse", r"reporting", r"don't message", r"remove me"
]

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    msg = req.get("message", "").lower()
    for pattern in HOSTILE_PATTERNS:
        if re.search(pattern, msg):
            return {"action": "end", "rationale": f"Hostility: {pattern}"}
    for pattern in AUTO_REPLY_PATTERNS:
        if re.search(pattern, msg):
            return {"action": "wait", "wait_seconds": 3600, "rationale": "Auto-reply"}

    prompt = f"Merchant message: {req.get('message', '')}. Turn: {req.get('turn_number')}. History: {req.get('history', [])}"
    sys = """Role: Vera AI. If merchant says 'ok/yes/do it', provide EXACT next step action. No more qualifying questions."""
    res = await call_llm_chain(prompt, system=sys)
    
    reply_body = res.get("body", "I'm on it. Setting that up for you now. Ready to proceed?") if res else "Understood. I'll get that started. Ready?"
    return {"action": "send", "body": reply_body, "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8086)))
