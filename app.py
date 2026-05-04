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

# Vera Engine - High-Intelligence Model Rotation Pool (v8.0)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VeraArchitect")

app = FastAPI()

# --- 1. Infrastructure & Elasticity ---
class ContextPayload(BaseModel):
    scope: Optional[str] = None
    context_id: Optional[str] = None
    version: Optional[int] = None
    payload: Dict[Any, Any] = {}

class TickRequest(BaseModel):
    available_triggers: List[str] = []

# --- 2. Scalable Multi-Agent Registry ---
class Agent:
    def __init__(self, name: str, provider: str, model: str, tier: int):
        self.name = name
        self.provider = provider
        self.model = model
        self.tier = tier
        self.keys = self._load_keys()
        self.key_index = 0
        self.is_healthy = True
        self.cooldown_until = 0

    def _load_keys(self) -> List[str]:
        keys = []
        for i in range(1, 11):
            key = os.getenv(f"{self.provider.upper()}_KEY_{i}")
            if key: keys.append(key)
        if not keys:
            key = os.getenv(f"{self.provider.upper()}_API_KEY")
            if key: keys.append(key)
        return keys

    async def get_key(self) -> Optional[str]:
        if not self.keys: return None
        return self.keys[self.key_index]

    def rotate_key(self):
        if self.keys:
            self.key_index = (self.key_index + 1) % len(self.keys)
            logger.info(f"Agent {self.name} rotated key to index {self.key_index}")

    def mark_unhealthy(self, duration: int = 60):
        self.is_healthy = False
        self.cooldown_until = time.time() + duration
        logger.warning(f"Agent {self.name} marked unhealthy for {duration}s")

    def check_health(self):
        if not self.is_healthy and time.time() > self.cooldown_until:
            self.is_healthy = True
        return self.is_healthy and len(self.keys) > 0

class LocalAgent(Agent):
    def __init__(self):
        super().__init__("LocalOllama", "ollama", "llama3.2", 5)
        self.keys = ["local"]
    def check_health(self): return True

# Initialize High-Intelligence Registry
AGENT_REGISTRY: List[Agent] = [
    # Tier 1: Cloud Speed
    Agent("Cloud-OpenRouter-Laguna", "openrouter", "poolside/laguna-m.1:free", 1),
    Agent("Cloud-OpenRouter-Hy3", "openrouter", "tencent/hy3:free", 1),
    
    # Tier 2: Intelligence Pool (Sequential Rotation)
    Agent("Cloud-Gemini-3-Lead", "gemini", "gemini-3-flash", 2),
    Agent("Cloud-Gemini-2.5-Stable", "gemini", "gemini-2.5-flash", 2),
    Agent("Cloud-Gemini-2.5-Lite", "gemini", "gemini-2.5-flash-lite", 2),
    Agent("Cloud-Gemma-4-Reasoning", "gemini", "gemma-4-31b-it", 2),
    
    # Tier 3: Throughput
    Agent("Cloud-Groq-Llama", "groq", "llama-3.3-70b-versatile", 3),
    
    # Tier 4: Fallback
    Agent("Cloud-DeepSeek-Chat", "deepseek", "deepseek-chat", 4),
    
    # Tier 5: Local
    LocalAgent()
]

contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
llm_semaphore_local = asyncio.Semaphore(1)

# --- 3. Orchestration Logic ---
async def call_llm_chain(prompt: str, system: str = "") -> Optional[Dict]:
    json_suffix = "\n\nRETURN JSON ONLY: {\"body\": \"...\", \"cta\": \"...\", \"rationale\": \"...\"}"
    full_system = system + json_suffix

    for tier in range(1, 6):
        tier_agents = [a for a in AGENT_REGISTRY if a.tier == tier and a.check_health()]
        for agent in tier_agents:
            res = await execute_agent(agent, prompt, full_system if agent.tier < 5 else system)
            if res: return res
    return None

