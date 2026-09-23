---
title: Vera Engine
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8080
pinned: false
---

# 🚀 Vera Engine v1.0

[![FastAPI](https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white)](https://www.docker.com/)
[![Python 3.10](https://img.shields.io/badge/Python-3776AB?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![Llama.cpp](https://img.shields.io/badge/llama.cpp-000000?style=for-the-badge&logo=c%2B%2B&logoColor=white)](https://github.com/ggerganov/llama.cpp)

> **High-Performance AI Orchestrator optimized for the magicpin Vera AI Challenge.**

---

## 🏗️ 1. The Architecture

The system operates on a highly optimized, deterministic fail-fast fallback cascade to guarantee sub-30-second responses on constrained Hugging Face Spaces (2vCPU / 16GB RAM) without compromising reasoning quality.

### 🌊 4-Tier Fail-Fast Cascade
Instead of relying on a single point of failure, the engine delegates composition to a highly available 4-tier chain:

1. **Tier 1 (Speed & Intelligence)**: NVIDIA NIM (`llama-3.3-70b-instruct`) - 5s timeout.
2. **Tier 2 (Fast Failover)**: Groq (`llama-3.3-70b-versatile`) - 4s timeout.
3. **Tier 3 (Secondary Failover)**: Gemini (`gemini-2.5-flash`) - 4s timeout.
4. **Tier 4 (Local Airgap)**: Natively executed `qwen2.5-3b-instruct` via `llama-cpp-python` with **strict LlamaGrammar enforcement**.

> [!TIP]
> **Dynamic Time Budgeting**
> If an API returns a `401` or `429`, the orchestrator immediately short-circuits to the next tier. Cloud timeouts are strictly capped at 13 seconds cumulative worst-case, reserving a guaranteed 14-second budget for the local airgapped model.

---

## ⚡ 2. Pipeline Strategy

1. **Context Distiller**: Instantly processes 500KB+ JSON payloads into dense factual bullet points in `< 0.001s`.
2. **LLM Expander**: Takes strict facts and expands them into compelling, natively conversational WhatsApp replies (supporting Hinglish code-mixing).
3. **Auto-Repair Loop**: Automatically intercepts taboo violations, word-count breaches, and CTA proliferation, dynamically calculating time budgets to fire an intra-tier self-correction prompt before failing over.
4. **Strict Schema Constraints**: Hardware-level `LlamaGrammar` (Local) and `json_object` format (Cloud) guarantee zero JSON parsing failures.

---

## 🌐 3. API Contract

| Endpoint | Method | Purpose | Response Schema |
| :--- | :--- | :--- | :--- |
| `/v1/healthz` | **GET** | Compliant Liveness Probe | `{"status": "ok", "uptime_seconds": 100}` |
| `/v1/metadata` | **GET** | System Identity | `{"version": "1.0", "model": "..."}` |
| `/v1/context` | **POST** | Elastic Context Ingestion | `{"accepted": true}` |
| `/v1/tick` | **POST** | Atomic Trigger Processing | `{"actions": [...]}` |
| `/v1/reply` | **POST** | Escalated Shield Handling | `{"action": "send|wait|end"}` |

---

## 🛠️ 4. Technical Stack

* **Framework**: FastAPI / Uvicorn (Port `8080`)
* **Local SLM Execution**: `llama-cpp-python` (Pre-compiled CPU Wheels)
* **Models**: `Llama 3.3 70B`, `Gemini 2.5 Flash`, `Qwen2.5 3B`
* **Infrastructure**: Dockerized `python:3.10-slim` on Hugging Face Spaces
