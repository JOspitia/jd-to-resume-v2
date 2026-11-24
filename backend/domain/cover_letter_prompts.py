"""
backend.domain.cover_letter_prompts
==================================

Builds the prompt body for the cover-letter generator (``POST /api/cover-letter``).

Pure domain module — no infrastructure imports, same contract as
:mod:`domain.audit_prompts`. The LLM receives the candidate's real resume
text, the job description and the per-domain context, and answers with a
structured letter (salutation / opening / body paragraphs / closing /
signature).

Why a cover letter needs its own prompt instead of reusing the CV prompt
------------------------------------------------------------------------
A cover letter is NOT a shortened CV. The failure modes are different:

  * A CV prompt rewards keyword density; a letter that repeats the CV's
    bullet points is worse than no letter at all.
  * A CV prompt rewards completeness (education, projects, skills
    taxonomy); a letter needs a narrative arc that carries 2 or 3
    arguments, not an inventory.
  * A CV prompt's section labels do not apply; the unit of a letter is the
    paragraph.

So this module composes its own body: a letter-specific rule set, a
per-domain guidance paragraph (so a Psychology CV does not get a sales
pitch and a Tech CV does not get a therapy talk), and the tone / length /
language controls the UI exposes.

Per-domain guidance
-------------------
Mirrors the ``_AUDIT_SEEDS`` pattern of :mod:`domain.audit_prompts`: the
domain's own vocabulary comes from ``game.skill_taxonomy_es`` (so it stays
in sync with the game file automatically), and only the *angle* — what a
letter for this domain should emphasise — lives here.
"""

from __future__ import annotations


# --- Tone -------------------------------------------------------------------
# The UI exposes these four; anything else falls back to "professional".
_TONES: dict[str, str] = {
    "professional": (
        "Corporate but human. The register of a written letter to a hiring "
        "manager: measured, direct, no slang, no exclamation marks, no "
        "emojis. It should read as if a competent colleague wrote it."
    ),
    "persuasive": (
        "Confident and sales-oriented, but still credible. Lead with the "
        "strongest match to the vacancy, argue the candidate's case in two "
        "or three concrete sentences, and close with a clear statement of "
        "availability and interest. Every claim still has to be backed by "
        "the resume."
    ),
    "warm": (
        "Warm and personable, closer to how a person would actually write "
        "to a small team. Still professional, still concrete; the warmth "
        "shows in the phrasing, not in adjectives about the candidate."
    ),
    "concise": (
        "The shortest acceptable version. No throat-clearing, no summary of "
        "the resume. Every sentence must carry information the reader did "
        "not get from the CV alone."
    ),
}


# --- Length ----------------------------------------------------------------
# Word budget for the whole letter (salutation + body + closing).
_LENGTHS: dict[str, str] = {
    "short": "120-180 words. One paragraph of substance and a short close.",
    "medium": "220-320 words. The default: two or three body paragraphs.",
    "long": "350-450 words. Only for roles where the letter is expected to "
            "carry more argument (management, consulting, teaching roles).",
}


# --- Per-domain angle ------------------------------------------------------
# What the letter for this domain should emphasise, in one short paragraph.
# The *vocabulary* comes from the game's skill taxonomy; this only says
# which of it leads.
_COVER_LETTER_GUIDANCE: dict[str, str] = {
    "tech": (
        "This is a technical letter. Lead with the one or two problems the "
        "candidate has actually solved end to end, name the stack only when "
        "it is the reason the result happened, and quote the metric "
        "(latency, coverage, throughput, deployment frequency, incidents "
        "resolved). Do not turn the letter into a list of technologies. The "
        "reader's fear is 'this person only knows the buzzwords' — answer it "
        "with one specific story that shows ownership of a real system."
    ),
    "hr_recruiting": (
        "This is a people-process letter. Lead with the scale of the "
        "candidate's process (vacancies closed, candidates managed, time to "
        "fill), then with the quality of the work (structured interviews, "
        "assessment decisions the candidate owned, retention or onboarding "
        "outcomes). The reader is a recruiter or an HRBP: they want to know "
        "the candidate understands the funnel, not just that they 'love "
        "people'."
    ),
    "psychology": (
        "This is a clinical and ethical letter. Lead with the population "
        "the candidate actually served and the setting (clinic, school, "
        "organisation, community), then with the instruments and protocols "
        "they administered and the outcome they measured. The reader is a "
        "professional peer: precision about method matters more than "
        "enthusiasm, and no claim may exceed what the resume documents."
    ),
    "general": (
        "This is a service and commercial letter. Lead with what the "
        "candidate does for customers and how they are measured on it "
        "(people served, sales closed, targets met, shifts covered), then "
        "with the practical facts that decide shortlists in these roles "
        "(availability, weekends, city, mobility) when the resume supports "
        "them. Keep the language of the shop floor: short sentences, "
        "concrete nouns, no empty adjectives about being proactive or "
        "dynamic."
    ),
}


