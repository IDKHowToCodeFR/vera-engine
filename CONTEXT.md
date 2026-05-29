# Vera Engine Domain Context

## Glossary

### Vera
The merchant-facing AI assistant that engages partners over WhatsApp to help them grow their business.

### 4-Context Framework
The core composition model for Vera's messages:
1. **CategoryContext**: Vertical-specific knowledge (e.g., dentists, salons).
2. **MerchantContext**: Specific business state (performance, identity).
3. **TriggerContext**: The event or signal that initiates a conversation.
4. **CustomerContext**: (Optional) Data about a customer when Vera acts on the merchant's behalf.

### Grounding
The requirement that every message must be backed by data from the context layers, with zero fabrication of metrics.

### Curiosity Hook
A conversational technique used to engage merchants when no specific performance data is available for a trigger.

### Hinglish
A natural mix of English and Hindi (transliterated or script) used to maintain a relatable persona for Indian merchants.

## Core Rules
- **Message Limit**: Maximum 320 characters. Target 280-310.
- **CTA**: Exactly one clear, actionable next step.
- **Tone**: Senior Growth Strategist (professional yet peer-to-peer).
- **Latency**: Must respond to judge within 30 seconds.
