"""YAML editor service: parsing, schema validation, content-drift guard,
and LLM-driven structural repair.

Pulled out of ``main.py`` during the hexagonal split. The three HTTP
endpoints in ``routes/yaml_editor_router.py`` (render-from-yaml,
analyze-yaml, repair-yaml) call into this module — the router stays a
thin FastAPI wrapper.

Public surface:

* :func:`parse_yaml_safe`               — tolerant syntactic parse
* :func:`validate_yaml_schema`          — Pydantic-backed schema check
* :func:`content_tokens`                — tokeniser used by drift check
* :func:`content_drift`                 — semantic-drift guard
* :func:`strip_yaml_fences`             — strip YAML markdown fences
* :class:`YamlEditorService`            — LLM-backed ``repair_yaml`` flow

Helpers are pure (no infra imports except ``yaml`` and the
``GeminiResumeOutput`` Pydantic schema). The service class wraps the
LLM call via the existing ``LLMOrchestrator`` service, so swapping the
provider cascade stays a composition-root concern.
"""

from __future__ import annotations

import re
from typing import Any, Optional

import yaml as _pyyaml
from pydantic import TypeAdapter as _TypeAdapter, ValidationError

from schemas.api_models import GeminiResumeOutput
from application.services.llm_orchestrator import LLMOrchestrator
from yaml_helpers import (
    serialize_resume_data_as_text as _serialize_resume_data_as_text,
    yaml_safe_dump_unicode as _yaml_safe_dump_unicode,
)


# ---------------------------------------------------------------------------
# YAML schema prompt template. Used by the LLM repair step.
# ---------------------------------------------------------------------------

_YAML_SCHEMA_DESCRIPTION = """
{
  "name": "Full Name (string)",
  "location": "City, Country (string)",
  "phone": "Phone Number (string)",
  "email": "Email Address (string)",
  "portfolio": "Portfolio URL (string)",
  "linkedin": "LinkedIn URL (string)",
  "github": "GitHub URL (string)",
  "summary": "Concise professional summary (string)",
  "education": [
    {
      "school": "string",
      "degree": "string",
      "dates": "string (e.g. '2020 - 2024' or '2018-01 - Presente')",
      "gpa": "string (optional)"
    }
  ],
  "skills": [
    { "category": "string (e.g. 'Backend', 'Bases de Datos')", "items": ["tool1", "tool2"] }
  ],
  "experience": [
    {
      "company": "string",
      "role": "string",
      "dates": "string",
      "points": ["Achievement 1", "Achievement 2", "Achievement 3"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "dates": "string",
      "url": "string (live demo URL — optional)",
      "github_url": "string (repo URL — optional)",
      "points": ["Achievement 1", "Achievement 2"]
    }
  ],
  "achievements": ["Award 1", "Certification 2"],
  "section_labels": {
    "summary": "string (e.g. 'Resumen Profesional')",
    "education": "string",
    "skills": "string (e.g. 'Habilidades')",
    "experience": "string",
    "projects": "string",
    "achievements": "string",
    "portfolio": "string"
  }
}

CRITICAL RULES (your output MUST honor):
1. Output ONLY a valid YAML document. No prose, no ``` fences, no comments.
2. lists MUST be YAML lists (lines starting with `- `), not inline `[a, b, c]`.
3. Strings inside lists MUST be quoted with double quotes if they contain
   colons, hashes, or special YAML characters.
4. NEVER invent new top-level keys. NEVER drop required keys.
5. Preserve all present candidate facts verbatim (real names, dates, schools,
   tool names, metrics). Only fix structure, indentation, and types.
"""


# ---------------------------------------------------------------------------
# Pure helpers — no infra dependency, testable in isolation.
# ---------------------------------------------------------------------------


def parse_yaml_safe(text: str) -> tuple[Optional[dict], Optional[str]]:
    """Parse YAML safely and return ``(parsed, error)``.

    ``parsed`` is ``None`` when the text is empty or fails to parse.
    ``error`` is the exception message string when parsing failed, else
    ``None``. A successful parse with an empty / scalar document yields
    ``({}, None)`` — the schema layer decides whether that's valid.
    """
    if not text or not text.strip():
        return None, "Empty YAML document"
    try:
        loaded = _pyyaml.safe_load(text)
    except _pyyaml.YAMLError as ye:
        return None, str(ye)
    if loaded is None:
        return {}, None
    if not isinstance(loaded, dict):
        return None, f"Expected a YAML mapping at the top level, got {type(loaded).__name__}"
    return loaded, None