# --- Language override -----------------------------------------------------
# A short, letter-specific version of the CV pipeline's LANGUAGE OVERRIDE
# block (that one is full of CV section labels, so it does not apply here).
_LANGUAGE_OVERRIDE: dict[str, str] = {
    "en": (
        "LANGUAGE OVERRIDE (ABSOLUTE PRIORITY): the user explicitly chose "
        "English. Write the ENTIRE letter in English — salutation, body and "
        "closing — regardless of the language of the job description. Never "
        "mix languages. Keep proper nouns (company names, cities, "
        "certifications, tool names) in their original spelling."
    ),
    "es": (
        "LANGUAGE OVERRIDE (ABSOLUTE PRIORITY): el usuario eligió "
        "explicitamente el español. Escribe TODA la carta en español — "
        "saludo, cuerpo y cierre — sin importar el idioma de la vacante. "
        "Nunca mezcles idiomas. Conserva los nombres propios (empresas, "
        "ciudades, certificaciones) tal como aparecen."
    ),
}


def _tone_label(tone: str) -> str:
    """Normalise an unknown tone to the default and return its description."""
    return _TONES.get((tone or "").strip().lower(), _TONES["professional"])


def _length_label(length: str) -> str:
    """Normalise an unknown length to the default and return its budget."""
    return _LENGTHS.get((length or "").strip().lower(), _LENGTHS["medium"])


def _domain_guidance(game) -> str:
    """Per-domain angle, falling back to the generic guidance."""
    return _COVER_LETTER_GUIDANCE.get(
        getattr(game, "name", ""),
        "Write a letter for this professional domain using the vocabulary of "
        "the candidate's own experience. Never use vocabulary that belongs "
        "to another domain.",
    )


