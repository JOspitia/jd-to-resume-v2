"""Audit service: the LLM-based ATS auditor.

Pulled out of ``main.py`` during the hexagonal split. Three call sites
all delegate to :py:meth:`AuditService.audit_text`:

  * ``POST /api/analyze-ats`` (frontend-initiated audit on a freshly
    uploaded CV)
  * ``_run_internal_audit`` (auto re-audit fired by ``/api/generate``
    after a forced translate-to-English flow)
  * ``POST /api/analyze-yaml`` (audit on a YAML dict the user has edited
    before rendering)

The service composes the per-game prompt via
:func:`domain.audit_prompts.build_audit_prompt`, calls the LLM, strips
any ``\`\`\`json\`\`\``` markdown fence, and returns the parsed dict.
Raises :class:`ValueError` if the response is not a JSON object
(caller is responsible for HTTP mapping).
"""

from __future__ import annotations

import json
import re
from typing import Any, Protocol


class _LLMCompleter(Protocol):
    """Protocol subset of :class:`LLMOrchestrator` that the service needs.

    A real ``LLMOrchestrator`` exposes ``complete(prompt, model=None)``
    which is what we call here.
    """
    async def complete(self, prompt: str, *, model: str | None = None) -> str: ...


class _ParserLike(Protocol):
    """Protocol subset of :class:`ResumeParser` we need for PDF→text."""
    def extract_text(self, file_path: str) -> str: ...


class AuditService:
    """The single source of truth for the ATS-audit LLM call."""

    def __init__(self, llm: _LLMCompleter, parser: _ParserLike | None = None) -> None:
        self._llm = llm
        # Parser is optional: ``audit_text`` doesn't need it (operates on
        # already-extracted text). It's only needed for ``audit_pdf``,
        # which the analyze-ats endpoint uses.
        self._parser = parser

    async def audit_text(
        self,
        resume_text: str,
        jd_text: str,
        audit_game: Any,
    ) -> dict:
        """Run the audit on already-extracted resume text.

        Returns the parsed dict. Raises ``ValueError`` if the LLM
        response is not a JSON object.
        """
        # Import inside the method to keep this module free of
        # domain-prompt dependencies at module-init time.
        from domain.audit_prompts import build_audit_prompt

        # The domain function uses a positional third arg (named
        # ``game`` in its public API). We pass the audit_game we
        # received as that positional arg.
        prompt = build_audit_prompt(resume_text, jd_text, audit_game)
        content = await self._llm.complete(prompt)

        clean_content = content.strip()
        if "```" in clean_content:
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
            if match:
                clean_content = match.group(1)

        try:
            parsed = json.loads(clean_content)
        except Exception:
            parsed = json.loads(content)

        # Some LLM clients wrap the payload in a list; take the first element.
        if isinstance(parsed, list) and len(parsed) > 0:
            parsed = parsed[0]

        if not isinstance(parsed, dict):
            raise ValueError(
                f"Audit response was not a dict (got {type(parsed).__name__})"
            )
        return parsed

    async def audit_pdf(
        self,
        pdf_path: str,
        jd_text: str,
        audit_game: Any,
    ) -> dict:
        """Convenience wrapper: extract text from a PDF, then run ``audit_text``.

        Raises ``RuntimeError`` if no parser is wired in.
        """
        if self._parser is None:
            raise RuntimeError(
                "AuditService.audit_pdf called without a parser wired in. "
                "Pass a ResumeParser (e.g. PyMuPDFParser) to the constructor."
            )
        resume_text = self._parser.extract_text(pdf_path)
        return await self.audit_text(resume_text, jd_text, audit_game)


__all__ = ["AuditService"]
