import os
import re
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI
from pydantic import BaseModel
from dotenv import load_dotenv

from scripts.composer import compose, compose_with_fallback

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VeraArchitect")

for key_name in ["NVIDIA_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"]:
    if not os.getenv(key_name):
        logger.warning(f"Missing {key_name} at startup. That tier will be skipped.")

app = FastAPI()

class ContextPayload(BaseModel):
    scope: Optional[str] = None
    context_id: Optional[str] = None
    version: Optional[int] = None
    payload: Dict[Any, Any] = {}

class TickRequest(BaseModel):
    available_triggers: List[str] = []

contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}

@app.get("/v1/healthz")
async def healthz():
    global contexts
    contexts = {"category": {}, "merchant": {}, "customer": {}, "trigger": {}}
    return {
        "status": "ok",
        "uptime_seconds": 100,
        "contexts_loaded": {
            "category": len(contexts["category"]),
            "merchant": len(contexts["merchant"]),
            "customer": len(contexts["customer"]),
            "trigger": len(contexts["trigger"])
        }
    }

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Lead Solver",
        "team_members": ["Agent", "User"],
        "model": "Fallback Chain (NVIDIA->Groq->Gemini) -> Local Qwen2.5-3B-Instruct",
        "approach": "Caveman Distiller + LLM Expander Pipeline",
        "contact_email": "rachit.mangawa.ug23@nsut.ac.in",
        "version": "1.0",
        "submitted_at": "2026-09-26T00:00:00Z"
    }

@app.post("/v1/context")
def push_context(data: ContextPayload):
    contexts[data.scope][data.context_id] = {"version": data.version, "payload": data.payload}
    return {"accepted": True, "ack_id": f"ack_{data.context_id}_v{data.version}", "stored_at": "2026-04-26T00:00:00Z"}

@app.post("/v1/tick")
async def tick(req: TickRequest):
    import time
    tids = sorted(req.available_triggers, key=lambda t: contexts["trigger"].get(t, {}).get("payload", {}).get("urgency", 0), reverse=True)
    request_deadline = time.time() + 27.0
    results = []
    for tid in tids:
        remaining = request_deadline - time.time()
        if remaining <= 2.0:
            logger.warning(f"Skipping trigger {tid}, {remaining:.1f}s left")
            break
        res = await process_trigger(tid, deadline=request_deadline)
        if res: results.append(res)
    return {"actions": results}

async def process_trigger(trigger_id: str, deadline: float = None):
    trigger_ctx = contexts["trigger"].get(trigger_id)
    if not trigger_ctx: return None
    trigger = trigger_ctx["payload"]
    merchant = contexts["merchant"].get(trigger.get("merchant_id", ""), {}).get("payload", {})
    category = contexts["category"].get(merchant.get("category_slug", ""), {}).get("payload", {"slug": "general"})
    customer = contexts["customer"].get(trigger.get("customer_id", ""), {}).get("payload")
    
    composed = await compose(category, merchant, trigger, customer, deadline=deadline)
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
            res = await compose_with_fallback(f"Merchant said: {msg}", system="Role: Vera AI. Interest detected. Provide EXACT next step action. 15 words max.")
            return {"action": "send", "body": res.get("body", "I'm setting that up for you now.") if res else "I'm setting that up now.", "cta": "Reply YES"}

    res = await compose_with_fallback(f"Merchant: {msg}", system="Role: Vera AI. Growth Strategist. Be concise.")
    return {"action": "send", "body": res.get("body", "Understood. Proceed?") if res else "Understood. Proceed?", "cta": "Reply YES"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
