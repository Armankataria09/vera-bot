# Architecture Decisions

1. **Gemini 3.8 Flash:** The LLM adapter uses Google's Gemini API directly through the official Google Gen AI Python SDK.
2. **Free tier:** `gemini-3.8-flash` is configured by default because Google's current pricing page lists free input/output pricing for its free tier.
3. **Grounding first:** The prompt and deterministic validators prevent unsupported facts from reaching the judge.
4. **Fallback:** If Gemini is unavailable or rate-limited, the service continues with a factual deterministic fallback instead of crashing.
5. **Stateful behavior:** Context versioning, suppression and conversation policy remain deterministic and testable outside the LLM.