def validate_yaml_schema(parsed: dict) -> tuple[Optional[dict], Optional[str]]:
    """Validate ``parsed`` against :class:`GeminiResumeOutput`.

    Returns ``(cleaned, error)``. ``cleaned`` is the Pydantic model dump
    (canonical field set, types normalised) on success, else ``None``.
    ``error`` is the joined validation message on failure, else ``None``.
    """
    try:
        model = GeminiResumeOutput(**parsed)
    except ValidationError as ve:
        return None, "; ".join(
            f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}"
            for err in ve.errors()
        )
    return model.model_dump(), None


def _valid_field_subset(parsed: dict) -> dict:
    """Return the subset of ``parsed`` whose values pass per-field type validation.

    Used to build a drift baseline that only covers the candidate's
    real facts. When the original is schema-invalid (e.g. a broken
    ``education: not-a-list`` placeholder), the invalid fields are
    excluded from the baseline — they're garbage the LLM was
    explicitly asked to replace, not facts to preserve — while fields
    the user filled correctly (e.g. ``name: Jane Doe``) still anchor
    the drift check.

    Per-field validation goes through ``TypeAdapter(field.annotation)``
    so each top-level key is checked against its declared type
    independently — one bad field does not exclude the others, and
    required-field-missing-on-whole-doc doesn't mask a valid isolated
    value.
    """
    safe: dict = {}
    fields = getattr(GeminiResumeOutput, "model_fields", {})
    for key, value in parsed.items():
        if key not in fields:
            # Unknown key — pydantic ignores extras by default; treat
            # as a fact the user wrote (e.g. ``location``, ``section_labels``).
            safe[key] = value
            continue
        annotation = fields[key].annotation
        try:
            _TypeAdapter(annotation).validate_python(value)
        except ValidationError:
            # Field invalid on its own (wrong type, shape mismatch) —
            # skip; the LLM is being asked to fix it.
            continue
        safe[key] = value
    return safe


def content_tokens(text: str) -> set[str]:
    """Extract the meaningful tokens (words, numbers) from a YAML-like text.

    Numbers are kept at any length (the older ``{3,}`` threshold silently
    dropped ``30%``, ``40``, ``15`` — exactly the metrics that a sloppy
    LLM repair would change). Words keep the 3-character floor to suppress
    noise while still capturing accented letters used throughout Spanish.
    """
    # Drop line-leading list markers so ``- Python`` and ``Python`` tokenize
    # alike.
    cleaned = re.sub(r"^\s*-\s+", " ", text, flags=re.MULTILINE)
    numbers = re.findall(r"\d+(?:[.,]\d+)*", cleaned)
    words = re.findall(r"[^\W\d_]{3,}", cleaned, flags=re.UNICODE)
    return {w.lower() for w in words} | {n for n in numbers}


def content_drift(original: str, repaired: str) -> Optional[str]:
    """Return a human-readable drift report if the LLM repair altered text.

    ``None`` when the two texts agree on the candidate's content tokens.
    Returns a reason string (``"...perdió 1 dato de tu texto (30%)..."``)
    when content was lost or invented. Numbers (including bare percentages
    and counts) are tracked at any length so a metric swap — the single
    most damaging edit an LLM could make to a CV — is always flagged.
    """
    if original is None or repaired is None:
        return None
    if not content_tokens(original):
        return None
    if original.strip() == repaired.strip():
        return None

    before = content_tokens(original)
    after = content_tokens(repaired)

    # A word the user split across two lines (``selecci\n  ón``) is rejoined
    # by the repair, so test substring presence against a whitespace-stripped
    # blob instead of exact token equality.
    after_flat = re.sub(r"\s+", "", repaired).lower()

    lost = sorted(w for w in before if w not in after and w not in after_flat)
    if lost:
        sample = ", ".join(lost[:8])
        # A lost number is a changed metric; a lost word is a rephrasing.
        has_number = any(any(ch.isdigit() for ch in w) for w in lost)
        noun = "dato" if has_number else ("palabra" if len(lost) == 1 else "palabras")
        return (
            f"la reparación cambió o perdió {len(lost)} "
            f"{'datos' if has_number and len(lost) > 1 else noun} de tu texto "
            f"({sample}{'…' if len(lost) > 8 else ''})"
        )

    # A pure syntax fix (indentation, quoting, list markers, colons) adds
    # zero tokens by definition. Anything new is invented content.
    added = sorted(after - before)
    if added:
        sample = ", ".join(added[:8])
        noun = "palabra" if len(added) == 1 else "palabras"
        verb = "estaba" if len(added) == 1 else "estaban"
        return (
            f"la reparación agregó {len(added)} {noun} que no {verb} en tu texto "
            f"({sample}{'…' if len(added) > 8 else ''})"
        )

    return None


