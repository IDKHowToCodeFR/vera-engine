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

# Vera Engine - Scalable Multi-Agent Reliability Build (v7.0)
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VeraOrchestrator")

app = FastAPI()

# --- 1. Infrastructure & Testing Mode ---
# If FAST_TEST=true, skip cloud tiers for local debugging speed.
FAST_TEST = os.getenv("FAST_TEST", "false").lower() == "true"

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
            logger.info(f"Agent {self.name} is healthy again")
        return self.is_healthy and len(self.keys) > 0

class LocalAgent(Agent):
    def __init__(self):
        super().__init__("LocalOllama", "ollama", "llama3.2", 5)
        self.keys = ["local"] # Placeholder
    def check_health(self): return True

# Initialize Registry
AGENT_REGISTRY: List[Agent] = [
    Agent("Cloud-OpenRouter-Laguna", "openrouter", "poolside/laguna-m.1:free", 1),
    Agent("Cloud-OpenRouter-Hy3", "openrouter", "tencent/hy3:free", 1),
    Agent("Cloud-Gemini-Flash", "gemini", "gemini-2.0-flash-exp", 2),
    Agent("Cloud-Groq-Llama", "groq", "llama-3.3-70b-versatile", 3),
    Agent("Cloud-DeepSeek-Chat", "deepseek", "deepseek-chat", 4),
    LocalAgent()
]

contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
llm_semaphore_local = asyncio.Semaphore(1)

# --- 3. Orchestration Logic ---
async def call_llm_chain(prompt: str, system: str = "") -> Optional[Dict]:
    if FAST_TEST:
        logger.info("FAST_TEST enabled: Skipping cloud tiers.")
        return await call_local_agent(AGENT_REGISTRY[-1], prompt, system)

    json_suffix = "\n\nRETURN JSON ONLY: {\"body\": \"...\", \"cta\": \"...\", \"rationale\": \"...\"}"
    full_system = system + json_suffix

    # Iterate through tiers
    for tier in range(1, 6):
        tier_agents = [a for p, a in enumerate(AGENT_REGISTRY) if a.tier == tier and a.check_health()]
        for agent in tier_agents:
            res = await execute_agent(agent, prompt, full_system if agent.tier < 5 else system)
            if res: return res
    return None

async def execute_agent(agent: Agent, prompt: str, system: str) -> Optional[Dict]:
    if agent.provider == "ollama":
        return await call_local_agent(agent, prompt, system)
    
    key = await agent.get_key()
    if not key: return None

    async with httpx.AsyncClient() as client:
        try:
            if agent.provider == "openrouter":
                res = await client.post("https://openrouter.ai/api/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}", "HTTP-Referer": "https://vera.ai", "X-Title": "Vera Platinum"},
                    json={
                        "model": agent.model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    }, timeout=5.0) # Tightened to 5s for chain speed
            
            elif agent.provider == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{agent.model}:generateContent?key={key}"
                res = await client.post(url, json={"contents": [{"parts": [{"text": f"System: {system}\n\nUser: {prompt}"}]}]}, timeout=5.0)
            
            elif agent.provider == "groq":
                res = await client.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": agent.model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    }, timeout=5.0)

            elif agent.provider == "deepseek":
                res = await client.post("https://api.deepseek.com/chat/completions",
                    headers={"Authorization": f"Bearer {key}"},
                    json={
                        "model": agent.model,
                        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                        "response_format": {"type": "json_object"}
                    }, timeout=5.0)

            if res.status_code == 200:
                if agent.provider == "gemini":
                    text = res.json()["candidates"][0]["content"]["parts"][0]["text"]
                    text = re.sub(r'```json\n?|\n?```', '', text).strip()
                    return json.loads(text)
                return json.loads(res.json()["choices"][0]["message"]["content"])
            
            if res.status_code in [401, 429]:
                agent.rotate_key()
            else:
                agent.mark_unhealthy()
        except Exception:
            pass
    return None

async def call_local_agent(agent: Agent, prompt: str, system: str) -> Optional[Dict]:
    async with llm_semaphore_local:
        logger.info(f"Local Inference: {agent.model}")
        payload = {
            "model": agent.model,
            "prompt": f"System: {system}\nStrict Grounding. No Fabrication. Context: {prompt}\nUser: Return JSON message.",
            "stream": False, "format": "json", "options": {"num_predict": 80, "temperature": 0.1}
        }
        async with httpx.AsyncClient() as client:
            try:
                # 28s here + overhead must be < 30s. If FAST_TEST=true, we skip cloud so we have full 30s.
                res = await client.post("http://127.0.0.1:11434/api/generate", json=payload, timeout=28.0)
                if res.status_code == 200: return json.loads(res.json().get('response', '{}'))
            except Exception as e:
                logger.error(f"Local Model Error: {e}")
                return None

