"""
backend.domain.translation_facts
=================================

Detects text that the translation mode left in the source language.

Why this module exists
----------------------
The translation prompt is emphatic about keeping the content intact, and
models over-apply that: "keep everything the same, change nothing" reads
as *copy the input*. The first run of the mode translated the section
headings (the prompt spells those out literally) and the summary (it was
already in English in the source PDF) — and left **every bullet, every
job title, every skill category, every degree and every achievement in
Spanish**. The prompt was not wrong; it was outnumbered.

So the language of the output is now verified mechanically, the same way
the cover letter's figures are: the prompt asks for English, and the
backend checks.

How the detection works
-----------------------
Not with a document-level classifier — that is the wrong granularity. A
single bullet point is a handful of words, and a document classifier
needs a document. What matters is whether *this string* contains
Spanish, so the detector looks for **high-signal Spanish function
words** that do not occur in English technical prose:

    "desarrollo", "gestión", "años", "clientes", "sistemas", ...

Two categories are deliberately excluded:

* **Proper nouns.** "Universidad de La Rioja", "Proyectos de Ingeniería
  Proing S.A." are names. Translating them would be wrong. The detector
  skips fields that are names (school, company) and only looks at the
  prose fields.
* **Short fields.** A skill item ("Docker", "Scrum") or a date has no
  language to detect. The detector only judges fields long enough to
  carry a sentence.

What the caller does with the result
-------------------------------------
1. One **corrective retry** with the offending strings quoted back.
2. If the model insists, a **targeted second pass** that translates
   only the leftover strings — a tiny job the model cannot get wrong by
   losing focus in a long document.
3. If that also fails, the original text is kept (no data loss) and the
   leftovers are reported to the caller.
"""

from __future__ import annotations

import re
from typing import Any, Iterable


#: High-signal Spanish words. Function words, infinitive endings and
#: domain nouns that are not English words. Kept short on purpose: a
#: wrong positive costs one extra retry, a missed one costs an
#: untranslated CV.
SPANISH_MARKERS = frozenset(
    {
        # Function words
        "de", "del", "la", "las", "los", "el", "un", "una", "unos", "unas",
        "con", "para", "por", "que", "como", "más", "pero", "sin", "sobre",
        "entre", "desde", "hasta", "cuando", "donde", "porque", "muy",
        "todo", "toda", "todos", "todas", "otro", "otra", "este", "esta",
        "esto", "eso", "aun", "cada", "casi", "solo", "sólo",
        # Verbs (accented forms and common inflections)
        "desarrollo", "desarrollé", "desarrolló", "desarrollamos",
        "implementé", "implementó", "implementamos", "construí", "construyó",
        "lideré", "lideró", "diseñé", "diseñó", "reduje", "redujo",
        "aumenté", "aumentó", "incrementé", "incrementó", "automaticé",
        "automaticó", "integré", "integró", "configuré", "configuró",
        "optimicé", "optimizó", "coordino", "coordiné", "reporté",
        "reportó", "participé", "participó", "validé", "validó",
        "gestión", "gestiono", "administro", "administré", "analicé",
        "analizó", "evalué", "evaluó", "seleccioné", "seleccionó",
        "búsqueda", "busqué", "identifiqué", "identificó",
        # Nouns that are not English words
        "años", "año", "meses", "mes", "días", "día", "semana", "semanas",
        "experiencia", "experiencias", "formación", "educación",
        "habilidades", "conocimientos", "perfil", "empresa", "empresas",
        "proyecto", "proyectos", "sistema", "sistemas", "aplicación",
        "aplicaciones", "clientes", "usuario", "usuarios", "equipo",
        "equipos", "proceso", "procesos", "servicio", "servicios",
        "soporte", "mantenimiento", "operación", "operaciones",
        "estrategia", "estrategias", "objetivo", "objetivos",
        "resultados", "indicadores", "reportes", "informes",
        "capacitación", "certificación", "certificaciones",
        # Job titles and study titles (they are translated, they are not names)
        "ingeniero", "ingeniera", "analista", "desarrollador", "desarrolladora",
        "técnico", "técnica", "científico", "científica", "investigador",
        "investigadora", "coordinador", "coordinadora", "supervisor",
        "lenguajes", "automatización", "seguridad", "móvil", "móviles",
        "formación", "complementaria", "curso", "certificado", "cursando",
        "nivel", "idiomas", "título", "profesional", "grado", "honores",
        "dirección", "gestión", "tecnologías", "información", "administrador",
        "administradora", "auditor", "auditora", "asesor", "asesora",
        "inteligencia", "diplomado", "postgrado", "licenciatura",
        "especialización", "maestría", "y",
        # Common accent-bearing words that mark a Spanish sentence
        "informática", "ingeniería", "administración", "continuidad",
        "operativa", "normativo", "acompañamiento", "área",
        "áreas", "tecnología", "tecnologías", "médicos", "farmacia",
        "facturación", "admisiones", "hospitalización", "pruebas",
        "automatizadas", "módulos", "prácticas", "ágiles", "detección",
        "producción", "priorizando", "fallos", "técnicos", "colaboración",
        "consultoría", "aplicaciones", "móviles", "nativas",
        "arquitectura", "microservicios", "integrada", "infraestructura",
        "existente", "escalabilidad", "disminuyendo", "tiempos",
        "despliegue", "planificación", "técnica", "requerimientos",
        "definiendo", "alinear", "soluciones", "necesidades", "negocio",
    }
)

