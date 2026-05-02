# Knowledge Base: Vera Lead Solver

## Failure Pattern Audit (2026-05-02)

### 1. Metric Fabrication (Grounding Failure)
- **Pattern**: Bot invented "45 directions" and "0.18% view increase" to sound specific.
- **Deduction**: Specificity score dropped to 6/10.
- **Fix**: Sanitize context and provide a "Whitelist of Grounded Metrics". Warn against inventing secondary metrics.

### 2. Language Imbalance
- **Pattern**: When Hinglish is requested, the bot writes "mostly in Hindi", which the judge penalizes for not being a proper "mix".
- **Fix**: Instruct bot to use 60% English / 40% Hindi for Hinglish.

### 3. Abrupt Tones
- **Pattern**: Short messages often sound too formal or clinical without enough "warmth" or "persuasion".
- **Fix**: Use specific persuasive triggers: loss aversion ("losing 5% weekly"), peer proof ("other clinics in [Locality]"), or scarcity.

### 4. Decision Quality Voids
- **Pattern**: Bot mentions the trigger but doesn't explain the *financial* or *business* impact.
- **Fix**: Prompt bot to explicitly state "WHY ACT NOW" (e.g., "Non-compliance risks clinic closure" or "Recall improves LTV").

## Technical Strategy for 50/50
- **Deterministic Metrics**: Only allow metrics explicitly found in `perf` or `payload`.
- **Character Buffer**: Hard-coded pruning to 300 chars to avoid truncation penalty.
- **Persona**: "Elite Growth Strategist" - peer of the merchant, but authoritative.
- **Citations**: Verbatim inclusion of sources is mandatory.
