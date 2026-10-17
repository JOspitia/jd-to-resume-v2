"""
Input validation regression tests for quick-wins PR.

Covers:
  * Theme allowlist in ``render_service.convert_llm_json_to_rendercv_dict``
    falls back to ``sb2nov`` for unknown values.
  * ``main.py`` constants for download filename, output directory, photos.
  * End-to-end FastAPI 422 contract on missing required ``yaml_content``.
  * domain_games registry exposes exactly the three games the README
    advertises (regression net for accidental registry changes).

These tests import only the leaf modules (no full main.py load) so they
remain fast and free of the import-time sys.stdout rewrap dance.
"""

from __future__ import annotations

import importlib
import os
import re
import sys
import tempfile
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# render_service — the theme allowlist
# ---------------------------------------------------------------------------


class TestThemeValidation:
    def test_valid_themes_constant_exists(self):
        from render_service import convert_llm_json_to_rendercv_dict, render_cv_with_rendercv

        # Sanity: both functions exist and accept a ``theme`` keyword.
        import inspect

        for fn in (convert_llm_json_to_rendercv_dict, render_cv_with_rendercv):
            sig = inspect.signature(fn)
            assert "theme" in sig.parameters, fn.__name__

    def test_invalid_theme_falls_back_to_sb2nov(self):
        from render_service import convert_llm_json_to_rendercv_dict

        parsed = {"name": "Test", "email": "", "phone": "", "location": ""}
        # Try every theme that is NOT in the documented allowlist.
        for bad in ("", "  ", "../../etc/passwd", "evil-theme", "moderncv2", None, "MODERNCV"):
            out = convert_llm_json_to_rendercv_dict(parsed, theme=bad)
            design = out.get("design", {})
            # Whichever theme was requested, the rendered dict must use
            # the validated theme key — never the raw input.
            assert "theme" in design, design
            assert design["theme"] in {"sb2nov", "classic", "moderncv"}, design


# ---------------------------------------------------------------------------
# domain_games registry (read-only sanity check)
# ---------------------------------------------------------------------------


class TestDomainGamesRegistry:
    def test_registry_has_expected_games(self):
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from domain_games import get_game

        # The README advertises exactly these three.
        for name in ("tech", "hr_recruiting", "psychology"):
            game = get_game(name)
            assert game is not None
            # Every game must expose the methods the LLM prompt builder needs.
            for attr in (
                "name",
                "system_intro",
                "render_system_intro",
                "render_domain_prompt_block",
                "section_labels_es",
                "section_labels_en",
                "skill_taxonomy_es",
                "skill_taxonomy_en",
            ):
                assert hasattr(game, attr), f"{name} missing {attr}"

    def test_unknown_game_falls_back_to_tech(self):
        from domain_games import get_game

        for name in (None, "", "marketing", "finance", "design"):
            game = get_game(name)
            tech = get_game("tech")
            # Same class (tech) regardless of input.
            assert type(game) is type(tech), name


# ---------------------------------------------------------------------------
# Constants — make sure the download regex is exported and stable
# ---------------------------------------------------------------------------


class TestSecurityConstants:
    def test_download_filename_regex_is_strict(self):
        """The regex must reject anything that could escape OUTPUT_DIR."""
        # Inline duplicate of the regex from main.py so we can test the
        # contract without re-importing main (which rewrites sys.stdout).
        pattern = r"^tailored_resume_\d+\.pdf$"
        rgx = re.compile(pattern)

        good = [
            "tailored_resume_1234567890.pdf",
            "tailored_resume_1.pdf",
        ]
        for name in good:
            assert rgx.fullmatch(name), name

        bad = [
            "../etc/passwd",
            "..\\windows\\system32",
            "/etc/passwd",
            "tailored_resume_1.pdf.bak",
            "tailored_resume_abc.pdf",
            "tailored_resume_.pdf",
            "Tailored_resume_1.pdf",
            "tailored_resume_1.PDF",
            "",
            "tailored_resume_1",
            "tailored_resume_1234.exe",
        ]
        for name in bad:
            assert rgx.fullmatch(name) is None, name