"""
backend.routes.design_router
=============================

Exposes the design options the UI can offer: the accent palettes and the
RenderCV themes.

Why an endpoint instead of a hardcoded list in the frontend
-----------------------------------------------------------
The backend is the one that actually renders the colours, so it is the
single source of truth for them. The frontend fetches the catalogue and
draws the swatches from the very same hex the renderer will use, which
removes the risk of the two drifting apart (a swatch showing one blue
while the PDF comes out in another).

Read-only and cheap: no LLM, no I/O, no rate limit.
"""

from __future__ import annotations

from fastapi import APIRouter

from design_palettes import PALETTE_IDS, palette_catalog

#: The RenderCV themes the app supports. ``classic_html`` is rendered by
#: the Playwright fallback instead of RenderCV, but it accepts the same
#: accent, so it lives in the same list.
THEMES = [
    {
        "id": "sb2nov",
        "name": "SB2Nov",
        "badge": "ATS / Silicon Valley",
        "description": "Limpio y estructurado para Tech",
    },
    {
        "id": "classic",
        "name": "Classic",
        "badge": "Sobrio",
        "description": "Tradicional, elegante y universal",
    },
    {
        "id": "moderncv",
        "name": "ModernCV",
        "badge": "Visual",
        "description": "Detalles a color y tipografía moderna",
    },
    {
        "id": "classic_html",
        "name": "Classic HTML",
        "badge": "Playwright",
        "description": "Renderizado web tradicional",
    },
]


#: The cover-letter layouts the renderer can produce. They mirror the
#: three CV designs, because a letter has no sections to arrange — but
#: the user still expects to pick a look that matches their CV.
LETTER_STYLES = [
    {
        "id": "classic",
        "name": "Clásica",
        "badge": "Sobrio",
        "description": "Encabezado centrado y cuerpo serif, como el CV clásico.",
    },
    {
        "id": "modern",
        "name": "Moderna",
        "badge": "Limpia",
        "description": "Encabezado a la izquierda y tipografía sin serifas.",
    },
    {
        "id": "sidebar",
        "name": "Lateral",
        "badge": "Visual",
        "description": "Columna de contactos a la izquierda y la carta a la derecha.",
    },
]


def build_design_router() -> APIRouter:
    """Build the design-options router. No DI needed — pure catalogue."""
    router = APIRouter(prefix="/api", tags=["design"])

    @router.get("/design-options")
    async def design_options():
        """Return the themes and the accent palettes the UI can render."""
        return {
            "themes": THEMES,
            "palettes": palette_catalog(),
            "letter_styles": LETTER_STYLES,
            "default_theme": "sb2nov",
            "default_palette": "none",
            "default_letter_style": "classic",
            "palette_ids": list(PALETTE_IDS),
        }

    return router


__all__ = ["build_design_router", "THEMES", "LETTER_STYLES"]
