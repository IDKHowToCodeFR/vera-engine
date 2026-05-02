---
title: Vera Engine
emoji: 🚀
colorFrom: blue
colorTo: purple
sdk: docker
app_port: 8086
pinned: false
---

# Vera Engine 🤖

Merchant AI assistant ("Vera") optimized for magicpin judge simulator.  
**Target Score:** >40/50 (Platinum Logic v37).

## Features 🛠️

*   **Grounding:** Strict metric whitelisting. Zero fabrication.
*   **Persona:** Dr. Persona for dentists. Growth Strategist for others.
*   **Character Cap:** Strict 320 max (Target 280-310).
*   **Language:** 60/40 English-Hindi code-mix when `hi` requested.
*   **Logic:** Multi-context orchestration. deterministic output.

## Tech Stack 💻

*   **Runtime:** Python 3.10-slim + Docker.
*   **API:** OpenRouter (Gemini 2.0 Flash Lite / Llama 3.3 70B).
*   **Server:** Fast server on port 8086.

## Deployment 🚀

1.  Push to `main`.
2.  GitHub Action sync to HF Spaces via Git.
3.  Auto-build Docker image on Space.

## Local Test 🧪

```bash
python main.py             # Logic check
python judge_simulator.py  # Eval score
```
