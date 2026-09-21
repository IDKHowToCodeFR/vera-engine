---
title: Vera Engine
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
---

# Vera Engine v1.0 🤖

**High-Performance AI Orchestrator optimized for the magicpin Vera AI Challenge.**

## 1. THE ARCHITECTURE
The system operates on a highly optimized, deterministic fail-fast fallback cascade to guarantee sub-30-second responses on Hugging Face Spaces (2vCPU / 16GB RAM) without compromising on reasoning quality.

### 4-Tier Fail-Fast Cascade
Instead of relying on a single provider, the engine delegates composition to a 4-tier chain of LLM providers.
1. **Tier 1 (Speed & Intelligence)**: NVIDIA NIM (`llama-3.3-70b-instruct`) - 5s timeout.
2. **Tier 2 (Fast Failover)**: Groq (`llama-3.3-70b-versatile`) - 4s timeout.
3. **Tier 3 (Secondary Failover)**: Gemini (`gemini-2.5-flash`) - 4s timeout.
4. **Tier 4 (Local Airgap)**: Natively executed `qwen2.5-3b-instruct` via `llama-cpp-python`.

### Dynamic Time Budgeting & Fail-Fast
- **Fail-Fast**: If an API returns a 401 (Auth Error) or 429 (Rate Limit), the orchestrator immediately short-circuits to the next tier without waiting for the timeout, saving crucial seconds.
- **Budget Reallocation**: The local model inherently requires the most time on a CPU. By aggressively capping the cloud tier timeouts (13s combined worst-case), the orchestrator guarantees a minimum of 14 seconds for the local `qwen2.5-3b` model to complete execution before the hard 30s deadline.

## 2. PIPELINE STRATEGY
1. **Context Distiller (Python)**: Instantly processes 500KB+ JSON payloads into dense factual bullet points in < 0.001s.
2. **LLM Expander**: Takes the strict facts and expands them into compelling, Hinglish-supported, natively conversational WhatsApp replies.
3. **Strict JSON Schema**: Native `response_format={"type": "json_object"}` constraints across all adapters ensure zero JSON-parsing failures.

## 3. API DOCUMENTATION

| Endpoint | Method | Purpose | Response Schema |
| :--- | :--- | :--- | :--- |
| /v1/healthz | GET | Compliant Liveness Probe | {"status": "ok"} |
| /v1/metadata | GET | System Identity | {"version": "1.0", "model": "Fallback Chain...", ...} |
| /v1/context | POST | Elastic Context Ingestion | {"accepted": true} |
| /v1/tick | POST | Atomic Trigger Processing | {"actions": [...]} |
| /v1/reply | POST | Escalated Shield Handling | {"action": "send/wait/end"} |

## 4. TECHNICAL STACK
* **Framework**: FastAPI / Uvicorn (Port 8080)
* **Local LLM Execution**: `llama-cpp-python` (Pre-compiled CPU Wheels)
* **Models**: Llama 3.3 70B, Gemini 2.5 Flash, Qwen2.5 3B
* **Infrastructure**: Dockerized Python 3.10-slim on Hugging Face Spaces
