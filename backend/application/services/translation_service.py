"""
backend.application.services.translation_service
=================================================

Builds the ``LANGUAGE OVERRIDE`` block the LLM prompt gets prepended and
appended with when ``force_language`` is set on a generation call.

Moved verbatim from ``backend/main.py:_build_language_override`` in
commit 6 of the hexagonal refactor. Kept as a module-level function
(no class) because it has no state and no DI dependencies — it's a pure
template builder.
"""

from __future__ import annotations


def build_language_override(target_language: str, source_language: str) -> str:
    """Build the LANGUAGE OVERRIDE block prepended AND appended to the
    system prompt when ``force_language`` is set. Priority is absolute
    over rule 8 (LANGUAGE MATCHING).

    The block is intentionally aggressive: it ignores the JD language
    even if the JD is in Spanish, because the user explicitly requested
    a forced translation via the Translate to English button.
    """
    return f"""
LANGUAGE OVERRIDE (ABSOLUTE PRIORITY — overrides rule 8 LANGUAGE MATCHING):
- The user explicitly requested the output CV in English ({target_language}).
- IGNORE the source JD language and the base resume source language ({source_language}).
- Produce ALL text fields (summary, experience[*].points, projects[*].points, skills[*].category,
  skills[*].items, education[*].degree, achievements[*], section_labels) in ENGLISH.
- Never mix languages in the same document.
- Even if the JD is in Spanish, English wins. Even if rule 8 says otherwise, this wins.

DO NOT TRANSLATE (keep verbatim):
- Brand names: BBVA, Mercadona, Carrefour, Google, Microsoft, Amazon, Mercado Libre, Rappi, Glovo, etc.
- Product names: iPhone, Android, RenderCV, Typst, Playwright, FastAPI, LangGraph, LangChain, etc.
- Tech stack: React, Python, TypeScript, JavaScript, FastAPI, AWS, Docker, Kubernetes, PostgreSQL,
  Postgres, Redis, GraphQL, REST, OpenAI, Gemini, Vite, Tailwind, shadcn/ui, etc.
  NEVER use Spanish variants (e.g. "Reaccionar", "Pitón") — always English canonical names.
- Proper nouns (cities): keep in local script (Medellín, Bogotá, Madrid, Sevilla, A Coruña).
  Do NOT anglicise accents.
- Proper nouns (countries): use EN convention (España → Spain, México → Mexico; Colombia and
  Argentina stay the same in EN).
- Certification credential codes: AZ-900, AWS Cloud Practitioner, PMP, CISSP, etc. Keep verbatim.

MUST TRANSLATE / ADAPT:
- Honorifics: Sr. / Sra. → OMIT (do not render).
- Ongoing dates: "Actualmente", "Presente", "Hoy" → "Present".
- Spanish vocational training degrees:
    * "Ciclo Formativo de Grado Superior" / "CFGS" → "Higher Vocational Training".
    * "Formación Profesional" / "FP" (generic) → "Vocational Degree".
    * "Grado Medio" → "Vocational Degree (Intermediate level)".
    * "Grado Superior" → "Higher Vocational Training".
- National IDs:
    * "DNI" → "National ID (DNI)".
    * "Cédula de ciudadanía" → "National ID (Cédula)".
    * "Cédula de identidad" → "National ID".
    * "NIE" → "Foreign Resident ID (NIE)".
- Driver's license: "Carnet de conducir B" / "Licencia de conducir B" → "Driver's license (Category B)".
- Phone numbers: keep the original digits verbatim. Do NOT invent a +1 US prefix when the digits
  are Spanish/Colombian/etc. — the existing sanitize_phone in render_service.py handles prefix.

ANTI-AI REAFFIRMATION (applies EQUALLY to English output):
- burstiness, vary_bullet_syntax, anti_repetition_project_footprint, natural_language_markers
  (rules 15, 17, 18, 20) continue to apply with equal force.
- DO NOT substitute the Spanish pattern examples with English AI clichés:
  NEVER use: "spearheaded", "delved into", "tackled", "orchestrated synergy",
  "navigated complexities", "synergized", "leveraged stakeholder value", "testament to".
- USE the four EN-native narrative patterns instead, varied across consecutive bullets:
  * Pattern A (Outcome-First): "Reduced response latency by 40% by refactoring the FastAPI endpoints..."
  * Pattern B (Challenge-First): "Faced with 8s p99 latency on the checkout flow, I rebuilt the queue layer with Redis Streams..."
  * Pattern C (Action-First): "Led the migration of the legacy monolith to Kubernetes, decommissioning 12 services over 4 months..."
  * Pattern D (Tool-First): "Through Playwright + FastAPI + SSE, automated E2E coverage for 40 critical user paths..."
- Vary sentence length and cadence: mix 1-line statements with 2-line contextual achievements.

SECTION LABELS:
- section_labels MUST be in English: "Professional Summary", "Education", "Skills",
  "Work Experience", "Projects", "Achievements", "Portfolio".
"""


__all__ = ["build_language_override"]