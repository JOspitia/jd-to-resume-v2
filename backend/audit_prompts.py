"""
backend.audit_prompts
=====================

Builds the ATS-audit system prompt body, domain-aware per game.

Used by:
  * `/api/analyze-ats` (frontend-initiated audit on a freshly uploaded CV)
  * `_run_internal_audit` (auto re-audit fired by `/api/generate` after a
    forced translate-to-English flow).

Both call sites used to inline the same prompt body verbatim. This module
extracts that body so the per-game vocabulary (taxonomy + seed keywords)
is testable in isolation, without importing main.py (which transitively
pulls in fastapi, fitz, google.generativeai, etc).

Public API:
    build_audit_prompt(resume_text: str, jd_text: str, game) -> str
"""

from __future__ import annotations


# Per-game audit-prompt seeds.
# Each game picks a few realistic matched_keywords / missing_keywords so the
# LLM has concrete anchors in ITS domain and stops recommending tech-only
# tools (e.g. 'add Docker') on HR or Psychology CVs.
_AUDIT_SEEDS: dict[str, tuple[list[str], list[str]]] = {
    "tech": (
        ["Python", "FastAPI", "React", "SQL"],
        ["Docker", "Pytest", "CI/CD"],
    ),
    "hr_recruiting": (
        ["Workday", "LinkedIn Recruiter", "Entrevista por Competencias"],
        ["Greenhouse", "Boolean Search", "Sourcing Pipeline"],
    ),
    "psychology": (
        ["16PF", "Entrevista por Competencias", "consentimiento informado"],
        ["BDI-II", "psicoeducación", "TCC"],
    ),
}


def build_audit_prompt(resume_text: str, jd_text: str, game) -> str:
    """
    Compose the ATS-audit system prompt for a specific game.

    `game` is a `DomainGame` instance (see backend.domain_games). The prompt
    embeds the game's `label_es` and ES skill taxonomy so the LLM only
    emits matched_keywords, missing_keywords, and actionable_tips that
    belong to the selected domain.

    The JSON example in the prompt also injects per-game seed keywords so
    the response shape stays consistent while the vocabulary rotates.
    """
    audit_taxonomy_es = ", ".join(game.skill_taxonomy_es)
    seed_matched, seed_missing = _AUDIT_SEEDS.get(game.name, _AUDIT_SEEDS["tech"])

    return f"""
You are an expert Applicant Tracking System (ATS) auditor and recruitment AI analyst (like CompuTrabajo, Workday, and Greenhouse ATS screeners).
You are auditing a CV in the {game.label_es} domain. The expected skill taxonomy for this CV is: {audit_taxonomy_es}.
Your task is to analyze the candidate's Base Resume against the target Job Description (JD) or General Professional Standards if no JD is provided.

Perform 3 comprehensive evaluations:
1. ATS MATCH SCORE (%): Calculate direct keyword and skill alignment between the Resume and Job Description/Professional Standards, scoring against the {game.label_es} taxonomy listed above.
2. AI WRITING DETECTION SCORE (%): Analyze the writing style of the resume. Identify if it sounds natural/human or overly robotic/AI-generated (detect AI buzzwords like 'spearheaded revolutionary synergy', 'delved into', 'testament to', etc.). Provide a risk score (0-20% = Low AI Risk/Natural, 21-50% = Medium, 51-100% = High AI Risk) and advice to humanize the tone.
3. ATS FORMATTING & KEYWORD CHECK: Extract matched keywords, missing keywords, and actionable tips for ranking higher on platforms like CompuTrabajo. Match and missing keyword suggestions MUST belong to the {game.label_es} taxonomy — do not suggest tools/instruments unrelated to this domain (e.g. do NOT recommend 'add Docker' on a psychology or HR CV).

STRICT INSTRUCTION: Detect the language of the Job Description/Resume (e.g. Spanish). Generate ALL feedback, tips, and verdicts strictly in that language.

Respond ONLY with a JSON object in this exact structure:
{{
  "ats_score": 85,
  "match_level": "Alto",
  "matched_keywords": {seed_matched!r},
  "missing_keywords": {seed_missing!r},
  "ai_detection_score": 15,
  "ai_tone_verdict": "Bajo Riesgo de IA - Redacción Humana y Natural",
  "ai_humanize_tips": ["El lenguaje es directo, conciso y fácil de leer por reclutadores."],
  "ats_formatting_score": 95,
  "actionable_tips": [
    "Refuerza la presencia de keywords del dominio {game.label_es} en tus viñetas más relevantes.",
    "Destaca métricas cuantificables (números, %, tiempo, ahorro) en tus experiencias clave."
  ]
}}

Base Resume:
{resume_text}

Job Description / Requirements:
{jd_text}
"""


__all__ = ["build_audit_prompt"]
