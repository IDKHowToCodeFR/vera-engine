import json
import logging
import asyncio
import time
from typing import Optional
import httpx

from .llm import call_nvidia, call_groq, call_gemini, call_local
from .prompts import FEW_SHOT_EXAMPLES, build_local_sys_prompt

logger = logging.getLogger("VeraArchitect")

_cache: dict = {}
def cache_key(category, merchant, trigger, customer):
    return f"{merchant.get('id', 'm')}:{trigger.get('kind', 'k')}:{trigger.get('id', 't')}:{customer.get('id', 'c') if customer else 'none'}"

import re

def validate_output(res: dict, taboos: list) -> list[str]:
    errors = []
    if not res or not all(k in res for k in ["body", "cta", "rationale"]): 
        errors.append("missing keys body, cta, rationale")
        return errors
    body = res.get("body", "")
    if len(body.split()) > 40: errors.append("body exceeds 40 words")
    for t in taboos:
        pattern = r'\b' + re.escape(t.lower()) + r'\b'
        if re.search(pattern, body.lower()):
            errors.append(f"contains taboo word: {t}")
    if body.lower().count("reply") > 1: errors.append("multiple CTAs detected")
    return errors

async def compose_with_fallback(prompt: str, full_system: str, local_system: str = None, deadline: float = None, taboos: list = None) -> dict:
    if local_system is None:
        local_system = full_system
    if taboos is None:
        taboos = []
        
    start_time = time.time()
    if deadline is None:
        deadline = start_time + 27.0
    
    tiers = [
        ("NVIDIA", call_nvidia, 5.0),
        ("Groq", call_groq, 4.0),
        ("Gemini", call_gemini, 4.0),
        ("Local", call_local, None)
    ]
    
    for name, func, timeout in tiers:
        elapsed = time.time() - start_time
        remaining = deadline - (start_time + elapsed)
        
        if timeout is not None and remaining <= timeout:
            logger.warning(f"Skipping {name} due to time budget: {remaining:.1f}s left")
            continue
            
        try:
            tier_start = time.time()
            system_to_use = local_system if name == "Local" else full_system
            
            async def _run_tier(p):
                if timeout:
                    return await func(p, system_to_use, timeout)
                else:
                    try:
                        return await asyncio.wait_for(func(p, system_to_use, deadline), timeout=deadline - time.time())
                    except asyncio.TimeoutError:
                        return None
                        
            res = await _run_tier(prompt)
            
            # Validation and repair loop
            if res:
                errors = validate_output(res, taboos)
                if errors:
                    logger.warning(f"{name} validation failed: {errors}. Retrying...")
                    repair_prompt = prompt + f"\n\nPrevious attempt failed: {', '.join(errors)}. Fix and retry."
                    retry_remaining = deadline - time.time()
                    req_timeout = timeout if timeout else 2.0
                    if retry_remaining >= req_timeout:
                        res = await _run_tier(repair_prompt)
                        res_errors = validate_output(res, taboos) if res else ["missing response"]
                        if res_errors:
                            logger.warning(f"{name} retry failed: {res_errors}. Falling to next tier.")
                            res = None
                    else:
                        logger.warning(f"Skipping retry for {name} due to time budget: {retry_remaining:.1f}s left")
                        res = None

            tier_latency = (time.time() - tier_start) * 1000
            
            if res and not validate_output(res, taboos):
                logger.info(f"Served by {name} in {tier_latency:.0f}ms")
                return res
            else:
                logger.warning(f"{name} returned invalid schema or content")
                
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning(f"{name} failed: RateLimitError (429). Skipping to next tier immediately.")
            elif e.response.status_code == 401:
                logger.warning(f"{name} failed: AuthenticationError (401). Check API key. Skipping immediately.")
            else:
                logger.warning(f"{name} failed with HTTP {e.response.status_code}. Skipping immediately.")
        except httpx.TimeoutException as e:
            logger.warning(f"{name} timed out. Proceeding to next tier.")
        except httpx.RequestError as e:
            logger.warning(f"{name} failed: APIConnectionError / network error. Skipping immediately.")
        except Exception as e:
            logger.warning(f"{name} failed: {str(e)}")
            
    logger.warning("All tiers failed, returning hardcoded default")
    return {"body": "Following up soon.", "cta": "reply_yes", "rationale": "fallback_default"}

