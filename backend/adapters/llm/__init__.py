"""
backend.adapters.llm
====================

LLM adapters — implementations of the ``LLMProvider`` port for three
provider families:

* ``OpenAICompatibleAdapter`` — OpenAI, DeepSeek, Groq, OpenRouter,
  MiniMax, Kimi, Moonshot (anything that speaks the OpenAI Chat
  Completions API).
* ``GeminiAdapter`` — Google's Gemini family. Internally cascades
  ``gemini-2.0-flash`` → ``gemini-1.5-flash`` → ``gemini-1.5-pro``
  within the adapter because each model has different availability
  per user (the 2.0/1.5 free tier limits differ).
* ``DeepSeekDirectAdapter`` — direct call to ``api.deepseek.com``
  via the OpenAI client (kept separate for legacy callers that pin
  DeepSeek regardless of ``LLM_PROVIDER``).

The fallback chain across families (e.g. OpenAI → Gemini → DeepSeek)
lives in ``application.services.llm_orchestrator.LLMOrchestrator``,
not in the adapters themselves. Each adapter only knows how to call
its own provider once.
"""