#: English function words that would otherwise look like Spanish markers.
_ENGLISH_LOOKALIKES = frozenset({"a", "in", "on", "at", "to", "of", "or"})

#: Minimum number of words for a field to be judged. Below this the
#: field is a tool name ("Docker", "Power BI") or a date — there is no
#: language to detect. The marker list, not this threshold, is what
#: prevents false positives: two English words never contain a Spanish
#: function word.
_MIN_WORDS = 2

_WORD_RE = re.compile(r"[A-Za-zÁÉÍÓÚÜÑáéíóúüñ]+")


def spanish_markers_in(text: str) -> list[str]:
    """The Spanish function words found in ``text`` (deduplicated).

    Args:
        text: the string to inspect.

    Returns:
        The markers found, in order of appearance. Empty means "no
        Spanish signal here".
    """
    if not text:
        return []
    found: list[str] = []
    for raw in _WORD_RE.findall(text):
        token = raw.lower()
        if token in _ENGLISH_LOOKALIKES:
            continue
        if token in SPANISH_MARKERS and token not in found:
            found.append(token)
    return found


def is_untranslated(text: str) -> bool:
    """True when ``text`` still carries Spanish.

    Only fields long enough to hold a sentence are judged: a skill name
    or a date has no language, and a one-word company name would be a
    false positive every time.
    """
    if not text or not text.strip():
        return False
    words = text.split()
    if len(words) < _MIN_WORDS:
        return False
    return bool(spanish_markers_in(text))


def _walk(value: Any, path: str) -> Iterable[tuple[str, str]]:
    """Yield ``(path, text)`` for every prose string in the parsed CV.

    Names are skipped on purpose: a school, a company or a project name
    is a proper noun and stays as it is.
    """
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _walk(item, f"{path}[{index}]")
    elif isinstance(value, dict):
        for key, item in value.items():
            if key in _NAME_FIELDS:
                continue
            child = f"{path}.{key}" if path else key
            yield from _walk(item, child)


#: Fields whose value is a proper noun.
_NAME_FIELDS = frozenset(
    {
        "name",
        "school",
        "company",
        "location",
        "portfolio",
        "linkedin",
        "github",
        "email",
        "phone",
        "url",
        "github_url",
        "section_labels",
    }
)


def find_untranslated_fields(parsed_data: dict) -> dict[str, str]:
    """Every field of the parsed CV that is still in Spanish.

    Args:
        parsed_data: the JSON the model returned for the CV.

    Returns:
        A mapping of dotted path to the offending text. Empty when the
        whole document came back in the target language.
    """
    offenders: dict[str, str] = {}
    for path, text in _walk(parsed_data, ""):
        if is_untranslated(text):
            offenders[path] = text
    return offenders


