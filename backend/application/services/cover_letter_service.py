"""
backend.application.services.cover_letter_service
==================================================

The cover-letter generator: the single source of truth for the
``POST /api/cover-letter`` LLM call and for the letter's PDF.

Flow (mirrors :class:`application.services.audit_service.AuditService`):

    1. Extract the candidate's real text from the uploaded PDF.
    2. Resolve the **contact block** deterministically — never from the
       model: email / phone / profile URLs come from the PDF itself
       (``parser.extract_header``) or from what the user typed in the
       form, with the form winning.
    3. Compose the prompt via
       :func:`domain.cover_letter_prompts.build_cover_letter_prompt`.
    4. Call the shared LLM cascade (primary provider → fallbacks).
    5. Parse the response tolerantly: markdown fences, a list wrapper, a
       ``{"letter": {...}}`` envelope, missing optional fields.
    6. Assemble the signature from the contact block (the model only
       supplies the candidate's name).
    7. Render the PDF with the chosen letter style + accent palette and
       persist it next to the generated CVs.

The normalised shape is::

    {
      "salutation": str,
      "opening": str,
      "body": [str, ...],
      "closing": str,
      "signature": str,          # name + contact lines + profile URLs
      "plain_text": str,         # the whole letter, ready to copy
      "contact": {               # what actually goes on the letterhead
        "name": str, "email": str, "phone": str,
        "linkedin": str, "github": str, "portfolio": str,
      },
      "pdf_filename": str,       # e.g. "cover_letter_1712345678.pdf"
      "meta": {
        "word_count": int,
        "language": "es" | "en" | "unknown",
        "domain_game": str,
        "tone": str,
        "length": str,
        "letter_style": str,
        "accent": str,
      },
    }

``plain_text`` is built here rather than by the LLM: assembling it from the
structured fields guarantees the copy/paste buffer is exactly what the UI
shows, with no stray markdown the model may have left in a field.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any, Optional, Protocol

from language import detect_language


class _LLMCompleter(Protocol):
    """Protocol subset of :class:`LLMOrchestrator` that the service needs."""

    async def complete(self, prompt: str, *, model: str | None = None) -> str: ...


class _ParserLike(Protocol):
    """Protocol subset of :class:`ResumeParser` we need for PDF→text."""

    def extract_text(self, file_path: str) -> str: ...

    def extract_header(self, text: str) -> dict: ...


class _StorageLike(Protocol):
    """Protocol subset of :class:`ResumeStorage` for persisting the PDF."""

    def save_generated_pdf(self, source_path: str, prefix: str = "tailored_resume") -> str: ...


# Fields the frontend renders, in reading order.
_REQUIRED_FIELDS = ("salutation", "opening", "body", "closing", "signature")

#: Contact fields the letterhead can show.
_CONTACT_FIELDS = ("email", "phone", "linkedin", "github", "portfolio")


class CoverLetterService:
    """Generates a cover letter (text + PDF) from a resume + job description."""

    def __init__(
        self,
        llm: _LLMCompleter,
        parser: _ParserLike | None = None,
        storage: _StorageLike | None = None,
        renderer: Any | None = None,
    ) -> None:
        self._llm = llm
        # The parser is optional: ``generate_text`` operates on
        # already-extracted text. It is only needed for ``generate_from_pdf``.
        self._parser = parser
        # Storage + renderer are optional: without them the service still
        # returns the letter, just without a PDF.
        self._storage = storage
        self._renderer = renderer

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
        letter_style: str = "classic",
        accent: Optional[str] = None,
        linkedin_url: str = "",
        github_url: str = "",
        portfolio_url: str = "",
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
            letter_style=letter_style,
            accent=accent,
            contact_overrides={
                "linkedin": linkedin_url,
                "github": github_url,
                "portfolio": portfolio_url,
            },
            header=self._safe_extract_header(resume_text),
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
        letter_style: str = "classic",
        accent: Optional[str] = None,
        contact_overrides: Optional[dict] = None,
        header: Optional[dict] = None,
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

        # The contact block is deterministic: what the PDF says, or what
        # the user typed in the form. The model never gets to invent a
        # phone number, an email or a URL.
        contact = self._resolve_contact(
            header=header,
            overrides=contact_overrides or {},
            model_signature=letter.get("signature", ""),
            fallback_name=self._guess_name(resume_text),
        )
        letter["contact"] = contact

        # The signature is rebuilt from the contact block: name, then the
        # contact line, then the profile URLs (LinkedIn included).
        signature_lines = self._signature_lines(contact)
        letter["signature"] = "\n".join(signature_lines)

        plain_text = self._compose_plain_text(letter)
        letter["plain_text"] = plain_text

        letter["meta"] = {
            "word_count": len(plain_text.split()),
            "language": detect_language(plain_text),
            "domain_game": getattr(game, "name", "tech"),
            "tone": tone,
            "length": length,
            "letter_style": letter_style,
            "accent": accent or "none",
        }

        # PDF rendering is best-effort: a letter without a PDF is still a
        # letter, so a rendering failure must not fail the request.
        pdf_filename = await self._render_pdf(letter, contact, letter_style, accent)
        if pdf_filename:
            letter["pdf_filename"] = pdf_filename

        return letter

    # ------------------------------------------------------------------
    # Contact resolution
    # ------------------------------------------------------------------

    def _safe_extract_header(self, resume_text: str) -> dict:
        """Call ``parser.extract_header`` without letting it break the flow.

        The extraction is best-effort (regexes over a messy PDF); a
        failure means "no contacts found", not "500".
        """
        if self._parser is None:
            return {}
        try:
            return self._parser.extract_header(resume_text) or {}
        except Exception:
            return {}

    @staticmethod
    def _resolve_contact(
        *,
        header: Optional[dict],
        overrides: dict,
        model_signature: str,
        fallback_name: str = "",
    ) -> dict:
        """Merge the PDF's contact fields with the form's.

        Precedence: the form wins (the user can fix a wrong extraction),
        then the PDF's header, then nothing. The name comes from the
        model's signature (it copies it from the CV) and falls back to
        the first line of the resume.
        """
        header = header or {}
        contact: dict[str, str] = {}

        for field in _CONTACT_FIELDS:
            value = (overrides.get(field) or "").strip() or (header.get(field) or "").strip()
            contact[field] = value

        name = (model_signature or "").strip().splitlines()[0].strip() if model_signature else ""
        contact["name"] = name or (fallback_name or "").strip()
        return contact

    @staticmethod
    def _guess_name(resume_text: str) -> str:
        """Best-effort candidate name: the first non-empty line of the CV.

        Only used when the model did not return a signature. It is a
        fallback, not the primary source.
        """
        for line in (resume_text or "").splitlines():
            cleaned = line.strip()
            if cleaned:
                # A contact line (email / phone) is not a name.
                if "@" in cleaned or cleaned.lower().startswith("tel:"):
                    continue
                return cleaned
        return ""

    @staticmethod
    def _contact_line(contact: dict) -> str:
        """The ``phone | email`` line of the signature."""
        bits = [
            (contact.get("phone") or "").strip(),
            (contact.get("email") or "").strip(),
        ]
        bits = [bit for bit in bits if bit]
        return " | ".join(bits)

    @classmethod
    def _signature_lines(cls, contact: dict) -> list[str]:
        """Build the signature block: name, contact line, profile URLs."""
        lines: list[str] = []
        name = (contact.get("name") or "").strip()
        if name:
            lines.append(name)

        contact_line = cls._contact_line(contact)
        if contact_line:
            lines.append(contact_line)

        for network in ("linkedin", "github", "portfolio"):
            url = (contact.get(network) or "").strip()
            if not url:
                continue
            lines.append(_pretty_profile_url(url, network))
        return lines

    # ------------------------------------------------------------------
    # PDF rendering
    # ------------------------------------------------------------------

    async def _render_pdf(
        self,
        letter: dict,
        contact: dict,
        letter_style: str,
        accent: Optional[str],
    ) -> str:
        """Render the letter to PDF and persist it. Returns the filename.

        The rendering is blocking (Playwright's sync API drives Chromium),
        so it runs in a worker thread: the sync API refuses to start
        inside a running asyncio loop, and the endpoint is async.
        """
        if self._renderer is None or self._storage is None:
            return ""

        import asyncio

        try:
            return await asyncio.to_thread(
                self._render_pdf_sync, letter, contact, letter_style, accent
            )
        except Exception as err:
            print(f"[WARN] Could not render the cover letter PDF: {err}")
            return ""

    def _render_pdf_sync(
        self,
        letter: dict,
        contact: dict,
        letter_style: str,
        accent: Optional[str],
    ) -> str:
        """Blocking part of :meth:`_render_pdf` (runs in a worker thread)."""
        try:
            from adapters.renderer.cover_letter_adapter import (
                build_signature_links,
                normalize_letter_style,
            )

            style = normalize_letter_style(letter_style)
            letter_data = {
                "name": contact.get("name") or "",
                "location": "",
                "phone": contact.get("phone") or "",
                "email": contact.get("email") or "",
                "linkedin": contact.get("linkedin") or "",
                "github": contact.get("github") or "",
                "portfolio": contact.get("portfolio") or "",
                "salutation": letter.get("salutation") or "",
                "opening": letter.get("opening") or "",
                "body": letter.get("body") or [],
                "closing": letter.get("closing") or "",
                "signature_name": contact.get("name") or "",
                "signature_lines": [self._contact_line(contact)],
                "signature_links": build_signature_links(contact),
            }

            fd, tmp_path = tempfile.mkstemp(suffix=".pdf", dir=tempfile.gettempdir())
            os.close(fd)
            try:
                self._renderer.render(
                    letter_data,
                    tmp_path,
                    style=style,
                    accent=accent,
                )
                final_path = self._storage.save_generated_pdf(tmp_path, prefix="cover_letter")
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

            filename = Path(final_path).name
            print(f"[INFO] Cover letter PDF rendered: {filename} (style={style}, accent={accent or 'none'})")
            return filename
        except Exception as err:
            print(f"[WARN] Could not render the cover letter PDF: {err}")
            return ""

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


def _pretty_profile_url(url: str, network: str) -> str:
    """Render a profile URL the way a letter would print it.

    ``https://www.linkedin.com/in/jane-doe/`` becomes
    ``linkedin.com/in/jane-doe`` — readable for a human and still the
    exact URL an ATS can match.
    """
    cleaned = (url or "").strip()
    cleaned = re.sub(r"^https?://", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"^www\.", "", cleaned, flags=re.IGNORECASE)
    return cleaned.rstrip("/")


__all__ = ["CoverLetterService"]
