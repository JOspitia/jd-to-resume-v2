"""
backend.domain.translate_prompts
================================

Builds the prompt for the **faithful translation** mode: "translate my
CV to English without changing anything else".

Why a dedicated prompt instead of reusing the CV prompt
--------------------------------------------------------
``/api/generate`` is a *tailoring* pipeline. Its prompt tells the model
to rewrite every bullet point, restructure the experience, emphasise
what the job description asks for, and surface metrics that the source
never had. That is exactly what we do NOT want when the user asks for
a translation: they want the same CV, in another language, to apply
somewhere else.

So this mode gets its own prompt with the opposite contract:

    Translate the content. Change nothing else.

The output is the **same JSON schema** the CV pipeline produces, so the
existing renderers (RenderCV and the Playwright HTML fallback) can
render the result without knowing anything about translations.

What the prompt protects
------------------------
* **The structure.** Same sections, same order, same entries, same
  number of bullet points, in the same order.
* **The facts.** Numbers, dates, employers, job titles, degrees and
  URLs are carried over, not recomputed.
* **The contact block.** E-mail, phone and profile URLs are copied
  verbatim; a URL is never "translated".
* **The absence of tailoring.** There is no job description in this
  mode. Nothing may be reordered by relevance, reworded to sound
  better, or optimised for a role.

What it does translate
----------------------
* Every piece of prose: the summary, the bullet points, the skill
  categories and their items, the achievements, the section headings.
* Technical terms, into their standard English industry name
  ("reposicion" -> "restocking", not "re-positioning").
* Date markers: "Actualidad" -> "Present", "En curso" -> "In progress".
* Proper nouns — company names, universities, cities — stay as they
  are, because they are names.
"""

from __future__ import annotations


#: The generic English section headings. The domain games carry the same
#: set, but the translation mode must work without a domain (you can
#: translate a CV without saying what job you are chasing).
DEFAULT_SECTION_LABELS_EN: dict[str, str] = {
    "summary": "Professional Summary",
    "education": "Education",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "achievements": "Achievements",
    "portfolio": "Portfolio",
}


#: The output schema. It mirrors the one the CV pipeline asks for, so
#: the renderers can paint the result without a special case.
_JSON_SCHEMA = """{
  "name": "Jane Doe",
  "location": "Bogota, Colombia",
  "phone": "555-1234",
  "email": "jane@example.com",
  "portfolio": "",
  "linkedin": "",
  "github": "",
  "summary": "The candidate's own summary, translated. Same length, same meaning.",
  "education": [{"school": "Universidad Ejemplo", "degree": "BSc in Computer Science", "dates": "2018 - 2022", "gpa": ""}],
  "skills": [{"category": "Languages & Frameworks", "items": ["Python", "React"]}],
  "experience": [{"company": "Empresa Ejemplo", "role": "Backend Engineer", "dates": "2023-01 - Present", "points": ["First bullet, translated.", "Second bullet, translated."]}],
  "projects": [{"name": "Project Name", "dates": "2025-01", "url": "", "github_url": "https://github.com/user/repo", "points": ["Built X using Y"]}],
  "achievements": [],
  "section_labels": {
    "summary": "Professional Summary",
    "education": "Education",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "achievements": "Achievements",
    "portfolio": "Portfolio"
  }
}"""