def build_targeted_prompt(offenders: dict[str, str]) -> str:
    """A prompt that translates only the strings that were left behind.

    A focused job is a job the model gets right: the previous attempt
    failed because the translation of a whole document is a big ask, and
    the model chose to copy. Here the input is a handful of strings and
    the instruction is a single verb.

    Args:
        offenders: the path → Spanish text mapping to fix.

    Returns:
        The prompt to send to the LLM. The expected answer is a JSON
        object with the same keys and the English text as values.
    """
    listing = "\n".join(f'  "{path}": {json_escape(text)}' for path, text in offenders.items())
    return f"""
Some strings of the CV were left in Spanish. Translate them into
English and return ONLY a JSON object with exactly these keys, where each
value is the English translation of the Spanish text under that key.

Rules:
- Translate every value. Keep the meaning, the level of detail and the
  order of the words the same.
- Keep every number, name, technology and URL exactly as they are.
- Do not add, drop or merge anything. One value in, one value out.
- Keep the JSON keys identical. Return no other key and no commentary.

Strings to translate:
{listing}
"""


def json_escape(text: str) -> str:
    """Quote a string for the targeted prompt's JSON-ish listing."""
    import json as _json

    return _json.dumps(text, ensure_ascii=False)


_PATH_TOKEN_RE = re.compile(r"([^.\[\]]+)|\[(\d+)\]")


def set_path(data: Any, path: str, value: str) -> bool:
    """Write ``value`` at ``path`` inside the parsed CV.

    The paths come from :func:`find_untranslated_fields` and look like
    ``summary``, ``experience[0].role`` or ``skills[2].category``.

    Args:
        data: the parsed CV (mutated in place).
        path: the dotted/indexed path.
        value: the text to write.

    Returns:
        True when the value was written, False when the path does not
        exist in the document.
    """
    tokens: list[Any] = []
    for name, index in _PATH_TOKEN_RE.findall(path):
        tokens.append(name if name else int(index))
    if not tokens:
        return False

    current = data
    for token in tokens[:-1]:
        try:
            current = current[token]
        except (KeyError, IndexError, TypeError):
            return False

    last = tokens[-1]
    try:
        if isinstance(last, int):
            if last >= len(current):
                return False
            if not isinstance(current[last], str):
                return False
            current[last] = value
        else:
            if last not in current:
                return False
            # Only a string may be replaced by a string. Without this, a
            # model that answers with the whole CV instead of the
            # path → text map would overwrite a whole list with a string.
            if not isinstance(current[last], str):
                return False
            current[last] = value
    except (KeyError, IndexError, TypeError):
        return False
    return True


def strip_degree_markers(parsed_data: dict) -> dict:
    """Remove the RenderCV ``in`` marker that leaks from the source PDF.

    RenderCV prints "in" before a degree ("in BSc Computer Science"), so
    the extracted text of a RenderCV CV contains it. A model that copies
    the text faithfully brings the marker along, and the renderer adds
    its own on top: the CV then reads "in in Bachelor's Degree".

    Args:
        parsed_data: the parsed CV (mutated in place).

    Returns:
        The same dict, for chaining.
    """
    education = parsed_data.get("education")
    if not isinstance(education, list):
        return parsed_data
    for entry in education:
        if not isinstance(entry, dict):
            continue
        degree = entry.get("degree")
        if not isinstance(degree, str):
            continue
        cleaned = degree.strip()
        while cleaned.lower().startswith("in "):
            cleaned = cleaned[3:].strip()
        if cleaned != degree:
            entry["degree"] = cleaned
    return parsed_data


__all__ = [
    "SPANISH_MARKERS",
    "build_targeted_prompt",
    "find_untranslated_fields",
    "is_untranslated",
    "set_path",
    "spanish_markers_in",
    "strip_degree_markers",
]
