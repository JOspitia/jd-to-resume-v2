"""
backend.design_palettes
=======================

Accent palettes for the rendered CV.

Why this module exists
----------------------
The rendered CV used to be strictly black & white. RenderCV supports a full
colour scheme per design (see
``rendercv.schema.models.design.classic_theme.Colors``), so the only thing
missing was a way to choose one. This module is the single source of truth
for the accent colours offered by the UI.

ATS / print-safety rules baked into the palettes
-------------------------------------------------
The palettes are deliberately boring so a recruiter's ATS keeps parsing the
document exactly as before:

1. **Body text stays black.** Only the name, the section titles and the
   links get the accent. Body copy is the part an ATS weights most, so it
   is never tinted.
2. **No background fills behind text.** RenderCV applies the colour as the
   text ``fill:``; the section-title rule is a separate ``box``. There is
   no shaded block that could swallow the text layer of the PDF.
3. **Nothing depends on colour alone.** Section titles stay bold, larger
   than the body copy and underlined by a rule, and links stay
   underlined. Printed in black & white the document is still fully
   readable and still shows the same visual hierarchy.
4. **Every tone clears WCAG AA (4.5:1) against white**, so a faded
   screenshot or a low-quality printer never makes a line unreadable.
   ``tests/test_design_palettes.py`` asserts this for every palette.
5. **No coloured bullets, no sidebars, no multi-column layout.** The
   accent is a tint, not a redesign.

Usage
-----
``get_palette_colors("navy")`` returns the eight RenderCV colour slots.
``get_palette_colors("none")`` returns ``{}`` — meaning "leave the theme's
own colours alone", which keeps the historical black & white output
byte-for-byte identical.
"""

from __future__ import annotations

import re
from typing import Dict, List, Optional, Tuple

#: Palette id meaning "no accent — keep the theme's own colours".
NO_ACCENT = "none"

#: The RenderCV colour slots a palette can drive. Kept explicit so a typo
#: in a palette definition fails loudly in the tests instead of silently
#: leaving a colour untouched.
COLOR_SLOTS: Tuple[str, ...] = (
    "body",
    "name",
    "headline",
    "connections",
    "section_titles",
    "links",
    "footer",
    "top_note",
)

# Body copy is never tinted (rule 1 above).
_BODY = "rgb(0, 0, 0)"

# Each palette is: accent (name / headline / section titles / links) +
# a softer tone for the secondary text (connections / footer / top note).
# The softer tone is the accent mixed with 20% white, which keeps it at
# or above 4.75:1 on white for every palette in this table.
_PALETTES: Dict[str, Dict[str, str]] = {
    "navy": {
        "label": "Azul marino",
        "hex": "#1B3A5C",
        "body": _BODY,
        "name": "rgb(27, 58, 92)",
        "headline": "rgb(27, 58, 92)",
        "connections": "rgb(73, 97, 125)",
        "section_titles": "rgb(27, 58, 92)",
        "links": "rgb(27, 58, 92)",
        "footer": "rgb(73, 97, 125)",
        "top_note": "rgb(73, 97, 125)",
    },
    "teal": {
        "label": "Verde azulado",
        "hex": "#0F5C57",
        "body": _BODY,
        "name": "rgb(15, 92, 87)",
        "headline": "rgb(15, 92, 87)",
        "connections": "rgb(63, 125, 121)",
        "section_titles": "rgb(15, 92, 87)",
        "links": "rgb(15, 92, 87)",
        "footer": "rgb(63, 125, 121)",
        "top_note": "rgb(63, 125, 121)",
    },
    "forest": {
        "label": "Verde bosque",
        "hex": "#23543B",
        "body": _BODY,
        "name": "rgb(35, 84, 59)",
        "headline": "rgb(35, 84, 59)",
        "connections": "rgb(79, 118, 98)",
        "section_titles": "rgb(35, 84, 59)",
        "links": "rgb(35, 84, 59)",
        "footer": "rgb(79, 118, 98)",
        "top_note": "rgb(79, 118, 98)",
    },
    "burgundy": {
        "label": "Granate",
        "hex": "#6E2639",
        "body": _BODY,
        "name": "rgb(110, 38, 57)",
        "headline": "rgb(110, 38, 57)",
        "connections": "rgb(139, 81, 97)",
        "section_titles": "rgb(110, 38, 57)",
        "links": "rgb(110, 38, 57)",
        "footer": "rgb(139, 81, 97)",
        "top_note": "rgb(139, 81, 97)",
    },
    "plum": {
        "label": "Ciruela",
        "hex": "#5B2D63",
        "body": _BODY,
        "name": "rgb(91, 45, 99)",
        "headline": "rgb(91, 45, 99)",
        "connections": "rgb(124, 87, 130)",
        "section_titles": "rgb(91, 45, 99)",
        "links": "rgb(91, 45, 99)",
        "footer": "rgb(124, 87, 130)",
        "top_note": "rgb(124, 87, 130)",
    },
    "slate": {
        "label": "Gris pizarra",
        "hex": "#3D4A5C",
        "body": _BODY,
        "name": "rgb(61, 74, 92)",
        "headline": "rgb(61, 74, 92)",
        "connections": "rgb(100, 110, 125)",
        "section_titles": "rgb(61, 74, 92)",
        "links": "rgb(61, 74, 92)",
        "footer": "rgb(100, 110, 125)",
        "top_note": "rgb(100, 110, 125)",
    },
}