async def execute_agent(agent: Agent, prompt: str, system: str) -> Optional[Dict]:
    if agent.provider == "ollama": return await call_local_agent(agent, prompt, system)
    key = await agent.get_key()
    if not key: return None

    async with httpx.AsyncClient() as client:
        try:
            if agent.provider == "openrouter":
                res = await client.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://vera.ai", "X-Title": "Vera Platinum"},
                    json={"model": agent.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}, timeout=7.0)
            elif agent.provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{agent.model}:generateContent?key={key}"
                res = await client.post(url, json={"contents": [{"parts": [{"text": f"System: {system}\n\nUser: {prompt}"}]}]}, timeout=7.0)
            elif agent.provider == "groq":
                res = await client.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": agent.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}, timeout=7.0)
            elif agent.provider == "deepseek":
                res = await client.post("https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={"model": agent.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}], "response_format": {"type": "json_object"}}, timeout=7.0)

            if res.status_code == 200:
                if agent.provider == "gemini":
                    text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    text = re.sub(r'```json\n?|\n?```', '', text).strip()
                    return json.loads(text)
                return json.loads(res.json()["choices"][0]["message"]["content"])
            if res.status_code in [401, 429]: agent.rotate_key()
            else: agent.mark_unhealthy()
        except: pass
    return None

async def call_local_agent(agent: Agent, prompt: str, system: str) -> Optional[Dict]:
    async with llm_semaphore_local:
        payload = {"model": agent.model, "prompt": f"System: {system}\nContext: {prompt}\nUser: Return JSON message.", "stream": False, "format": "json", "options": {"num_predict": 80, "temperature": 0.1}}
        async with httpx.AsyncClient() as client:
            try:
                res = await client.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=90.0)
                if res.status_code == 200: return json.loads(res.json().get('response', '{}'))
            except: return None

# --- 4. Core Logic ---
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
    evidence_block = f"MANDATORY METRIC: '{primary_metric[0]}' is {primary_metric[1]}. MANDATORY CITATION: '{str(payload)[:150]}'." if primary_metric else "Use curiosity hook."

    sys_prompt = f"""Role: Elite Growth Strategist. Target: {prefix} {owner_name} in {ident.get('locality')}.
Objective: WhatsApp growth message.
RULES: 1. TRIGGER PRIMACY: Address {trigger.get('kind')}. 2. NO FABRICATION. {evidence_block} 3. TONE: {hinglish_note} 4. LIMIT: 280-310 chars."""
    prompt = f"CONTEXT: {json.dumps({'merchant': ident, 'trigger': trigger})}"
    res = await call_llm_chain(prompt, system=sys_prompt)
    if not res:
        res = {"body": f"{prefix} {owner_name}, noticed update in {ident.get('locality')}. Review growth opportunity now?", "cta": "Reply YES", "rationale": "Hard Fallback"}
    res["body"] = prune_message(res.get("body", ""))
    return res

# --- 5. Endpoints ---
@app.get("/v1/healthz")
async def healthz(): return {"status": "ok"}

@app.get("/v1/metadata")
async def metadata(): return {"team_name": "Vera Lead Solver", "version": "8.0", "engine": "High-Intelligence-Registry"}

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = data.payload
    return {"accepted": True}

@app.post("/v1/tick")
async def tick(req: TickRequest):
    tids = sorted(req.available_triggers, key=lambda t: contexts["trigger"].get(t, {}).get("kind", ""), reverse=True)
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
    customer = contexts["customer"].get(trigger.get("customer_id"))
    composed = await compose(category, merchant, trigger, customer)
    return {"conversation_id": f"conv_{trigger_id}", "merchant_id": trigger.get("merchant_id"), "trigger_id": trigger_id, "body": composed["body"], "cta": composed["cta"]}

AUTO_REPLY_PATTERNS = [r"thank you for contacting", r"we are currently away", r"automated message", r"business hours", r"auto-reply"]
HOSTILE_PATTERNS = [r"stop", r"spam", r"useless", r"abuse"]
INTENT_PATTERNS = [r"\bok\b", r"\byes\b", r"\bdo it\b", r"let'?s do it", r"\bsure\b"]

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    msg, turn = req.get("message", "").lower(), req.get("turn_number", 1)
    for p in HOSTILE_PATTERNS:
        if re.search(p, msg): return {"action": "end", "rationale": "Hostility."}
    for p in AUTO_REPLY_PATTERNS:
        if re.search(p, msg):
            if turn > 2: return {"action": "end", "rationale": "Repeated auto-reply."}
            return {"action": "wait", "wait_seconds": 3600, "rationale": "Auto-reply wait."}
    for p in INTENT_PATTERNS:
        if re.search(p, msg):
            res = await call_llm_chain(f"Merchant said: {msg}", system="Role: Vera AI. Interest detected. Provide EXACT next step action. 15 words max.")
            return {"action": "send", "body": res.get("body", "I'm setting that up for you now.") if res else "I'm setting that up now.", "cta": "Reply YES"}

    res = await call_llm_chain(f"Merchant: {msg}", system="Role: Vera AI. Growth Strategist. Be concise.")
    return {"action": "send", "body": res.get("body", "Understood. Proceed?") if res else "Understood. Proceed?", "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