async def compose(category: dict, merchant: dict, trigger: dict, customer: Optional[dict] = None, deadline: float = None) -> dict:
    key = cache_key(category, merchant, trigger, customer)
    if key in _cache:
        return _cache[key]

    ident, perf = merchant.get("identity", {}), merchant.get("performance", {})
    owner_name = ident.get("owner_first_name", "Partner")
    active_offers = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    
    # 1. Context Distiller
    facts = []
    if customer:
        cust_ident = customer.get("identity", {})
        cust_rel = customer.get("relationship", {})
        facts.append(f"- Customer Name: {cust_ident.get('name', 'Customer')}")
        facts.append(f"- Last Visit: {cust_rel.get('last_visit', 'Unknown')}")
        if trigger.get("payload"): facts.append(f"- Trigger Context: {str(trigger['payload'])[:200]}")
    else:
        if perf.get("views"): facts.append(f"- Profile views (30d): {perf['views']}")
        if perf.get("ctr"): facts.append(f"- Your Click-Through Rate: {perf['ctr']} (Peer avg: {category.get('peer_stats', {}).get('avg_ctr', 'unknown')})")
        if active_offers: facts.append(f"- Active offer available: {active_offers[0].get('title')}")
        if trigger.get("payload"): facts.append(f"- Trigger Reason: {str(trigger['payload'])[:150]}")
    fact_string = "\n".join(facts) if facts else "- No specific data. Use curiosity hook."

    # 2. Dynamic Tone & Taboos
    voice = category.get("voice", {})
    tone = voice.get("tone", "professional peer")
    taboos_list = voice.get("taboos", ["guaranteed", "100%", "click here", "promise"])
    taboos = ", ".join(taboos_list)
    
    prefix = "Dr. " if category.get('slug') == 'dentists' else ""
    lang_pref = ident.get('languages', ['en'])
    hinglish_note = "USE NATURAL HINGLISH (code-mix English words and Hindi script/transliteration)." if 'hi' in lang_pref else "USE PROFESSIONAL ENGLISH."

    # 3. Engagement Lever Selection
    kind = trigger.get('kind', '')
    if 'dip' in kind:
        compulsion = "Loss Aversion (e.g., 'You are missing out on X...')"
        few_shot_key = "dip"
    elif 'spike' in kind or 'milestone' in kind:
        compulsion = "Social Proof / Validation (e.g., 'Everyone is doing X...')"
        few_shot_key = "spike"
    elif 'recall' in kind:
        compulsion = "Effort externalization ('I prepared these slots for you...')"
        few_shot_key = "recall"
    elif 'digest' in kind:
        compulsion = "Curiosity gap ('A new method improves X by Y%...')"
        few_shot_key = "digest"
    else:
        compulsion = "Curiosity ('Want to see how?')"
        few_shot_key = "digest"

    # 4. Few-Shot Example Injection
    few_shot_data = FEW_SHOT_EXAMPLES.get(few_shot_key, FEW_SHOT_EXAMPLES["digest"])
    few_shot_json = json.dumps(few_shot_data, indent=2)

    contrast_example = """
BAD (vague): 'We have a great offer for you!'
GOOD (specific): 'Your CTR dropped 12% this week vs 18% category avg — want the 3 fixes?'
"""

    scoring_rubric = f"You will be scored on: (1) SPECIFICITY - exact numbers/names/dates used, (2) GROUNDING - zero fabricated facts, (3) ENGAGEMENT - reply-worthy CTA, (4) TONE - matches {tone} register. Optimize for all four."

    if customer:
        cust_name = customer.get("identity", {}).get("name", "Customer")
        full_sys_prompt = f"""Role: {prefix}{owner_name} (Merchant). Target: {cust_name} (Customer).
Goal: WhatsApp engagement using {compulsion}. Send on behalf of {prefix}{owner_name}.
CRITICAL RULES:
{scoring_rubric}
1. TRIGGER PRIMACY: Address the {kind} trigger in the very first sentence.
2. HYPER-SPECIFICITY: You MUST quote exact numbers, metrics, or dates from the FACT SHEET (e.g., '38% better', '30 views', 'Oct issue'). Do not generalize.
3. MAX ENGAGEMENT: Keep the message under 3 sentences. End with a frictionless, curiosity-driven question (e.g., 'Want to see the data?', 'Should I draft a reply?').
4. NO FABRICATION: Only use data from the FACT SHEET.
5. LENGTH: body must be 25-40 words. WhatsApp messages over 40 words get ignored — be ruthlessly concise.
6. TONE: {hinglish_note} Be conversational, not corporate.
7. CTA: Exactly ONE clear call-to-action (e.g., 'Reply YES to X').
8. SELF-CHECK: before writing, mentally list which FACT SHEET items you will cite. Do not include any name/number/date not in that list.
9. TABOOS: Do not use these words: {taboos}.

WARNING: YOU WILL BE PENALIZED IF YOU USE ANY OF THESE WORDS: {taboos}

Example Output format for a good message:
{few_shot_json}
{contrast_example}"""
        local_sys_prompt = build_local_sys_prompt(tone, kind, compulsion, taboos, hinglish_note, prefix, owner_name, few_shot_json, cust_name=cust_name)
    else:
        full_sys_prompt = f"""Role: {tone}. Target: {prefix}{owner_name} (Merchant) in {ident.get('locality', 'your area')}.
Goal: WhatsApp engagement using {compulsion}.
CRITICAL RULES:
{scoring_rubric}
1. TRIGGER PRIMACY: Address the {kind} trigger in the very first sentence.
2. HYPER-SPECIFICITY: You MUST quote exact numbers, metrics, or dates from the FACT SHEET (e.g., '38% better', '30 views', 'Oct issue'). Do not generalize.
3. MAX ENGAGEMENT: Keep the message under 3 sentences. End with a frictionless, curiosity-driven question (e.g., 'Want to see the data?', 'Should I activate this?').
4. NO FABRICATION: Only use data from the FACT SHEET.
5. LENGTH: body must be 25-40 words. WhatsApp messages over 40 words get ignored — be ruthlessly concise.
6. TONE: {hinglish_note} Be conversational, not corporate.
7. CTA: Exactly ONE clear call-to-action (e.g., 'Reply YES to X').
8. SELF-CHECK: before writing, mentally list which FACT SHEET items you will cite. Do not include any name/number/date not in that list.
9. TABOOS: Do not use these words: {taboos}.

WARNING: YOU WILL BE PENALIZED IF YOU USE ANY OF THESE WORDS: {taboos}

Example Output format for a good message:
{few_shot_json}
{contrast_example}"""
        local_sys_prompt = build_local_sys_prompt(tone, kind, compulsion, taboos, hinglish_note, prefix, owner_name, few_shot_json)

    prompt = f"FACT SHEET:\n{fact_string}\n\nTask: Draft a WhatsApp message using ONLY the facts above. Be highly specific with numbers and dates."
    
    res = await compose_with_fallback(prompt, full_sys_prompt, local_sys_prompt, deadline=deadline, taboos=taboos_list)
    
    # Add sender attribution required by the challenge
    res["send_as"] = "merchant_on_behalf" if customer else "vera"
    if res.get("rationale") != "fallback_default":
        _cache[key] = res
    return res
