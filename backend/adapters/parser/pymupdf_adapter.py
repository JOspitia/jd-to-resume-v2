"""
backend.adapters.parser.pymupdf_adapter
=======================================

Adapter that reads a PDF with PyMuPDF (``fitz``) and returns plain text +
extracted header fields. Implements the ``ResumeParser`` port.

Moved verbatim from ``backend/main.py`` in commit 2 of the hexagonal
refactor. Only structural change is the class wrapper so callers can
swap the parser without touching the generation pipeline.
"""

from __future__ import annotations

import re
from typing import Any

import pymupdf  # PyMuPDF (formerly imported as `fitz`)

from ports.resume_parser import ResumeParser


# ---------------------------------------------------------------------------
# Regex constants. Module-level so they compile once.
# ---------------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(
    r"(\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}"
)
_GITHUB_RE = re.compile(
    r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9._-]+/?", re.IGNORECASE
)
_LINKEDIN_RE = re.compile(
    r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9._-]+/?", re.IGNORECASE
)
_PORTFOLIO_RE = re.compile(
    r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)?\.(?:com|net|org|io|dev|me|co|app|page|site|xyz|store|portfolio)(?:/[A-Za-z0-9._~:/?#@!$&'()*+,;=-]*)?",
    re.IGNORECASE,
)
# Common email providers that look like domains but are not portfolio sites.
_PORTFOLIO_EXCLUDE_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.es", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "me.com", "aol.com", "protonmail.com",
    "mail.com", "zoho.com", "yandex.com", "yandex.ru",
}


class PyMuPDFParser:
    """Adapter that reads a PDF resume with PyMuPDF and exposes the text +
    header fields via the ``ResumeParser`` port."""

    def extract_text(self, file_path: str) -> str:
        """Open the PDF, concatenate plain text + all /Link annotation URIs.

        The PDF hyperlinks that render as bare labels (e.g. ``"LinkedIn"``)
        are surfaced as their real URLs in the extracted text. The LLM and
        the header extractor can then see them.
        """
        doc = pymupdf.open(file_path)
        text_parts: list[str] = []
        for page in doc:
            text_parts.append(page.get_text())
            try:
                for link in page.get_links():
                    uri = link.get("uri", "").strip()
                    if uri:
                        text_parts.append(" " + uri)
            except Exception:
                # Some PDFs have malformed link structures; skip silently.
                pass
        extracted = " ".join(text_parts)

        # Debug: log any linked URLs we found so the user can verify the PDF
        # actually has the /Link annotations we expect.
        urls_found: list[str] = []
        for page in doc:
            try:
                for link in page.get_links():
                    uri = link.get("uri", "").strip()
                    if uri:
                        urls_found.append(uri)
            except Exception:
                pass
        if urls_found:
            print(f"[EXTRACT] PDF /Link URIs found ({len(urls_found)}): {urls_found[:10]}")
        return extracted

    def extract_header(self, text: str) -> dict[str, Any]:
        """Best-effort extraction of contact fields from the base-resume plain text.

        Returns a dict with keys: ``email``, ``phone``, ``github``, ``linkedin``,
        ``portfolio``, ``has_placeholder_github``, ``has_placeholder_linkedin``,
        ``has_placeholder_portfolio``. Each value is a string (possibly empty);
        callers decide how to merge with form-provided values. The
        ``*_placeholder`` booleans flag words like ``"GitHub"`` or
        ``"LinkedIn"`` appearing as bare tokens (no URL) so the UI can warn
        the user that the resume had placeholders but no real URLs were found.

        Uses targeted regex patterns that bias toward precision over recall —
        a missed field is better than a wrong one, since the LLM still sees
        the full text in the prompt and the user can correct any false
        negative manually.
        """
        if not text:
            return {
                "email": "", "phone": "", "github": "", "linkedin": "", "portfolio": "",
                "has_placeholder_github": False,
                "has_placeholder_linkedin": False,
                "has_placeholder_portfolio": False,
            }

        # Email: prefer the first match that doesn't look like example/noreply.
        email_match = ""
        for m in _EMAIL_RE.finditer(text):
            candidate = m.group(0)
            if "example" in candidate.lower() or "noreply" in candidate.lower():
                continue
            email_match = candidate
            break

        # Phone: prefer + prefix and 10+ digits.
        phone_match = ""
        for m in _PHONE_RE.finditer(text):
            candidate = m.group(0)
            digits = re.sub(r"\D", "", candidate)
            if len(digits) >= 10:
                phone_match = candidate.strip()
                break

        github_match = _GITHUB_RE.search(text)
        linkedin_match = _LINKEDIN_RE.search(text)

        # Portfolio: scan URL-like strings, exclude github/linkedin/email domains.
        portfolio_match = ""
        seen_domains = set(_PORTFOLIO_EXCLUDE_DOMAINS)
        if github_match:
            seen_domains.add("github.com")
        if linkedin_match:
            seen_domains.add("linkedin.com")
        # Always exclude the email's domain — it appears in the text as
        # ``something@gmail.com`` and the bare ``gmail.com`` matches the regex.
        if email_match and "@" in email_match:
            email_domain = email_match.split("@", 1)[1].strip().lower()
            if email_domain:
                seen_domains.add(email_domain)
        print(f"[EXTRACT] portfolio exclusion set: {sorted(seen_domains)}")
        for m in _PORTFOLIO_RE.finditer(text):
            candidate = m.group(0)
            candidate_lower = candidate.lower()
            host_match = re.match(r"(?:https?://)?(?:www\.)?([^/]+)", candidate_lower)
            host = host_match.group(1) if host_match else candidate_lower
            match_start = m.start()
            if match_start > 0:
                char_before = text[match_start - 1]
                if char_before in "@.0123456789abcdefghijklmnopqrstuvwxyz":
                    # Part of a longer string (probably email or path). Skip.
                    continue
            if host in seen_domains:
                print(f"[EXTRACT] portfolio skip (excluded domain): '{candidate}' host='{host}'")
                continue
            if any(skip in candidate_lower for skip in ["example.com", "test.com", "yourname", "placeholder"]):
                print(f"[EXTRACT] portfolio skip (skip word): '{candidate}'")
                continue
            # Normalize to https:// if no scheme.
            if not candidate_lower.startswith("http"):
                candidate = "https://" + candidate
            print(f"[EXTRACT] portfolio MATCHED: '{candidate}' (host='{host}')")
            portfolio_match = candidate
            break

        # Detect placeholder words: a line containing only "LinkedIn | GitHub | Portafolio"
        # or similar where each platform is just a token, not a URL. Flag them so
        # the UI can warn the user to fill the form.
        first_lines = "\n".join(text.split("\n")[:8])
        has_placeholder_github = (
            not github_match
            and bool(re.search(r"\bgithub\b", first_lines, re.IGNORECASE))
        )
        has_placeholder_linkedin = (
            not linkedin_match
            and bool(re.search(r"\blinkedin\b", first_lines, re.IGNORECASE))
        )
        has_placeholder_portfolio = (
            not portfolio_match
            and bool(re.search(r"\bportafolio\b|\bportfolio\b", first_lines, re.IGNORECASE))
        )

        return {
            "email": email_match,
            "phone": phone_match,
            "github": github_match.group(0) if github_match else "",
            "linkedin": linkedin_match.group(0) if linkedin_match else "",
            "portfolio": portfolio_match,
            "has_placeholder_github": has_placeholder_github,
            "has_placeholder_linkedin": has_placeholder_linkedin,
            "has_placeholder_portfolio": has_placeholder_portfolio,
        }


__all__ = ["PyMuPDFParser"]