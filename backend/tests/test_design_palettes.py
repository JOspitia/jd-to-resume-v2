"""
Tests for the accent palettes (``design_palettes``) and their wiring into the
render pipeline.

The whole point of the accent feature is that the CV stops looking flat
*without* becoming harder for an ATS to parse. These tests are the safety
net for that claim:

    * every palette defines all eight RenderCV colour slots;
    * the body copy always stays black (rule 1 of the palette contract);
    * every tone clears WCAG AA (4.5:1) against white, so nothing becomes
      unreadable on a bad printer or a faded screen;
    * the accent reaches ``design["colors"]`` and overrides the theme's own
      hardcoded colours (``sb2nov`` ships with everything in black);
    * "none" leaves the design untouched, so the default output is
      byte-for-byte what it was before the feature existed.
"""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, ".")

from design_palettes import (
    COLOR_SLOTS,
    NO_ACCENT,
    PALETTE_IDS,
    accent_css_variables,
    contrast_ratio,
    get_palette_colors,
    is_valid_palette_id,
    normalize_palette_id,
    palette_catalog,
    parse_rgb,
)
from render_service import convert_llm_json_to_rendercv_dict

# WCAG AA threshold for normal-sized text.
AA_CONTRAST = 4.5

_MINIMAL_PARSED = {
    "name": "Jane Doe",
    "email": "jane@example.com",
    "summary": "Ingeniera de software con diez años de experiencia.",
    "experience": [
        {
            "company": "Acme",
            "role": "Senior Engineer",
            "dates": "2020-01 - 2021-05",
            "points": ["Construyó APIs", "Redujo el tiempo de build"],
        }
    ],
    "education": [{"school": "Uni", "degree": "Ingeniería", "dates": "2014 - 2018"}],
    "skills": [{"category": "Lenguajes", "items": ["Python", "TypeScript"]}],
}


# ---------------------------------------------------------------------------
# Palette definitions
# ---------------------------------------------------------------------------


class TestPaletteDefinitions:
    def test_no_accent_is_first_in_the_catalogue(self):
        assert PALETTE_IDS[0] == NO_ACCENT

    def test_catalogue_covers_every_palette(self):
        catalog_ids = [entry["id"] for entry in palette_catalog()]
        assert catalog_ids == list(PALETTE_IDS)

    def test_catalogue_entries_have_a_label_and_a_hex_swatch(self):
        for entry in palette_catalog():
            assert entry["label"], f"{entry['id']} has no label"
            assert entry["hex"].startswith("#"), f"{entry['id']} has no hex swatch"
            assert len(entry["hex"]) == 7

    @pytest.mark.parametrize("palette_id", PALETTE_IDS)
    def test_every_palette_defines_all_colour_slots(self, palette_id):
        colors = get_palette_colors(palette_id)
        if not colors:
            # "none" -> the theme's own colours are used, nothing to define.
            return
        assert set(colors) == set(COLOR_SLOTS)

    @pytest.mark.parametrize("palette_id", PALETTE_IDS)
    def test_body_copy_is_always_black(self, palette_id):
        """Rule 1: the body copy is the part an ATS weights most."""
        colors = get_palette_colors(palette_id)
        if not colors:
            return  # "none" -> the theme's own colours are used.
        assert parse_rgb(colors["body"]) == (0, 0, 0)

    @pytest.mark.parametrize("palette_id", PALETTE_IDS)
    def test_every_tone_clears_wcag_aa_on_white(self, palette_id):
        colors = get_palette_colors(palette_id)
        for slot, color in colors.items():
            ratio = contrast_ratio(color)
            assert ratio >= AA_CONTRAST, (
                f"{palette_id}/{slot} = {color} has a contrast of "
                f"{ratio:.2f}:1, below the WCAG AA minimum of {AA_CONTRAST}:1"
            )

    @pytest.mark.parametrize("palette_id", PALETTE_IDS)
    def test_palette_is_not_identical_to_black_and_white(self, palette_id):
        """A palette that renders black would be a lie in the UI."""
        colors = get_palette_colors(palette_id)
        if not colors:
            return
        assert colors["section_titles"] != "rgb(0, 0, 0)"

    def test_section_titles_and_name_share_the_accent(self):
        """One accent, one hierarchy — the name and the titles match."""
        for palette_id in PALETTE_IDS:
            colors = get_palette_colors(palette_id)
            if not colors:
                continue
            assert colors["name"] == colors["section_titles"]
            assert colors["links"] == colors["section_titles"]


# ---------------------------------------------------------------------------
# Normalisation / validation
# ---------------------------------------------------------------------------


