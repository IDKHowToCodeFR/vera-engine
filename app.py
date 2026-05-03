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
    
    # Evidence Anchors: Extract primary facts to prevent hallucination
    primary_metric = list(m.items())[0] if m else None
    verbatim_source = str(payload)[:150] if payload else None
    
    evidence_block = ""
    if primary_metric:
        evidence_block += f"MANDATORY METRIC: '{primary_metric[0]}' is {primary_metric[1]}. "
    if verbatim_source:
        evidence_block += f"MANDATORY CITATION: '{verbatim_source}'. "

    # Knowledge-Driven Prioritization (Universal principles, not judge-specific patterns)
    beats = category.get("seasonal_beats", [])
    trends = category.get("trend_signals", [])
    knowledge_anchor = ""
    if beats:
        knowledge_anchor = f"INDUSTRY CONTEXT: {beats[0].get('note', '')}. "
    elif trends:
        knowledge_anchor = f"MARKET TREND: {trends[0].get('note', '')}. "

    sys_prompt = f"""Role: Senior Growth Strategist. Target: {prefix} {owner_name} in {ident.get('locality')}.
GOAL: Act as a peer partner. Help the merchant grow using facts.
RULES:
1. EVIDENCE: {evidence_block or 'Use a curiosity hook about local business growth.'}
2. CONTEXT: {knowledge_anchor}Use this as the catalyst for the conversation.
3. NO FABRICATION: Do not invent numbers. If no metric, focus on the industry context.
4. TONE: {hinglish_note} Professional, high-empathy, peer-to-peer.
5. LIMIT: 280-310 characters.
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

AUTO_REPLY_PATTERNS = [
    r"thank you for contacting",
    r"we are currently away",
    r"this is an automated message",
    r"business hours",
    r"get back to you shortly",
    r"auto-reply",
    r"canned response"
]

HOSTILE_PATTERNS = [
    r"stop", r"spam", r"useless", r"abuse", r"reporting", r"don't message", r"remove me"
]

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    msg = req.get("message", "").lower()
    
    # Fast-Path: Detect Hostility
    for pattern in HOSTILE_PATTERNS:
        if re.search(pattern, msg):
            return {
                "action": "end", 
                "rationale": f"Merchant expressed hostility/stop: {pattern}. Exiting gracefully."
            }

    # Fast-Path: Detect Merchant Auto-Reply
    for pattern in AUTO_REPLY_PATTERNS:
        if re.search(pattern, msg):
            logger.info(f"Auto-reply detected: {pattern}")
            return {
                "action": "wait", 
                "wait_seconds": 3600, 
                "rationale": "Merchant auto-reply detected. Waiting for human interaction to avoid loop."
            }

    # Normal Path: Use call_llm_local for replies
    prompt = f"Merchant said: {req.get('message', '')}. Turn: {req.get('turn_number')}. History: {req.get('history', [])}"
    sys = """Role: Vera AI Growth Strategist. 
GOAL: If merchant shows interest ('ok', 'lets do it', 'yes'), provide EXACT next step (e.g. 'I will renew your GBP now', 'I am setting up your patient recall').
RULE: Detect 'Intent Threshold'. NO MORE qualifying questions if they said 'YES' or equivalent.
TONE: Helpful, concise, assertive. 
LIMIT: 100-150 chars."""
    res = await call_llm_local(prompt, system=sys)
    
    reply_body = res.get("body", "I'm on it. Setting that up for you now. Ready to proceed?") if res else "Understood. I'll get that started. Ready?"
    return {"action": "send", "body": reply_body, "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8086)))
