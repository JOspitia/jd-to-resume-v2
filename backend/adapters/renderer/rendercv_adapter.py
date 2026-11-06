"""
backend.adapters.renderer.rendercv_adapter
==========================================

Adapter that wraps ``render_service.render_cv_with_rendercv`` to expose
the same renderer through the ``PDFRenderer`` port. RenderCV produces
the Typst-based sb2nov / classic / moderncv themes.

When this adapter raises, the application layer falls back to
``PlaywrightHTMLAdapter`` (the universal HTML template).
"""

from __future__ import annotations

from typing import Optional

from ports.pdf_renderer import PDFRenderer
from render_service import render_cv_with_rendercv


class RenderCVAdapter:
    """Adapter wrapping ``render_service.render_cv_with_rendercv``."""

    name = "rendercv:sb2nov"

    def __init__(self, theme: str = "sb2nov") -> None:
        self._theme = theme
        # Update the name to reflect the theme so logs distinguish adapters.
        self.name = f"rendercv:{theme}"

    def render(
        self,
        parsed_data: dict,
        output_path: str,
        *,
        theme: str = "sb2nov",
        fit_single_page: bool = False,
        page_break_section: Optional[str] = None,
        photo_path: Optional[str] = None,
        labels: Optional[dict] = None,
        accent: Optional[str] = None,
    ) -> None:
        """Render via RenderCV. ``labels`` is ignored (RenderCV handles
        section titles internally via its design schema).

        ``accent`` names a palette from ``design_palettes``; ``"none"`` or
        ``None`` keeps the theme's own (black & white) colours.
        """
        render_cv_with_rendercv(
            parsed_data,
            output_path,
            theme=theme,
            fit_single_page=fit_single_page,
            page_break_section=page_break_section,
            photo_path=photo_path,
            accent=accent or "none",
        )


__all__ = ["RenderCVAdapter"]