# --- 4. Utilities & Core Logic ---
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
    if primary_metric: evidence_block += f"MANDATORY METRIC: '{primary_metric[0]}' is {primary_metric[1]}. "
    if verbatim_source: evidence_block += f"MANDATORY CITATION: '{verbatim_source}'. "

    beats = category.get("seasonal_beats", [])
    knowledge_anchor = f"INDUSTRY CONTEXT: {beats[0].get('note', '')}. " if beats else ""

    sys_prompt = f"""Role: Elite Growth Strategist. Target: {prefix} {owner_name} in {ident.get('locality')}.
Objective: Compose high-impact WhatsApp message.
RULES:
1. TRIGGER PRIMACY: Address trigger '{trigger.get('kind')}' first.
2. NO FABRICATION: Use only context numbers. EVIDENCE: {evidence_block}
3. CONTEXT: {knowledge_anchor}
4. TONE: {hinglish_note} Professional clinical-peer tone for dentists.
5. LIMIT: 280-310 characters."""

    prompt = f"CONTEXT: {json.dumps({'merchant': ident, 'perf': m, 'trigger': trigger, 'customer': customer})}"
    res = await call_llm_chain(prompt, system=sys_prompt)
    if not res:
        v, c = m.get('views', '?'), m.get('calls', '?')
        body = f"{prefix} {owner_name}, noticed {v} views and {c} calls in {ident.get('locality')}. Important growth update found. Review now?"
        res = {"body": body, "cta": "Reply YES", "rationale": "Hard Fallback"}
    res["body"] = prune_message(res.get("body", ""))
    return res

# --- 5. Endpoints ---
@app.on_event("startup")
async def startup_event():
    logger.info("Initializing Agent Registry...")
    for agent in AGENT_REGISTRY:
        logger.info(f"Agent {agent.name} initialized with {len(agent.keys)} keys")

@app.get("/v1/healthz")
async def healthz(): return {"status": "ok"}

@app.get("/v1/metadata")
async def metadata():
    return {"team_name": "Vera Lead Solver", "version": "7.0", "engine": "Multi-Agent-Orchestrator"}

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = data.payload
    return {"accepted": True}

@app.post("/v1/tick")
async def tick(req: TickRequest):
    tids = sorted(req.available_triggers, key=lambda t: contexts["trigger"].get(t, {}).get("kind", ""), reverse=True)
    results = []
    # Sequential processing. Limit to 1 to stay under 30s.
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
    is_customer_facing = trigger.get("scope") == "customer"

    return {
        "conversation_id": f"conv_{trigger_id}", "merchant_id": trigger.get("merchant_id"),
        "customer_id": trigger.get("customer_id") if is_customer_facing else None,
        "send_as": "merchant_on_behalf" if is_customer_facing else "vera",
        "trigger_id": trigger_id, "template_name": "vera_platinum_v7",
        "body": composed["body"], "cta": composed["cta"], "suppression_key": trigger_id,
        "rationale": composed.get("rationale", "Orchestrated Inference")
    }

AUTO_REPLY_PATTERNS = [r"thank you for contacting", r"we are currently away", r"automated message", r"business hours", r"auto-reply"]
HOSTILE_PATTERNS = [r"stop", r"spam", r"useless", r"abuse", r"remove me"]
INTENT_PATTERNS = [r"\bok\b", r"\byes\b", r"\bdo it\b", r"let'?s do it", r"\bsure\b", r"\bgo ahead\b"]

@app.post("/v1/reply")
async def reply(req: Dict[str, Any]):
    msg = req.get("message", "").lower()
    turn = req.get("turn_number", 1)
    for p in HOSTILE_PATTERNS:
        if re.search(p, msg): return {"action": "end", "rationale": "Hostility detected."}
    for p in AUTO_REPLY_PATTERNS:
        if re.search(p, msg):
            if turn > 2: return {"action": "end", "rationale": "Repeated auto-reply."}
            return {"action": "wait", "wait_seconds": 3600, "rationale": "Auto-reply wait."}
    for p in INTENT_PATTERNS:
        if re.search(p, msg):
            sys = "Role: Vera AI. Merchant interest detected. Provide EXACT next step action. 15 words max."
            res = await call_llm_chain(f"Merchant said: {msg}", system=sys)
            body = res.get("body", "I'm setting that up for you now.") if res else "I'm setting that up now."
            return {"action": "send", "body": body, "cta": "Reply YES", "rationale": "Intent Transition."}

    prompt = f"Merchant message: {req.get('message', '')}. Turn: {turn}. History: {req.get('history', [])}"
    sys = "Role: Vera AI. If merchant says 'ok/yes/do it', provide EXACT next step action. Be concise."
    res = await call_llm_chain(prompt, system=sys)
    body = res.get("body", "I'm on it. Setting that up for you now. Ready?") if res else "Understood. I'll get that started. Ready?"
    return {"action": "send", "body": body, "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
