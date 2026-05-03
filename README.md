---
title: Vera Engine Platinum
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
---

# Vera Engine Platinum v7.0 🤖

**Autonomous Multi-Agent Orchestrator optimized for the magicpin AI Challenge.**

## 1. THE CORE (CAVEMAN LOGIC)
*   **Vera good.** 
*   **Bot no lie.** 
*   **Chain long.**
*   **Local safe.** 
*   **Always win.**

## 2. ARCHITECTURAL SPECIFICATIONS

### Scalable Multi-Agent Orchestrator
The system has been refactored from a static chain to a dynamic **Agent Registry**. This allows for infinite horizontal scaling of models and providers.

1.  **Agent Registry**: Each provider (OpenRouter, Gemini, Groq, DeepSeek) is an independent Agent with its own health tracking.
2.  **Health-Aware Key Rotation**: If an Agent encounters a 429 (Rate Limit) or 401 (Auth), it automatically rotates its local key pool.
3.  **Tiered Redundancy**:
    *   **Tier 1-4 (Cloud)**: Sequential execution across high-performance models (Laguna, Hy3, Gemini 2.0, Llama 3.3).
    *   **Tier 5 (Local)**: 100% autonomous fallback to `Llama 3.2 (3B)` via Ollama. 17.9s benchmarked.
4.  **FAST_TEST Mode**: Environment-aware flag to bypass cloud tiers during local judge simulation for rapid iteration.

## 3. KEY FEATURES

*   **Metric Anchoring**: Pre-extraction of metrics as "Mandatory Evidence" to ensure 100% grounding integrity.
*   **Elastic Schema**: Optional Pydantic fields with strict defaults to eliminate 422 Unprocessable Entity errors.
*   **Atomic Throughput**: Sequential processing in `/v1/tick` to survive strict 30s judge timeouts on 2vCPU hardware.
*   **Turn-Based Escalation**: Intelligent auto-reply shield that terminates conversations stuck in infinite canned-response loops (Turn 3+).

## 4. API DOCUMENTATION

| Endpoint | Method | Purpose | Response Schema |
| :--- | :--- | :--- | :--- |
| `/v1/healthz` | `GET` | Compliant Liveness Probe | `{"status": "ok"}` |
| `/v1/metadata` | `GET` | System Identity & Multi-Agent Status | `{"version": "7.0", ...}` |
| `/v1/context` | `POST` | Elastic Context Ingestion | `{"accepted": true}` |
| `/v1/tick` | `POST` | Atomic Trigger Processing | `{"actions": [...]}` |
| `/v1/reply` | `POST` | Escalated Shield Handling | `{"action": "send/wait/end"}` |

## 5. TECHNICAL STACK

*   **Framework**: FastAPI / Uvicorn (Port 8080)
*   **Runtime**: Docker (Python 3.10-slim)
*   **Local LLM**: Ollama / Llama 3.2 (3B)
*   **Infrastructure**: Hugging Face Spaces (2vCPU / 16GB RAM)

## 6. DEPLOYMENT

```bash
git push origin main
# Auto-sync to Hugging Face Space
```