#: Public palette ids, in the order the UI should show them.
PALETTE_IDS: Tuple[str, ...] = (NO_ACCENT, *_PALETTES.keys())


def normalize_palette_id(value: Optional[str]) -> str:
    """Normalise a user-supplied palette id.

    Unknown or empty values fall back to ``"none"`` (no accent) rather than
    raising: a stale bookmark or a hand-made ``curl`` should still produce a
    valid CV, just without the accent.
    """
    if not value:
        return NO_ACCENT
    candidate = str(value).strip().lower()
    if candidate in _PALETTES:
        return candidate
    return NO_ACCENT


def is_valid_palette_id(value: Optional[str]) -> bool:
    """True when ``value`` names a palette this build knows about.

    ``"none"`` is valid: it means "no accent", which is the default.
    """
    if not value:
        return False
    candidate = str(value).strip().lower()
    return candidate == NO_ACCENT or candidate in _PALETTES


def get_palette_colors(palette_id: Optional[str]) -> Dict[str, str]:
    """Return the RenderCV colour slots for ``palette_id``.

    Returns an **empty dict** for ``"none"`` (or any unknown id), which
    means "do not override the theme's colours". That keeps the default
    output identical to the pre-feature behaviour.
    """
    normalized = normalize_palette_id(palette_id)
    if normalized == NO_ACCENT:
        return {}
    palette = _PALETTES[normalized]
    return {slot: palette[slot] for slot in COLOR_SLOTS}


def palette_catalog() -> List[Dict[str, str]]:
    """Catalogue for the UI: id, label and swatch hex for every palette."""
    catalog: List[Dict[str, str]] = [
        {
            "id": NO_ACCENT,
            "label": "Sin color",
            "hex": "#000000",
            "description": "Negro y blanco, el más seguro para ATS",
        }
    ]
    for palette_id, palette in _PALETTES.items():
        catalog.append(
            {
                "id": palette_id,
                "label": palette["label"],
                "hex": palette["hex"],
                "description": "Color de acento en nombre y títulos",
            }
        )
    return catalog


def accent_css_variables(palette_id: Optional[str]) -> Dict[str, str]:
    """CSS custom properties for the Playwright HTML template.

    The HTML fallback (``classic_html``) is hand-written CSS with hardcoded
    ``#000`` values. These variables let the same accent reach that
    template without a second, divergent palette table.

    When there is no accent every variable resolves to black, so the
    rendered HTML is unchanged from today.
    """
    colors = get_palette_colors(palette_id)
    if not colors:
        black = "#000000"
        return {
            "body": black,
            "accent": black,
            "muted": black,
            "rule": black,
        }
    return {
        "body": _rgb_to_hex(colors["body"]),
        "accent": _rgb_to_hex(colors["section_titles"]),
        "muted": _rgb_to_hex(colors["connections"]),
        "rule": _rgb_to_hex(colors["section_titles"]),
    }


# ---------------------------------------------------------------------------
# Colour maths — used by the tests to prove the palettes are accessible
# ---------------------------------------------------------------------------

_RGB_RE = re.compile(r"rgb\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)\s*\)")


def parse_rgb(color: str) -> Tuple[int, int, int]:
    """Parse an ``rgb(r, g, b)`` string into a tuple of ints."""
    match = _RGB_RE.search(color or "")
    if not match:
        raise ValueError(f"Not an rgb() colour: {color!r}")
    return tuple(int(match.group(i)) for i in (1, 2, 3))  # type: ignore[return-value]


def _rgb_to_hex(color: str) -> str:
    r, g, b = parse_rgb(color)
    return f"#{r:02x}{g:02x}{b:02x}"


def _relative_luminance(rgb: Tuple[int, int, int]) -> float:
    """WCAG 2.x relative luminance of an sRGB colour."""
    channels = []
    for value in rgb:
        srgb = value / 255
        if srgb <= 0.03928:
            channels.append(srgb / 12.92)
        else:
            channels.append(((srgb + 0.055) / 1.055) ** 2.4)
    red, green, blue = channels
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast_ratio(color_a: str, color_b: str = "rgb(255, 255, 255)") -> float:
    """WCAG contrast ratio between two ``rgb()`` colours.

    1.0 means identical, 21.0 is black on white. The WCAG AA threshold for
    normal-sized text is 4.5.
    """
    lum_a = _relative_luminance(parse_rgb(color_a))
    lum_b = _relative_luminance(parse_rgb(color_b))
    lighter, darker = max(lum_a, lum_b), min(lum_a, lum_b)
    return (lighter + 0.05) / (darker + 0.05)


__all__ = [
    "COLOR_SLOTS",
    "NO_ACCENT",
    "PALETTE_IDS",
    "accent_css_variables",
    "contrast_ratio",
    "get_palette_colors",
    "is_valid_palette_id",
    "normalize_palette_id",
    "palette_catalog",
    "parse_rgb",
]
