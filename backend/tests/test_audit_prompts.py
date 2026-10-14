"""
backend.tests.test_audit_prompts
=================================

Tests for the domain-aware audit prompt builder (`audit_prompts.py`).

Covers:
  * Tech audit prompt preserves the v2.5 vocabulary (FastAPI / Docker /
    Pytest / CI/CD anchors).
  * HR audit prompt carries HR markers and DOES NOT recommend tech-only
    artifacts like 'Docker' or 'Kubernetes'.
  * Psychology audit prompt carries psychometrics markers and DOES NOT
    recommend tech-only artifacts.
  * Each prompt embeds the game's ES skill taxonomy in the system prompt.
  * JSON example in the audit prompt uses per-game seeds so the response
    shape stays consistent across domains.
  * Unknown game names fall back to tech seeds (safe default).

Run with:
    cd backend && pytest tests/test_audit_prompts.py -v
"""

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain_games import GAMES, get_game  # noqa: E402
from audit_prompts import build_audit_prompt  # noqa: E402


RESUME_TEXT = "Sample resume text used in tests."
JD_TEXT = "Sample job description used in tests."


def _build(game_name: str) -> str:
    return build_audit_prompt(RESUME_TEXT, JD_TEXT, GAMES[game_name])


# ---------------------------------------------------------------------------
# Tech (legacy preservation)
# ---------------------------------------------------------------------------


def test_tech_audit_prompt_preserves_v25_anchors():
    """Tech audit must keep the legacy v2.5 inventory so existing callers
    (who do not pass domain_game) get identical vocabulary."""
    prompt = _build("tech")
    # The legacy v2.5 inventory:
    legacy = [
        "Python",
        "FastAPI",
        "React",
        "SQL",
        "Docker",
        "Pytest",
        "CI/CD",
    ]
    for marker in legacy:
        assert marker in prompt, f"tech audit prompt missing legacy marker {marker!r}"


def test_tech_audit_prompt_embeds_tech_label():
    prompt = _build("tech")
    assert GAMES["tech"].label_es in prompt


# ---------------------------------------------------------------------------
# HR / Recruiting
# ---------------------------------------------------------------------------


def test_hr_audit_prompt_uses_hr_seed_keywords():
    prompt = _build("hr_recruiting")
    hr_anchors = ["Workday", "LinkedIn Recruiter", "Entrevista por Competencias",
                  "Greenhouse", "Boolean Search", "Sourcing Pipeline"]
    for marker in hr_anchors:
        assert marker in prompt, f"hr audit prompt missing required marker {marker!r}"


def test_hr_audit_prompt_does_not_mention_docker_in_recommendation():
    """Specifically: actionable_tips must NOT recommend 'add Docker' on HR."""
    prompt = _build("hr_recruiting")
    # The action tip from v2.5 was:
    #   "Añade la palabra clave 'Docker' si posees conocimientos en contenedores."
    # If we see literal Docker mention, the legacy leak is still there.
    assert "añade la palabra clave 'Docker'" not in prompt.lower()
    assert "add 'Docker'" not in prompt
    assert "**docker**" not in prompt.lower()


def test_hr_audit_prompt_embeds_hr_label_and_taxonomy():
    prompt = _build("hr_recruiting")
    g = GAMES["hr_recruiting"]
    assert g.label_es in prompt
    for category in g.skill_taxonomy_es[:3]:
        assert category in prompt, (
            f"hr audit prompt missing ES taxonomy category {category!r}"
        )


# ---------------------------------------------------------------------------
# Psychology
# ---------------------------------------------------------------------------


def test_psych_audit_prompt_uses_psych_seed_keywords():
    prompt = _build("psychology")
    psych_anchors = ["16PF", "Entrevista por Competencias",
                     "consentimiento informado", "BDI-II", "psicoeducación", "TCC"]
    for marker in psych_anchors:
        assert marker in prompt, f"psych audit prompt missing required marker {marker!r}"


def test_psych_audit_prompt_does_not_mention_docker_in_recommendation():
    prompt = _build("psychology")
    assert "añade la palabra clave 'Docker'" not in prompt.lower()
    assert "add 'Docker'" not in prompt
    assert "**docker**" not in prompt.lower()


def test_psych_audit_prompt_embeds_psych_label_and_taxonomy():
    prompt = _build("psychology")
    g = GAMES["psychology"]
    assert g.label_es in prompt
    for category in g.skill_taxonomy_es[:3]:
        assert category in prompt, (
            f"psych audit prompt missing ES taxonomy category {category!r}"
        )


# ---------------------------------------------------------------------------
# Cross-cutting: each prompt mentions the game's vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "game_name, must_have_together",
    [
        ("tech", "Lenguajes & Frameworks"),
        ("hr_recruiting", "ATS & CRM"),
        ("psychology", "Psicotécnicas"),
    ],
)
def test_each_audit_prompt_embeds_a_taxonomy_category(game_name, must_have_together):
    """Smoke check that the composed prompt carries an unmistakable taxonomy
    marker for each domain so the LLM can't fall back to the generic
    'compuTrabajo / Workday / Greenhouse' tech-only vocabulary."""
    prompt = _build(game_name)
    assert must_have_together in prompt


# ---------------------------------------------------------------------------
# JSON example shape uses per-game seeds
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "game_name, expected_marker",
    [
        ("tech", "Pytest"),  # legacy v2.5 inventory item
        ("hr_recruiting", "Greenhouse"),
        ("psychology", "BDI-II"),
    ],
)
def test_audit_json_example_carries_per_game_seed_marker(game_name, expected_marker):
    """The JSON example inside the prompt must use the per-game seeds so
    the LLM is anchored to the right vocabulary."""
    prompt = _build(game_name)
    assert expected_marker in prompt


# ---------------------------------------------------------------------------
# Unknown / accidental game names: fallback
# ---------------------------------------------------------------------------


def test_audit_prompt_unknown_game_falls_back_to_tech_seeds():
    """If a caller passes a DomainGame with an unknown `.name`, the seed
    selection must fall back to the tech inventory (safe default)."""
    class _FakeGame:
        name = "unknown-game"
        label_es = "Desconocido"

        @property
        def skill_taxonomy_es(self):
            return ["Categoria de prueba"]

    prompt = build_audit_prompt(RESUME_TEXT, JD_TEXT, _FakeGame())
    # The safe default keeps tech inventory available.
    assert "Docker" in prompt
    assert "Pytest" in prompt
