import time
import os
import sys
from huggingface_hub import hf_hub_download
from llama_cpp import Llama

def run_benchmark():
    print("Loading model qwen2.5-7b-instruct-q4_k_m...")
    t0 = time.time()
    llm = Llama.from_pretrained(
        repo_id="bartowski/Qwen2.5-7B-Instruct-GGUF",
        filename="Qwen2.5-7B-Instruct-Q4_K_M.gguf",
        n_ctx=2048,
        n_threads=os.cpu_count(),
        verbose=False
    )
    load_time = time.time() - t0
    print(f"Load time: {load_time:.2f}s")

    prompt_system = "Role: Elite Growth Strategist. Target: Dr. Smith in New York. Goal: WhatsApp engagement using Curiosity gap. CRITICAL RULES: 1. TRIGGER PRIMACY: Address spike immediately. 2. SPECIFICITY: You MUST explicitly include exact names, dates, numbers, and locations from the FACT SHEET in the body. 3. ENGAGEMENT: Make it irresistible to reply. Ask a highly relevant, low-effort question. 4. NO FABRICATION. 5. TABOOS: Do not use these words: internal metrics, JSON, system, guaranteed. 6. TONE: USE PROFESSIONAL ENGLISH. 7. CTA: Exactly ONE call-to-action at the end (e.g. Reply YES)."
    prompt_user = "FACT SHEET:\n- Profile views (30d): 1500\n- Your Click-Through Rate: 12% (Peer avg: 8%)\n- Active offer available: Summer Clean 50% Off\n- Trigger Reason: Profile views spiked by 40% this week.\n\nTask: Draft a WhatsApp message using ONLY the facts above. Be highly specific with numbers and dates."

    messages = [
        {"role": "system", "content": prompt_system + "\n\nRETURN JSON ONLY."},
        {"role": "user", "content": prompt_user}
    ]

    latencies = []
    toks_per_sec = []

    for max_tokens in [150, 250]:
        print(f"\n--- Testing max_tokens={max_tokens} ---")
        current_latencies = []
        for i in range(5):
            t0 = time.time()
            res = llm.create_chat_completion(
                messages=messages,
                temperature=0.3,
                max_tokens=max_tokens,
                response_format={"type": "json_object"}
            )
            t_total = time.time() - t0
            
            gen_tokens = res["usage"]["completion_tokens"]
            tps = gen_tokens / t_total if t_total > 0 else 0
            
            current_latencies.append(t_total)
            toks_per_sec.append(tps)
            print(f"Run {i+1}: Latency={t_total:.2f}s, Tokens={gen_tokens}, TPS={tps:.2f} tok/s")
        
        current_latencies.sort()
        p50 = current_latencies[len(current_latencies)//2]
        p95_idx = int(0.95 * len(current_latencies))
        if p95_idx >= len(current_latencies): p95_idx = len(current_latencies) - 1
        p95 = current_latencies[p95_idx]
        
        print(f"Stats (max_tokens={max_tokens}): p50={p50:.2f}s, p95={p95:.2f}s")
    
if __name__ == "__main__":
    run_benchmark()