class TestNormalisation:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            (None, NO_ACCENT),
            ("", NO_ACCENT),
            ("   ", NO_ACCENT),
            ("none", NO_ACCENT),
            ("NONE", NO_ACCENT),
            ("navy", "navy"),
            ("  Navy  ", "navy"),
            ("TEAL", "teal"),
            ("unknown-palette", NO_ACCENT),
            ("../etc/passwd", NO_ACCENT),
        ],
    )
    def test_normalize_palette_id(self, raw, expected):
        assert normalize_palette_id(raw) == expected

    def test_none_returns_no_overrides(self):
        """Without an accent the design must stay exactly as it was."""
        assert get_palette_colors("none") == {}
        assert get_palette_colors(None) == {}
        assert get_palette_colors("does-not-exist") == {}

    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("none", True),
            ("navy", True),
            ("NAVY", True),
            ("teal", True),
            ("forest", True),
            ("burgundy", True),
            ("plum", True),
            ("slate", True),
            ("chartreuse", False),
            ("", False),
            (None, False),
        ],
    )
    def test_is_valid_palette_id(self, raw, expected):
        assert is_valid_palette_id(raw) is expected


# ---------------------------------------------------------------------------
# CSS variables for the HTML fallback
# ---------------------------------------------------------------------------


class TestAccentCssVariables:
    def test_without_accent_everything_is_black(self):
        variables = accent_css_variables("none")
        assert set(variables) == {"body", "accent", "muted", "rule"}
        assert all(value == "#000000" for value in variables.values())

    def test_accent_reaches_the_css_variables(self):
        variables = accent_css_variables("navy")
        assert variables["accent"] == "#1b3a5c"
        assert variables["body"] == "#000000"
        assert variables["rule"] == "#1b3a5c"


# ---------------------------------------------------------------------------
# Integration with the RenderCV design dict
# ---------------------------------------------------------------------------


class TestRenderServiceIntegration:
    def test_no_accent_leaves_the_design_untouched(self):
        design = convert_llm_json_to_rendercv_dict(_MINIMAL_PARSED)["design"]
        assert "colors" not in design

    @pytest.mark.parametrize("palette_id", [p for p in PALETTE_IDS if p != NO_ACCENT])
    def test_accent_is_injected_into_the_design(self, palette_id):
        design = convert_llm_json_to_rendercv_dict(
            _MINIMAL_PARSED, accent=palette_id
        )["design"]
        assert "colors" in design
        assert design["colors"] == get_palette_colors(palette_id)
        assert design["colors"]["body"] == "rgb(0, 0, 0)"

    def test_unknown_accent_is_ignored_rather_than_fatal(self):
        design = convert_llm_json_to_rendercv_dict(
            _MINIMAL_PARSED, accent="not-a-palette"
        )["design"]
        assert "colors" not in design

    def test_accent_does_not_change_the_cv_content(self):
        """The accent is purely visual: the sections must be identical."""
        plain = convert_llm_json_to_rendercv_dict(_MINIMAL_PARSED)
        colored = convert_llm_json_to_rendercv_dict(_MINIMAL_PARSED, accent="navy")
        assert plain["cv"] == colored["cv"]

    def test_accent_does_not_change_the_layout_settings(self):
        """Same margins, same spacing, same theme — only the colours move."""
        plain = convert_llm_json_to_rendercv_dict(_MINIMAL_PARSED)["design"]
        colored = convert_llm_json_to_rendercv_dict(_MINIMAL_PARSED, accent="navy")["design"]
        assert plain["theme"] == colored["theme"]
        assert plain["entries"] == colored["entries"]
        assert plain["sections"] == colored["sections"]
        assert plain["section_titles"] == colored["section_titles"]

    @pytest.mark.parametrize("theme", ["sb2nov", "classic", "moderncv"])
    def test_design_with_accent_passes_rendercv_validation(self, theme):
        """The colour block must not break RenderCV's own schema."""
        from rendercv.schema.rendercv_model_builder import (
            build_rendercv_dictionary_and_model,
        )

        rendercv_dict = convert_llm_json_to_rendercv_dict(
            _MINIMAL_PARSED, theme=theme, accent="navy"
        )
        _, model = build_rendercv_dictionary_and_model(
            json.dumps(rendercv_dict, ensure_ascii=False)
        )
        # ``sb2nov`` hardcodes black; the explicit ``colors`` block wins.
        assert model.design.colors.name.as_rgb_tuple() == (27, 58, 92)
        assert model.design.colors.body.as_rgb_tuple() == (0, 0, 0)
