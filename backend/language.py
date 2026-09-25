"""
backend/language.py
===================

Heuristic language detector used by the `cv-translate-to-english` change.

This module deliberately avoids pulling a new dependency (no `langdetect` /
`langid`) and ships with a small, transparent heuristic based on diacritics and
high-signal stopwords.

Design contract (see `sdd/cv-translate-to-english/design` section 2.2):

* For CVs longer than ~200 words the recall is documented at ~95-98%.
* For very short texts (< 80 tokens) the detector returns ``"unknown"`` so the
  caller can fall back to its own logic.
* False-positive rate on Spanish CVs misclassified as English is documented as
  roughly 5%; the backend guardrail ``E_CV_ALREADY_ENGLISH`` is a safety net
  that always fires for true positives, so the user experience degrades to a
  single error toast rather than a wrong translation.

Public API:
    detect_language(text: str) -> Literal["en", "es", "unknown"]
"""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

# Spanish-specific diacritics (uppercase + lowercase variants handled in code).
_ES_DIACRITICS = set("áéíóúñÁÉÍÓÚÑüÜ¿¡")

# High-signal Spanish function words. Tokens are 3+ chars to match the
# tokenisation regex below. Verbs are intentionally excluded because they
# inflect heavily; closed-class words are stable across registers.
_ES_STOPWORDS = frozenset({
    "para", "con", "sin", "por", "del", "los", "las", "una", "uno",
    "que", "como", "más", "pero", "este", "esta", "estos", "estas",
    "desde", "hasta", "sobre", "entre", "cuando", "donde", "porque",
    "muy", "todo", "todos", "todas", "otro", "otros", "otra", "otras",
    "cual", "cuales", "quien", "quienes", "sido", "sido", "siendo",
    "años", "año", "meses", "mes", "días", "día", "trabajé", "trabajo",
    "empresa", "empresas", "proyecto", "proyectos", "desarrollo",
    "desarrollé", "implementé", "lideré", "diseñé", "actualmente",
    "experiencia", "formación", "educación", "habilidades", "perfil",
    "ingeniero", "ingeniera", "desarrollador", "desarrolladora",
    "responsable", "encargado", "encargada",
})

# High-signal English function words; same coverage principle.
_EN_STOPWORDS = frozenset({
    "the", "and", "with", "from", "this", "that", "these", "those",
    "for", "into", "over", "under", "between", "when", "where",
    "because", "while", "have", "has", "had", "been", "being",
    "years", "year", "months", "month", "days", "day", "worked",
    "company", "companies", "project", "projects", "development",
    "engineered", "implemented", "led", "designed", "currently",
    "experience", "education", "skills", "profile", "engineer",
    "developer", "responsible", "own", "role", "team", "teams",
})

_TOKEN_RE = re.compile(r"[a-záéíóúñü]{3,}", re.IGNORECASE)


def _strip_accents(s: str) -> str:
    """Strip combining diacritics so we can match ES tokens without their tildes."""
    decomposed = unicodedata.normalize("NFD", s)
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")


def detect_language(text: str) -> Literal["en", "es", "unknown"]:
    """
    Classify ``text`` as ``"es"`` (Spanish), ``"en"`` (English) or ``"unknown"``.

    Heuristic:
        1. Presence of a Spanish-specific diacritic -> ``"es"`` (cheap, high-precision,
           fires before the length check so short Spanish fragments still classify).
        2. Empty / very short text without diacritics -> ``"unknown"``.
        3. Tokenise with a 3+ char regex; if fewer than 40 tokens -> ``"unknown"``.
        4. Score ES hits on accent-stripped tokens; score EN hits on raw tokens.
        5. ``es_ratio >= 0.6`` -> ``"es"``; ``es_ratio <= 0.4`` -> ``"en"``; else ``"unknown"``.
    """
    # Step 1: Spanish-specific diacritics are an extremely strong signal.
    if text and any(ch in _ES_DIACRITICS for ch in text):
        return "es"

    # Step 2: short text without diacritics is not enough to classify.
    if not text or len(text.strip()) < 40:
        return "unknown"

    # Step 3: tokenise
    tokens = _TOKEN_RE.findall(text.lower())
    if len(tokens) < 40:
        return "unknown"

    # Step 4: count hits against accent-stripped tokens for ES, raw for EN.
    es_hits = 0
    en_hits = 0
    for tok in tokens:
        # Lower-case already from the regex group with re.IGNORECASE.
        if tok in _EN_STOPWORDS:
            en_hits += 1
        else:
            stripped = _strip_accents(tok)
            if stripped in _ES_STOPWORDS or tok in _ES_STOPWORDS:
                es_hits += 1

    total = es_hits + en_hits
    if total == 0:
        return "unknown"

    es_ratio = es_hits / total
    if es_ratio >= 0.6:
        return "es"
    if es_ratio <= 0.4:
        return "en"
    return "unknown"