def strip_yaml_fences(text: str) -> str:
    """Strip leading/trailing markdown code fences from ``text``.

    LLMs frequently answer with::

        ```yaml
        name: ...
        ```

    The repair step must accept that shape.
    """
    if text is None:
        return ""
    t = text.strip()
    if t.startswith("```"):
        # Drop the first line (``\`\`\`yaml`` or ``\`\`\```)
        first_nl = t.find("\n")
        if first_nl != -1:
            t = t[first_nl + 1:]
        # Drop the trailing ``\`\`\```
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return t


# ---------------------------------------------------------------------------
# LLM-backed repair service.
# ---------------------------------------------------------------------------


class YamlEditorService:
    """Two-pass YAML repair: local validation, then LLM-driven fix.

    Each pass asks the LLM to fix structure only — the content-drift
    guard runs after every repair and aborts the operation if the LLM
    rewrote the candidate's facts. The service returns a JSON envelope
    matching the original endpoint contract so callers can distinguish
    "no repair needed" from "LLM fixed it" from "could not fix".
    """

    def __init__(self, llm_orchestrator: LLMOrchestrator) -> None:
        self._llm = llm_orchestrator

    async def ask_llm_to_repair(
        self,
        broken_yaml: str,
        schema_errors: list[str],
        domain_game: Optional[str],
    ) -> str:
        """Invoke the LLM cascade to repair ``broken_yaml``."""
        game_hint = (
            f"\n\nTarget domain: {domain_game!r}. Honour that domain's "
            "vocabulary in section_labels."
            if domain_game
            else ""
        )
        prompt = (
            "You are a strict YAML repair agent. The following YAML is "
            "either syntactically broken or fails schema validation. "
            "Output ONLY the repaired YAML document — no prose, no "
            "markdown fences, no surrounding JSON envelope.\n\n"
            "Hard rules:\n"
            "  * Use block-style YAML (indentation + lists with ``-``), "
            "not JSON braces.\n"
            "  * Keep every existing key name exactly as-is. Do NOT "
            "rename, abbreviate, prefix (``nname``, ``nemail``), or "
            "wrap keys.\n"
            "  * Preserve every fact from the original: names, dates, "
            "metrics, project titles, skills. Fix structure, never "
            "content.\n"
            "  * Add ONLY fields required by the schema to satisfy the "
            "validation errors. If the original has no data for a "
            "required field, leave it as an empty list/string per the "
            "schema — do not invent values.\n\n"
            f"Target schema:\n{_YAML_SCHEMA_DESCRIPTION}\n\n"
            f"Errors to address:\n- " + "\n- ".join(schema_errors)
            + f"\n\nYAML to repair:\n```yaml\n{broken_yaml}\n```"
            + game_hint
        )
        return await self._llm.complete(prompt)

    async def repair(
        self,
        yaml_content: str,
        domain_game: Optional[str],
    ) -> dict:
        """Two-pass repair; returns the original endpoint envelope shape.

        Shape::

            {
              "ok": bool,
              "yaml": str,
              "repairs": list[str],
              "schema_errors": list[str],
              "error": str | missing if ok,
            }
        """
        try:
            original_yaml = yaml_content
            repairs: list[str] = []

            # The latest schema-validated dict. Drift comparison runs against
            # ``_yaml_safe_dump_unicode(current_cleaned)`` — the canonical
            # YAML — not the raw LLM text. Why: the LLM often answers in
            # JSON-style YAML (still valid YAML, but with quote/brace noise
            # tokens like ``content``, ``json``) or sprinkles ``n``-prefixed
            # mirror keys next to the real ones (``nachievements`` next to
            # ``achievements``) that Pydantic accepts as ``extras`` and
            # silently drops from ``model_dump()``. Comparing drift against
            # the raw LLM string would flag those formatting artefacts as
            # fabricated data and abort every time; comparing against the
            # canonical cleaned dict compares *semantic* content only.
            current_cleaned: Optional[dict] = None
            # Whether any pass had to call the LLM. The final drift check
            # is skipped when no LLM was called: the only "change" then is
            # the YAML re-normalisation (block vs JSON style), and any
            # extras the user typed (``location``, ``section_labels``,
            # etc.) that the schema silently drops would otherwise trip
            # the guard on every valid input.
            llm_called: bool = False

            # Pass 1 — local syntactic validation
            parsed, syntax_err = parse_yaml_safe(original_yaml)
            if syntax_err or parsed is None:
                repairs.append(f"Local validation rejected the YAML: {syntax_err}")
                llm_called = True
                llm_response = await self.ask_llm_to_repair(
                    original_yaml, [syntax_err or "unknown syntax error"], domain_game,
                )
                llm_yaml = strip_yaml_fences(llm_response)
                parsed2, syntax_err2 = parse_yaml_safe(llm_yaml)
                if syntax_err2 or parsed2 is None:
                    return {
                        "ok": False,
                        "yaml": llm_yaml,
                        "repairs": repairs + [f"LLM still returned invalid YAML: {syntax_err2}"],
                        "schema_errors": [syntax_err2 or "yaml.safe_load failed"],
                        "error": (
                            f"La IA no pudo producir YAML con sintaxis válida. "
                            f"Editá el YAML manualmente. Error del parser: {syntax_err2 or 'yaml.safe_load failed'}"
                        ),
                    }
                repairs.append("LLM produced valid YAML syntax.")
                yaml_text = llm_yaml
                parsed = parsed2
                # Compare against canonical YAML from the parsed dict so
                # JSON-style answers don't trip the guard on quote/brace
                # noise tokens.
                drift = content_drift(original_yaml, _yaml_safe_dump_unicode(parsed2))
                if drift:
                    return {
                        "ok": False,
                        "yaml": original_yaml,
                        "repairs": repairs,
                        "schema_errors": [f"El texto fue modificado: {drift}"],
                        "error": (
                            f"La IA reparó la sintaxis pero {drift}. "
                            f"Se devolvió tu texto original sin tocar — corregí la sintaxis a mano."
                        ),
                    }
                repairs.append("Texto verificado: sin cambios de contenido.")
            else:
                yaml_text = original_yaml

            # Pass 2 — schema validation
            cleaned, schema_err = validate_yaml_schema(parsed)
            current_cleaned = cleaned
            if schema_err or cleaned is None:
                repairs.append(f"Local schema check rejected the YAML: {schema_err}")
                llm_called = True
                llm_response = await self.ask_llm_to_repair(
                    yaml_text, [schema_err or "unknown schema error"], domain_game,
                )
                llm_yaml = strip_yaml_fences(llm_response)
                parsed2, syntax_err2 = parse_yaml_safe(llm_yaml)
                if syntax_err2 or parsed2 is None:
                    return {
                        "ok": False,
                        "yaml": llm_yaml,
                        "repairs": repairs + [f"LLM returned YAML that still fails syntax: {syntax_err2}"],
                        "schema_errors": [syntax_err2 or "yaml.safe_load failed"],
                        "error": (
                            f"La IA no pudo arreglar la sintaxis del YAML. "
                            f"Error del parser: {syntax_err2 or 'yaml.safe_load failed'}"
                        ),
                    }
                cleaned2, schema_err2 = validate_yaml_schema(parsed2)
                if schema_err2 or cleaned2 is None:
                    return {
                        "ok": False,
                        "yaml": llm_yaml,
                        "repairs": repairs + ["LLM returned YAML that still fails schema validation."],
                        "schema_errors": [schema_err2 or "schema validation failed"],
                        "error": (
                            f"La IA no pudo arreglar el schema del YAML. "
                            f"Editá manualmente. Error de schema: {schema_err2 or 'schema validation failed'}"
                        ),
                    }
                repairs.append("LLM produced YAML that passes schema validation.")
                yaml_text = llm_yaml
                current_cleaned = cleaned2
                # Compare the user's *valid* fields against the LLM's
                # same fields. Both sides are filtered through the
                # valid-field subset: the LLM gets full license to
                # repair broken fields (``achievements: Speaker at
                # PyCon`` -> list of strings, etc.), but the fields the
                # user wrote correctly must come back unchanged.
                #
                # Extras the LLM sprinkles in (``n``-prefixed mirror
                # keys, ``content`` / ``json`` envelope pair) are
                # dropped by ``model_dump()`` here on the LLM side;
                # they never enter the comparison.
                valid_keys = (
                    set(cleaned.keys())
                    if cleaned is not None
                    else set(_valid_field_subset(parsed).keys())
                )
                llm_subset = {k: v for k, v in cleaned2.items() if k in valid_keys}
                if cleaned is not None:
                    user_subset = cleaned
                else:
                    user_subset = _valid_field_subset(parsed)
                drift = content_drift(
                    _yaml_safe_dump_unicode(user_subset),
                    _yaml_safe_dump_unicode(llm_subset),
                )
                if drift:
                    return {
                        "ok": False,
                        "yaml": original_yaml,
                        "repairs": repairs,
                        "schema_errors": [f"El texto fue modificado: {drift}"],
                        "error": (
                            f"La IA reparó la estructura pero {drift}. "
                            f"Se devolvió tu texto original sin tocar — corregí a mano."
                        ),
                    }
                repairs.append("Texto verificado: sin cambios de contenido.")

            # Re-serialize through the schema-cleaned dict (when available)
            # so the output is ALWAYS block-style and excludes LLM artefacts.
            # Falls back to the LLM text only when there's no cleaned dict
            # (shouldn't happen post-pass-2, but defensive).
            try:
                if current_cleaned is not None:
                    normalized = _yaml_safe_dump_unicode(current_cleaned)
                else:
                    normalized = _yaml_safe_dump_unicode(_pyyaml.safe_load(yaml_text))
                if normalized.strip() != yaml_text.strip():
                    repairs.append("Re-formateado a YAML legible (bloques y saltos de línea).")
                yaml_text = normalized
            except Exception as fmt_err:  # noqa: BLE001 — best-effort reformat
                print(f"[WARN] Could not normalize repaired YAML formatting: {fmt_err}")

            # Final drift safety net. Skipped when no LLM was called: in that
            # case the only "change" is YAML re-normalisation (block vs
            # JSON style) plus schema-side extras-drop, and the per-pass
            # drift check above already covered every LLM contribution.
            # When the original was schema-invalid we use the partial
            # valid-fields subset as baseline (both sides) so user facts
            # still anchor the check.
            if not llm_called:
                final_drift = None
            elif cleaned is not None:
                final_drift = content_drift(
                    _yaml_safe_dump_unicode(cleaned),
                    yaml_text,
                )
            else:
                valid_keys = set(_valid_field_subset(parsed).keys())
                llm_subset_final = {
                    k: v for k, v in (current_cleaned or {}).items() if k in valid_keys
                }
                final_drift = content_drift(
                    _yaml_safe_dump_unicode(_valid_field_subset(parsed)),
                    _yaml_safe_dump_unicode(llm_subset_final),
                )
            if final_drift:
                return {
                    "ok": False,
                    "yaml": original_yaml,
                    "repairs": repairs,
                    "schema_errors": [f"El texto fue modificado: {final_drift}"],
                    "error": (
                        f"La reparación alteró tu texto ({final_drift}). "
                        f"Se devolvió tu texto original sin tocar."
                    ),
                }

            return {
                "ok": True,
                "yaml": yaml_text,
                "repairs": repairs,
                "schema_errors": [],
            }
        except Exception as e:  # noqa: BLE001 — endpoint-level safety net
            import traceback
            traceback.print_exc()
            return {
                "ok": False,
                "yaml": yaml_content,
                "repairs": [],
                "schema_errors": [f"Repair endpoint error: {e}"],
            }


__all__ = [
    "parse_yaml_safe",
    "validate_yaml_schema",
    "content_tokens",
    "content_drift",
    "strip_yaml_fences",
    "YamlEditorService",
]
