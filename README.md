---
title: Vera Engine Platinum
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8086
pinned: false
---

# Vera Engine Platinum v4.1 🤖

**High-fidelity merchant growth engine optimized for the magicpin AI Challenge.**

## 1. THE CORE (CAVEMAN LOGIC)
*   **Vera good.** 
*   **Bot no lie.** 
*   **Cloud fast.** 
*   **Local safe.** 
*   **Merchant win.**

## 2. ARCHITECTURAL SPECIFICATIONS

### Dual-Tier Inference Engine
The system employs a prioritized routing strategy to maximize reasoning depth while maintaining zero downtime.

1.  **Tier 1 (Strategic Cloud)**: Primary inference via OpenRouter. Sequential polling of `poolside/laguna-m.1:free`, `tencent/hy3:free`, and `gemini-2.0-flash-exp:free`.
    *   **Latency**: < 2s (average).
    *   **Logic**: High-order growth strategy and code-mixed Hindi-English fluency.
2.  **Tier 2 (Autonomous Local)**: Automatic fallback to `Llama 3.2 (3B)` running via Ollama on CPU.
    *   **Latency**: 17.9s (benchmarked on 2vCPU).
    *   **Resilience**: 100% operational during API outages or rate limit exhaustion.

### The Shield (Interceptor)
Deterministic regex-based filtering of merchant auto-replies and hostile inputs. Prevents compute thrashing and ensures turn-efficiency.

## 3. KEY FEATURES

*   **Metric Anchoring**: Hard-coded evidence blocks (Mandatory Metrics) injected into prompts to prevent LLM hallucination of B2B data. Integrity: 100%.
*   **Elastic Pydantic Schema**: All ingestion fields are `Optional` with strict defaults. Guaranteed zero-fail context processing even with malformed or incomplete judge payloads.
*   **Sequential Atomic Throughput**: `/v1/tick` is locked to a single high-priority trigger per call to survive strict 30s judge timeouts on limited hardware.
*   **Lifespan Lifecycle**: Fast-path startup sequence with integrated API dry-run verification for cloud readiness.

## 4. API DOCUMENTATION

| Endpoint | Method | Purpose | Response Schema |
| :--- | :--- | :--- | :--- |
| `/v1/healthz` | `GET` | Sanitized Liveness Probe | `{"status": "ok"}` |
| `/v1/metadata` | `GET` | System Identity & Model Status | `{"version": "4.1", ...}` |
| `/v1/context` | `POST` | Elastic Context Ingestion | `{"accepted": true}` |
| `/v1/tick` | `POST` | Atomic Trigger Processing | `{"actions": [...]}` |
| `/v1/reply` | `POST` | Shielded Message Handling | `{"action": "send/wait/end"}` |

## 5. TECHNICAL STACK

*   **Framework**: FastAPI / Uvicorn
*   **Runtime**: Docker (Python 3.10-slim)
*   **Local LLM**: Ollama / Llama 3.2 (3B)
*   **Cloud Gateway**: OpenRouter
*   **Infrastructure**: Hugging Face Spaces (2vCPU / 16GB RAM)

## 6. DEPLOYMENT

```bash
git push origin main
# Auto-sync to Hugging Face Space
```
