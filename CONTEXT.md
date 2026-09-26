# Domain Context

## Glossary
* **Vera**: AI bot → WhatsApp engagement → grow merchant biz.
* **4-Context**:
  1. `CategoryContext`: Vertical info (dentists/salons).
  2. `MerchantContext`: Biz state (perf/identity).
  3. `TriggerContext`: Event → convo start.
  4. `CustomerContext`: Opt data (acting for merchant).
* **Grounding**: 100% real metrics from req. 0 metric hallucination.
* **Curiosity Hook**: Hook merchant when no perf data.
* **Hinglish**: Hindi+En mix (60/40) → relate to IN merchants.

## Rules
* **Len**: No hard cap. Keep terse/readable.
* **CTA**: 1 clear action. YES/STOP or open.
* **Tone**: Match category `voice` (peer/clinical). No promo.
* **Lang**: Match merchant pref.
* **Speed**: Res < 30s.

## Tech Strategy (50/50 Score)
* **Distill**: `Context Distiller` → shrink 500KB JSON → 4 bullets.
* **Router**: API req → `compose_with_fallback`. 4-tier chain (NVIDIA → Groq → Gemini → Local `llama-cpp-python` `qwen2.5-3b-instruct`).
* **Format**: Schema force → pure JSON.
* **Idempotent**: `/v1/healthz` → clear `contexts`.
* **Hooks**: Loss aversion, peer proof, scarcity, binary commit.