def build_translation_prompt(
    resume_text: str,
    *,
    contact_header: dict | None = None,
    section_labels: dict | None = None,
    source_language: str = "unknown",
) -> str:
    """Compose the prompt for one faithful translation.

    Args:
        resume_text: the candidate's real resume text (PDF → plain text).
        contact_header: the contact fields extracted from the PDF. They
            are written into the prompt as protected values, exactly as
            the CV pipeline does, so the model cannot translate or
            "improve" a URL.
        section_labels: the English section headings to use. Defaults to
            :data:`DEFAULT_SECTION_LABELS_EN`.
        source_language: the detected language of the source resume, for
            the log line inside the prompt.

    Returns:
        The prompt string to hand to the LLM.
    """
    labels = {**DEFAULT_SECTION_LABELS_EN, **(section_labels or {})}
    labels_block = "\n".join(f'    "{key}": "{value}",' for key, value in labels.items())

    header = contact_header or {}
    email = header.get("email") or ""
    phone = header.get("phone") or ""
    linkedin = header.get("linkedin") or ""
    github = header.get("github") or ""
    portfolio = header.get("portfolio") or ""

    detected = source_language or "unknown"

    return f"""
You are a professional translator specialised in resumes and CVs. You
translate a candidate's CV into English. You are NOT a resume writer:
you do not improve, rewrite, shorten, expand or optimise anything.

The candidate's CV (source language detected as: {detected}) is given
below. Translate it into English.

THE ONE THING THAT MATTERS: EVERY TEXT IN YOUR ANSWER MUST BE IN
ENGLISH. Not the summary, not one bullet, not a job title, not a skill
category, not a degree. ALL of it. The rules below are about the
CONTENT of your translation — they are not an excuse to copy the
Spanish text through. A single Spanish sentence left in the output
makes the whole document wrong.

WHAT YOU MUST TRANSLATE — go through this list, item by item:
- the "summary" → English prose
- EVERY bullet of EVERY "experience" entry → English
- EVERY bullet of EVERY "projects" entry → English
- EVERY "skills" category name → English ("Lenguajes & Frameworks" →
  "Languages & Frameworks")
- EVERY skill item that is a Spanish phrase → English (a technology
  name like "Docker" stays as it is; "Automatización de pruebas" becomes
  "Test automation")
- EVERY job title ("Ingeniero TICs - QA" → "ICT Engineer - QA"; job
  titles are not names, translate them)
- EVERY degree or study title ("Máster Universitario en Dirección y
  Gestión de Tecnologías de la Información" → "Master's Degree in
  Management of Information Technologies")
- EVERY entry of "achievements" → English
- the "section_labels" → the English labels listed below

WHAT MUST NOT CHANGE — the content of your translation:
1. KEEP THE STRUCTURE EXACTLY. The same sections, in the same order.
   The same entries in each section, in the same order. The same number
   of bullet points per entry, in the same order. Do not merge two
   bullets into one, do not split one into two, do not add a bullet,
   do not drop a bullet, do not reorder anything. (Translate each of
   them — all of them.)
2. NO TAILORING. There is no job description and there is no target
   role. Do not reorder anything by relevance, do not emphasise one
   entry over another, do not rewrite anything to sound more impressive
   for any position. A recruiter reading the English version must find
   exactly the same CV they would find in the original language.
3. NO ADDITIONS AND NO INVENTIONS. Do not add achievements, metrics,
   skills, projects, certifications, employers, job titles, dates or
   responsibilities that are not in the input. Do not "complete" a
   bullet point that looks thin. Do not reformat a date into a
   different date. (Translate what is there — do not make more of it.)
4. KEEP EVERY FACT AS IT IS. Numbers, percentages, volumes, dates,
   company names, job titles, degrees, institutions and URLs are copied
   across unchanged. Translate the words around them, never the values.
5. DATES: keep the same format and the same values. Translate the
   markers only: "Actualidad" -> "Present", "En curso" -> "In progress",
   "Egresado" -> "Graduated", "Fecha" -> "Date".
6. CONTACT FIELDS ARE PROTECTED. Copy them verbatim.
   Never translate or reformat a URL, an e-mail address or a phone number:
   - email: {email}
   - phone: {phone}
   - linkedin: {linkedin}
   - github: {github}
   - portfolio: {portfolio}
   If one of them is empty, leave it empty. Never invent one.
7. PROPER NOUNS STAY AS THEY ARE: company names, university names,
   city names, product names and people's names are names, not words to
   translate. (A job title is not a name — see the list above.)
8. TECHNICAL TERMS use their standard English industry name, not a
   literal translation ("reposicion" -> "restocking", "caja" -> "cash
   handling", "soporte" -> "support", "mantenimiento" -> "maintenance").
   Keep the candidate's own level of detail — do not upgrade "worked
   with" into "specialised in".
9. THE SUMMARY IS TRANSLATED, NOT REWRITTEN. Keep its length and its
   content. Do not make it punchier.
10. SKILL CATEGORIES keep the same categories, in the same order, with
    the same items. Translate the category name into its English
    equivalent and translate each item, but never regroup the items,
    never add a technology the CV does not mention and never drop one.
11. SECTION LABELS must be exactly these:
{labels_block}
    Use the English labels for every section. Do not use Spanish ones.
12. CERTIFICATIONS, AWARDS AND HONOURS: the output schema has an
    "achievements" array for them. If the source has a section called
    "Certificaciones", "Logros", "Premios", "Reconocimientos",
    "Certifications", "Awards" or "Honors", put EVERY entry of it in the
    "achievements" array, translated, in the same order. Leave the array
    empty only when the source really has no such entry. Dropping a
    certification is a content loss, not a translation.

FINAL CHECK, before you answer: read your own JSON and look for any
Spanish word left in it. Translate it. The answer must be readable by
someone who speaks no Spanish.

Respond ONLY with a JSON object in this exact structure:
{_JSON_SCHEMA}

Base Resume (source language: {detected}):
{resume_text}
"""


__all__ = [
    "build_translation_prompt",
    "DEFAULT_SECTION_LABELS_EN",
]
