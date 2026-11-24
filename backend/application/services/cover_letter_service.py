"""
backend.application.services.cover_letter_service
==================================================

The cover-letter generator: the single source of truth for the
``POST /api/cover-letter`` LLM call.

Flow (mirrors :class:`application.services.audit_service.AuditService`):

    1. Extract the candidate's real text from the uploaded PDF.
    2. Compose the prompt via :func:`domain.cover_letter_prompts.build_cover_letter_prompt`.
    3. Call the shared LLM cascade (primary provider → fallbacks).
    4. Parse the response tolerantly: markdown fences, a list wrapper, a
       ``{"letter": {...}}`` envelope, missing optional fields.
    5. Normalise it into the stable contract the frontend consumes.

The normalised shape is::

    {
      "salutation": str,
      "opening": str,
      "body": [str, ...],
      "closing": str,
      "signature": str,
      "plain_text": str,        # the whole letter, ready to copy
      "meta": {
        "word_count": int,
        "language": "es" | "en" | "unknown",
        "domain_game": str,
        "tone": str,
        "length": str,
      },
    }

``plain_text`` is built here rather than by the LLM: assembling it from the
structured fields guarantees the copy/paste buffer is exactly what the UI
shows, with no stray markdown the model may have left in a field.
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol

from language import detect_language


class _LLMCompleter(Protocol):
    """Protocol subset of :class:`LLMOrchestrator` that the service needs."""

    async def complete(self, prompt: str, *, model: str | None = None) -> str: ...


class _ParserLike(Protocol):
    """Protocol subset of :class:`ResumeParser` we need for PDF→text."""

    def extract_text(self, file_path: str) -> str: ...


# Fields the frontend renders, in reading order.
_REQUIRED_FIELDS = ("salutation", "opening", "body", "closing", "signature")


class CoverLetterService:
    """Generates a cover letter from a resume + job description."""

    def __init__(self, llm: _LLMCompleter, parser: _ParserLike | None = None) -> None:
        self._llm = llm
        # The parser is optional: ``generate_text`` operates on
        # already-extracted text. It is only needed for ``generate_from_pdf``.
        self._parser = parser

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate_from_pdf(
        self,
        pdf_path: str,
        jd_text: str,
        game,
        *,
        target_role: str = "",
        company_name: str = "",
        tone: str = "professional",
        length: str = "medium",
        language: str = "auto",
        custom_instructions: str = "",
    ) -> dict:
        """Extract the PDF's text, then run :meth:`generate_text`."""
        if self._parser is None:
            raise RuntimeError(
                "CoverLetterService.generate_from_pdf called without a parser "
                "wired in. Pass a ResumeParser (e.g. PyMuPDFParser) to the "
                "constructor."
            )
        resume_text = self._parser.extract_text(pdf_path)
        return await self.generate_text(
            resume_text,
            jd_text,
            game,
            target_role=target_role,
            company_name=company_name,
            tone=tone,
            length=length,
            language=language,
            custom_instructions=custom_instructions,
        )

    async def generate_text(
        self,
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
    ) -> dict:
        """Run the LLM and return the normalised cover-letter dict.

        Raises:
            ValueError: when the LLM response cannot be read as a letter.
        """
        from domain.cover_letter_prompts import build_cover_letter_prompt

        prompt = build_cover_letter_prompt(
            resume_text,
            jd_text,
            game,
            target_role=target_role,
            company_name=company_name,
            tone=tone,
            length=length,
            language=language,
            custom_instructions=custom_instructions,
        )

        content = await self._llm.complete(prompt)
        parsed = self._parse_response(content)

        letter = self._normalize(parsed)

        plain_text = self._compose_plain_text(letter)
        letter["plain_text"] = plain_text

        letter["meta"] = {
            "word_count": len(plain_text.split()),
            "language": detect_language(plain_text),
            "domain_game": getattr(game, "name", "tech"),
            "tone": tone,
            "length": length,
        }
        return letter

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_response(content: str) -> dict:
        """Parse the LLM response into a dict, tolerating the usual noise.

        Handles three shapes seen in practice:
          * a markdown-fenced JSON block (``\\`\\`\\`json ... \\`\\`\\```)
          * a bare JSON object
          * a single-element list wrapping the object

        Raises:
            ValueError: when nothing JSON-shaped can be read.
        """
        clean = (content or "").strip()
        if "```" in clean:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean)
            if match:
                clean = match.group(1)

        parsed: Any = None
        for candidate in (clean, content or ""):
            try:
                parsed = json.loads(candidate)
                break
            except Exception:
                continue

        if parsed is None:
            raise ValueError(
                "La respuesta del modelo no es JSON válido para la carta de presentación."
            )

        # Some clients wrap the payload in a list; take the first element.
        if isinstance(parsed, list):
            if not parsed:
                raise ValueError("La respuesta del modelo fue una lista vacía.")
            parsed = parsed[0]

        if not isinstance(parsed, dict):
            raise ValueError(
                f"La respuesta del modelo no fue un objeto (fue {type(parsed).__name__})."
            )

        # Some models nest the letter under a "letter" key.
        inner = parsed.get("letter")
        if isinstance(inner, dict):
            parsed = inner

        return parsed

    @staticmethod
    def _normalize(parsed: dict) -> dict:
        """Coerce the parsed payload into the stable contract.

        The model is asked for five fields; every one of them is required
        for a usable letter, so a missing one is a hard error rather than a
        silently empty paragraph. Optional metadata is dropped.
        """
        missing = [f for f in _REQUIRED_FIELDS if f not in parsed]
        if missing:
            raise ValueError(
                "La carta generada está incompleta: faltan " + ", ".join(missing) + "."
            )

        salutation = str(parsed.get("salutation") or "").strip()
        opening = str(parsed.get("opening") or "").strip()
        closing = str(parsed.get("closing") or "").strip()
        signature = str(parsed.get("signature") or "").strip()

        raw_body = parsed.get("body")
        if isinstance(raw_body, str):
            # A model that answers with one string: split it on blank lines
            # so the UI still gets real paragraphs.
            body = [
                chunk.strip()
                for chunk in re.split(r"\n\s*\n", raw_body)
                if chunk.strip()
            ]
        elif isinstance(raw_body, list):
            body = [str(chunk).strip() for chunk in raw_body if str(chunk).strip()]
        else:
            body = []

        if not body:
            raise ValueError(
                "La carta generada no contiene ningún párrafo de contenido."
            )

        return {
            "salutation": salutation,
            "opening": opening,
            "body": body,
            "closing": closing,
            "signature": signature,
        }

    @staticmethod
    def _compose_plain_text(letter: dict) -> str:
        """Assemble the copy/paste-ready letter from the structured fields."""
        blocks: list[str] = []
        if letter.get("salutation"):
            blocks.append(letter["salutation"])
        if letter.get("opening"):
            blocks.append(letter["opening"])
        for paragraph in letter.get("body", []):
            blocks.append(paragraph)
        if letter.get("closing"):
            blocks.append(letter["closing"])
        if letter.get("signature"):
            blocks.append(letter["signature"])
        return "\n\n".join(blocks).strip()


__all__ = ["CoverLetterService"]
