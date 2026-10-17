"""
backend.adapters.renderer.factory
=================================

Builds the right ``PDFRenderer`` based on the requested theme.

Selection logic:
    * ``classic_html`` → ``PlaywrightHTMLAdapter`` (always available; no
      external Typst / RenderCV dependency for this path).
    * ``sb2nov`` / ``classic`` / ``moderncv`` → ``RenderCVAdapter``.
      This path can fail at runtime (RenderCV binary missing, Typst
      template unavailable, etc.); the caller falls back to the
      Playwright adapter on failure.
"""

from __future__ import annotations

from adapters.renderer.playwright_html_adapter import PlaywrightHTMLAdapter
from adapters.renderer.rendercv_adapter import RenderCVAdapter
from ports.pdf_renderer import PDFRenderer


_HTML_THEMES = frozenset({"classic_html"})


def build_pdf_renderer(theme: str) -> PDFRenderer:
    """Return the ``PDFRenderer`` adapter for ``theme``.

    ``classic_html`` is always backed by the Playwright HTML adapter.
    Any other theme (``sb2nov`` / ``classic`` / ``moderncv``) is backed
    by the RenderCV adapter. Callers handle the fallback to HTML when
    RenderCV raises at render time.
    """
    if theme in _HTML_THEMES:
        return PlaywrightHTMLAdapter()
    return RenderCVAdapter(theme)


__all__ = ["build_pdf_renderer"]