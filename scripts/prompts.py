FEW_SHOT_EXAMPLES = {
    "spike": {
        "body": "[Merchant Name], your profile views jumped 45% this week. Other merchants in your area are running active offers to capture this traffic... Want me to activate one for you?",
        "cta": "Reply YES",
        "rationale": "Social proof and validation."
    },
    "dip": {
        "body": "[Merchant Name], your CTR dropped 12% this week vs 18% category avg. You are missing out on potential customers... Want the 3 fixes to recover traffic?",
        "cta": "Reply YES",
        "rationale": "Loss aversion."
    },
    "recall": {
        "body": "[Merchant Name], it's time for your customers' 3-month check-in. I prepared these slots for you to send a quick WhatsApp reminder... Should I draft it for you?",
        "cta": "Reply YES",
        "rationale": "Effort externalization."
    },
    "digest": {
        "body": "[Merchant Name], the latest report shows a new method improves retention by 38%... Want to see how it works for your business?",
        "cta": "Reply YES",
        "rationale": "Curiosity gap."
    }
}

def build_local_sys_prompt(tone, kind, compulsion, taboos, hinglish_note, prefix, owner_name, few_shot_json, cust_name=None):
    role_str = f"Role: {prefix}{owner_name} (Merchant). Target: {cust_name} (Customer)." if cust_name else f"Role: {tone}. Target: {prefix}{owner_name} (Merchant)."
    return f"""{role_str}
Goal: WhatsApp engagement using {compulsion}.
CRITICAL RULES:
1. TRIGGER PRIMACY: Address the {kind} in the first sentence.
2. HYPER-SPECIFICITY: Quote exact numbers/dates from FACT SHEET.
3. MAX ENGAGEMENT: Keep under 3 sentences. End with a curiosity question.
4. NO FABRICATION: Only use data from FACT SHEET.
5. LENGTH: body must be 25-40 words. Be ruthlessly concise.
6. TONE: {hinglish_note} Be conversational.
7. CTA: Exactly ONE clear call-to-action (e.g., 'Reply YES to X').
8. TABOOS: Do not use these words: {taboos}.

WARNING: YOU WILL BE PENALIZED IF YOU USE ANY OF THESE WORDS: {taboos}

Example Output format for a good message:
{few_shot_json}"""