def build_cover_letter_prompt(
    resume_text: str,
    jd_text: str,
    game,
    *,
    target_role: str = "",
    company_name: str = "",
    tone: str = "professional",
    length: str = "medium",
    language: str = "auto",
    custom_instructions: str = "",
) -> str:
    """Compose the full prompt for one cover letter.

    Args:
        resume_text: the candidate's real resume text (PDF → plain text).
        jd_text: the job description. May be empty; the letter then leans on
            the resume and the stated target role.
        game: a ``DomainGame`` instance — supplies the label and the skill
            taxonomy that anchors the vocabulary.
        target_role: the role the candidate is applying to (free text).
        company_name: the company, when the user typed it. Used in the
            salutation and in the opening argument.
        tone: one of ``professional`` / ``persuasive`` / ``warm`` / ``concise``.
        length: one of ``short`` / ``medium`` / ``long``.
        language: ``auto`` (follow the JD), or an explicit ``es`` / ``en``.
        custom_instructions: free-text extra requirements from the user.

    Returns:
        The prompt string to hand to the LLM.
    """
    taxonomy = ", ".join(game.skill_taxonomy_es)
    tone_desc = _tone_label(tone)
    length_desc = _length_label(length)
    guidance = _domain_guidance(game)

    role_line = (target_role or "").strip() or "the advertised position"
    company_line = (company_name or "").strip()
    if company_line:
        company_block = f"Company the candidate is applying to: {company_line}"
        salutation_hint = (
            f"Address the letter to {company_line} "
            "(use 'Estimado equipo de [Empresa]' or a named contact only if "
            "the job description names one — never invent a person's name)."
        )
    else:
        company_block = "Company the candidate is applying to: not specified"
        salutation_hint = (
            "Address the letter to the hiring team in a neutral way "
            "('Estimado equipo de Selección:' or the equivalent in the "
            "letter's language). Never invent a company or a person's name."
        )

    language_block = ""
    normalized_language = (language or "auto").strip().lower()
    if normalized_language in _LANGUAGE_OVERRIDE:
        language_block = "\n" + _LANGUAGE_OVERRIDE[normalized_language] + "\n"
    else:
        language_block = (
            "\nLANGUAGE: Detect the dominant language of the job description "
            "and write the ENTIRE letter in that language (salutation, body "
            "and closing). If the job description is in Spanish, write in "
            "Spanish; if it is in English, write in English. Never mix "
            "languages in the same letter.\n"
        )

    custom_block = ""
    if custom_instructions and custom_instructions.strip():
        custom_block = (
            "\nADDITIONAL REQUIREMENTS FROM THE USER (they override the "
            "defaults above, but never the no-invention rule):\n"
            f"{custom_instructions.strip()}\n"
        )

    return f"""\
You are a professional writer who specializes in cover letters for job
applications in Latin America (Colombia, Mexico, Argentina, Spain, Chile).
You are given the candidate's real 'Base Resume' and the target 'Job
Description' (JD). You write ONE cover letter that a recruiter reads in
under a minute and that makes them want to call the candidate.

The letter is NOT a summary of the resume. It is an argument: this person
can do this job, and here is the evidence.

Target role: {role_line}
{company_block}

TONE FOR THIS LETTER: {tone_desc}
LENGTH FOR THIS LETTER: {length_desc}
{language_block}
DOMAIN CONTEXT: This is a letter in the {game.label_es} domain. The
candidate's real skill categories are: {taxonomy}. Use that vocabulary
(and only that vocabulary) when you name what the candidate brings.
{guidance}

STRICT RULES (CRITICAL — ALL MUST BE FOLLOWED):
1. ZERO HALLUCINATION: Use ONLY the companies, roles, dates, studies and numbers that appear in the Base Resume. Never invent an employer, a client, a certification, a metric, a salary, a hiring manager's name, a date or a project. If the resume does not say the candidate has experience with something, the letter must not claim it. A cover letter that lies is a cover letter that ends the candidacy.
2. THE LETTER MUST ADD SOMETHING THE CV DOES NOT SAY: the recruiter has the CV. The letter's job is to connect the candidate's real background to THIS vacancy. Do not list the resume section by section, do not repeat bullet points, and do not write "as you can see in my resume".
3. ARGUMENT, NOT INVENTORY: pick the TWO or THREE requirements that matter most in the job description and show the candidate's evidence for each one. A letter with one strong argument beats a letter with five weak ones.
4. NUMBERS: include one or two concrete figures from the resume (volume handled, percentage of a target, time reduced, people served, candidates managed, clients served). Keep the figure attached to its claim. Do not invent figures.
5. CONCRETE OVER GENERIC: name the actual work ("atendí a más de 120 clientes por día", "cerré 35 ventas mensuales", "reducí el tiempo de entrega de 3 a 1 día") instead of adjectives. BANNED unless the resume backs them: "persona dinámica y proactiva", "gran capacidad de adaptación", "excelente compromiso", "apasionado por el servicio", "orientado a resultados", "miembro destacado del equipo". Say what the person DID, not how impressive they are.
6. STRUCTURE — the output JSON fields are the letter:
   - 'salutation': one line that addresses the hiring team. {salutation_hint}
   - 'opening': two or three sentences. Why THIS vacancy and THIS company, and the single strongest thing the candidate brings to it. No "I am writing to apply for the position" filler — start from the match.
   - 'body': an array of TWO or three paragraphs. Each paragraph carries one argument and its evidence. Paragraphs are 3 to 5 sentences long.
   - 'closing': two or three sentences. Availability, willingness to talk, the practical facts the candidate can offer (schedule, city, mobility) WHEN the resume supports them, and a clear next step.
   - 'signature': the candidate's name followed by their contact line (phone and email) exactly as they appear in the resume. If the resume has no phone or email, keep only the name — never invent contact details.
7. PARAGRAPH FLOW: no headings, no bullet points, no markdown, no bold. Plain prose that reads as a continuous letter, in the same voice from the first sentence to the last.
8. NO META-COMMENTARY: never mention the ATS, the scoring, the AI, the job market, "this letter", "the position advertised on your site", or anything about the writing process. The candidate is writing to a person.
9. DO NOT ASK FOR A TEST OR A TASK, and do not ask the reader to contact the candidate "at my earliest convenience" — state availability plainly and close with a clear, low-friction next step.
10. DO NOT INCLUDE A REFERENCES SECTION, and do not mention that references are available on request.
11. HUMAN WRITING: vary the sentence length, avoid a repetitive structure across paragraphs, and avoid the AI-flavoured openings ("I am writing to express my interest", "In today's competitive landscape", "It is with great enthusiasm"). Write it the way a real candidate would, only with better punctuation.
12. FACT CHECK BEFORE ANSWERING: every sentence that names a skill, a tool, a number, a company or a date must be traceable to the Base Resume. If you cannot trace it, delete the sentence.
{custom_block}
Respond ONLY with a JSON object in this exact structure:
{{
  "salutation": "Estimado equipo de Selección:",
  "opening": "Two or three sentences that connect the candidate to this specific vacancy.",
  "body": ["First body paragraph, 3 to 5 sentences.", "Second body paragraph, 3 to 5 sentences."],
  "closing": "Two or three sentences: availability, practical facts, next step.",
  "signature": "Full Name\\n+57 300 000 0000\\nname@example.com"
}}

Base Resume:
{resume_text}

Job Description / Requirements:
{jd_text}
"""


__all__ = [
    "build_cover_letter_prompt",
    "_COVER_LETTER_GUIDANCE",
    "_TONES",
    "_LENGTHS",
]
