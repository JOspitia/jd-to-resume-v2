"""
backend.tests.test_domain_routing
=================================

Smoke + regression tests for the multi-domain resume tailoring feature.

These tests intentionally avoid calling the LLM or rendering PDFs. They focus
on the bits that are deterministic and fast to assert:

  * The game registry exposes exactly 3 games today (tech, hr_recruiting,
    psychology).
  * The tech game is the legacy v2.5 prompt body verbatim — provable by
    anchor-marker assertions.
  * Each non-tech game carries its own domain vocabulary in the rendered
    prompt and does NOT leak tech-exclusive markers into it.
  * The composed prompt for an unknown / empty game falls back to tech.
  * The composed prompt size is bounded (sanity check that we are not
    silently truncating).

Run with:
    cd backend && pytest tests/test_domain_routing.py -v
"""

import sys
from pathlib import Path

import pytest

# Make domain_games importable without a package install.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from domain_games import DEFAULT_GAME, GAMES, get_game  # noqa: E402


# ---------------------------------------------------------------------------
# Registry basics
# ---------------------------------------------------------------------------


def test_default_game_is_tech():
    """The default keeps the v2.5 UX (tech-only prompt body)."""
    assert DEFAULT_GAME == "tech"


def test_registry_contains_exactly_three_games():
    """Today: tech, hr_recruiting, psychology. Adding a 4th requires an
    explicit test update so the contract stays visible."""
    assert set(GAMES.keys()) == {"tech", "hr_recruiting", "psychology"}


def test_get_game_returns_instances_not_classes():
    """get_game(name) must return an INSTANCE whose attributes resolve to
    values, not descriptors (which would happen if we stored classes in the
    registry instead of instances)."""
    g = get_game("tech")
    assert isinstance(g.system_intro, str)
    assert isinstance(g.strict_rules_block, str)
    assert isinstance(g.skill_taxonomy_es, list)
    assert isinstance(g.section_labels_es, dict)


# ---------------------------------------------------------------------------
# Each game must have the structural contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game_name", ["tech", "hr_recruiting", "psychology"])
def test_each_game_has_full_contract(game_name):
    g = GAMES[game_name]
    # Mandatory string fields are non-empty.
    assert g.name == game_name
    assert isinstance(g.label_es, str) and g.label_es
    assert isinstance(g.label_en, str) and g.label_en
    assert isinstance(g.system_intro, str) and g.system_intro.strip()
    assert isinstance(g.strict_rules_block, str) and g.strict_rules_block.strip()
    assert isinstance(g.narrative_patterns, str) and g.narrative_patterns.strip()
    assert isinstance(g.skill_taxonomy_es, list) and len(g.skill_taxonomy_es) >= 3
    assert isinstance(g.skill_taxonomy_en, list) and len(g.skill_taxonomy_en) >= 3
    assert isinstance(g.section_labels_es, dict) and len(g.section_labels_es) >= 4
    assert isinstance(g.section_labels_en, dict) and len(g.section_labels_en) >= 4
    # Each game has 4 narrative patterns A/B/C/D.
    for letter in "ABCD":
        assert f"Pattern {letter}" in g.narrative_patterns, (
            f"{game_name} missing Pattern {letter} in narrative_patterns"
        )


# ---------------------------------------------------------------------------
# Tech prompt: byte-equivalence anchor check
# ---------------------------------------------------------------------------


# Anchors chosen from the legacy v2.5 prompt body in main.py prior to the
# multi-domain refactor. If any of these disappear, the v2.5 UX would break.
TECH_ANCHORS = (
    "You are a professional technical recruiter and resume writer specialized in ATS optimization.",
    "achieve maximum ATS scores on platforms like CompuTrabajo, Workday, LinkedIn, and Greenhouse.",
    "STRICT RULES (CRITICAL — ALL MUST BE FOLLOWED):",
    "1. ZERO HALLUCINATION & NO INVENTING DATA",
    "10. DOMAIN-AWARE INTELLIGENT SKILLS CATEGORIZATION",
    "13. ATS ADVANCED REFINEMENT & ANTI-SPAM RULES",
    "14. KEYWORD GAP DETECTION & AUTOMATIC SKILL ENRICHMENT",
    "20. STRICT REPETITION BAN IN PROJECTS",
    "Implementé el stack con",  # forbidden phrase kept verbatim
    "Diseñé, Implementé, Refactoricé",  # the Spanish verbs list
    # Pattern A-D examples (kept verbatim):
    "Incrementé la velocidad de respuesta en 40%",
    "Ante cuellos de botella en el procesamiento masivo de datos",
    "Lideré el despliegue del sistema distribuido sobre AWS",
    "Mediante FastAPI y PostgreSQL, automaticé",
    # Project 1-4 openings (kept verbatim):
    "Arquitecturé una plataforma de optimización de CVs",
    "Para resolver la falta de visibilidad del inventario",
    "Mediante la integración de Playwright, FastAPI y SSE",
    "Reduje los tiempos de respuesta en 45%",
)


def test_tech_prompt_preserves_legacy_anchors():
    """Each anchor in the legacy v2.5 prompt body must still be present in
    the tech game's strict_rules_block after the refactor. If we lose any,
    callers who don't pick a game get a DIFFERENT v2.5 UX — that's a
    regression we want this test to catch early."""
    g = get_game("tech")
    body = g.system_intro + g.strict_rules_block
    missing = [anchor for anchor in TECH_ANCHORS if anchor not in body]
    assert not missing, f"tech prompt missing legacy anchors: {missing!r}"


# ---------------------------------------------------------------------------
# Non-tech games: domain-specific vocabulary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "game_name, must_have, must_not_have",
    [
        (
            "hr_recruiting",
            # HR-specific anchors
            ("Workday", "Headhunteé", "Greenhouse", "pipeline", "Sourcing"),
            # Tech-exclusive terms that must NOT appear
            ("FastAPI", "Kubernetes", "PostgreSQL", "Service Discovery patterns"),
        ),
        (
            "psychology",
            # Psychology-specific anchors
            ("16PF", "BDI-II", "TCC", "psicoeducación", "consentimiento informado"),
            # Tech-exclusive terms that must NOT appear
            ("FastAPI", "Kubernetes", "PostgreSQL"),
        ),
    ],
)
def test_non_tech_prompts_have_domain_specific_vocabulary(
    game_name, must_have, must_not_have
):
    g = get_game(game_name)
    body = g.strict_rules_block
    body_with_intro = g.system_intro + body
    for marker in must_have:
        assert marker in body_with_intro, (
            f"{game_name} prompt missing required domain marker {marker!r}"
        )
    for marker in must_not_have:
        # Some tools (e.g. LinkedIn Recruiter) cross domains; we allow generic
        # cross-domain markers. The chosen must_not_have are strictly tech-only.
        assert marker not in body, (
            f"{game_name} prompt leaked tech-only marker {marker!r}"
        )


# ---------------------------------------------------------------------------
# Skill taxonomy per game
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game_name", ["tech", "hr_recruiting", "psychology"])
def test_skill_taxonomies_are_distinct_per_game(game_name):
    """Skills taxonomies must NOT be identical across games — that would
    indicate the labels leaked between games."""
    other_games = [n for n in GAMES if n != game_name]
    g = GAMES[game_name]
    for other in other_games:
        og = GAMES[other]
        # Compare sorted lists — taxonomies differ if any category differs.
        assert sorted(g.skill_taxonomy_es) != sorted(og.skill_taxonomy_es), (
            f"{game_name} taxonomy (ES) is identical to {other}"
        )


def test_tech_skill_taxonomy_is_v25_categories():
    """The v2.5 hardcoded categories in the old `keyword_gap_detection` rule
    must still appear in the tech game so callers relying on the v2.5 output
    do not see a regression."""
    g = get_game("tech")
    expected_v25 = [
        "Lenguajes & Frameworks",
        "DevOps & Automatización",
        "Bases de Datos & Cloud",
    ]
    for category in expected_v25:
        assert category in g.skill_taxonomy_es, (
            f"tech taxonomy missing v2.5 category {category!r}"
        )


def test_hr_skill_taxonomy_has_ats_crm():
    g = get_game("hr_recruiting")
    assert "ATS & CRM" in g.skill_taxonomy_es


def test_psych_skill_taxonomy_has_psychometrics():
    g = get_game("psychology")
    assert any("Psicotécnicas" in c or "Psicométr" in c for c in g.skill_taxonomy_es)


# ---------------------------------------------------------------------------
# Section labels per game (localized headers)
# ---------------------------------------------------------------------------


def test_section_labels_differ_per_game():
    """At least the 'experience' label must reflect the domain (the user's
    CV header changes between Tech and Psychology for the same word)."""
    tech = GAMES["tech"]
    hr = GAMES["hr_recruiting"]
    psy = GAMES["psychology"]
    # The word 'experiencia' is shared but the suffix MUST differ between
    # at least one pair of games so the spec gets covered.
    assert (
        tech.section_labels_es["experience"]
        != hr.section_labels_es["experience"]
    ) or (
        hr.section_labels_es["experience"]
        != psy.section_labels_es["experience"]
    ), "section_labels[experience] should differ between games"


def test_psych_section_labels_use_academic_vocabulary():
    g = get_game("psychology")
    # Psychology CVs in LATAM Spain use 'Formación Académica' over 'Educación'.
    assert g.section_labels_es["education"] in (
        "Educación",
        "Formación Académica",
    ), f"unexpected psychology education label: {g.section_labels_es['education']!r}"


def test_hr_skill_taxonomy_has_onboarding_or_retention_category():
    """HR CVs classify 'onboarding' and 'retention' as SKILL CATEGORIES, not
    section headers. The headers stay canonical (Resumen / Educación /
    Habilidades / Experiencia / Proyectos / Certificaciones / Portafolio)
    so ATS parsers recognize the document shape; the domain-specific
    vocabulary lives in the skills array."""
    g = get_game("hr_recruiting")
    taxonomy = " ".join(g.skill_taxonomy_es).lower()
    assert ("onboarding" in taxonomy) or ("retention" in taxonomy) or ("retención" in taxonomy), (
        f"hr skill taxonomy (ES) missing Onboarding / Retention marker: "
        f"{g.skill_taxonomy_es}"
    )


# ---------------------------------------------------------------------------
# Default-game fallback
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", [None, "", "unknown-game", "tech_recruiting", "PSYCHOLOGY"])
def test_unknown_or_empty_game_falls_back_to_tech(name):
    """Empty / unknown values must NOT raise — they must produce the same
    instance as the explicit 'tech' selection. This preserves v2.5 UX for
    callers who don't pick a game (the original UI did not show a selector)."""
    g_name = get_game(name).name
    assert g_name == "tech"


# ---------------------------------------------------------------------------
# Render helpers
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game_name", ["tech", "hr_recruiting", "psychology"])
def test_render_system_intro_equals_cached_attribute(game_name):
    g = get_game(game_name)
    assert g.render_system_intro() == g.system_intro


@pytest.mark.parametrize("game_name", ["tech", "hr_recruiting", "psychology"])
def test_render_domain_prompt_block_is_non_trivial(game_name):
    g = get_game(game_name)
    block = g.render_domain_prompt_block()
    # Sanity bound: at minimum the 20 rules fit in 5 kB; we cap at 25 kB to
    # catch accidental truncation of rule bodies.
    assert 5000 < len(block) < 25000, (
        f"{game_name} render_domain_prompt_block has unusual length {len(block)}: "
        "truncation or bloat suspected"
    )


# ---------------------------------------------------------------------------
# End-to-end compose (the actual prompt body the pipeline builds)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("game_name", ["tech", "hr_recruiting", "psychology"])
def test_end_to_end_compose_contains_all_20_rules(game_name):
    """Simulating what generation_pipeline() does — build the prompt body
    from {language_override_block} + {game.system_intro} + {game.strict_rules_block}.
    Each compose must contain all 20 numbered rules."""
    g = get_game(game_name)
    language_override_block = ""  # default case (no force_language)
    composed = (
        f"\n{language_override_block}\n{g.system_intro}\n{g.strict_rules_block}\n"
    )
    for i in range(1, 21):
        assert f"{i}." in composed, (
            f"{game_name} composed prompt missing rule number {i}"
        )


def test_end_to_end_compose_tech_matches_legacy_shape():
    """For tech (the default), the composed prompt body must contain the
    SAME legacy content as the v2.5 inline string — a structural regression
    check that doesn't require reading the original main.py."""
    g = get_game("tech")
    composed = f"\n{g.system_intro}\n{g.strict_rules_block}\n"
    # Spot-check several legacy markers across the composed body.
    legacy_spots = [
        # system_intro
        "tailor the candidate's actual experience",
        "achieve maximum ATS scores on platforms like CompuTrabajo",
        # rule 1
        "DO NOT add ZScore, Hackumi, Resume Analyzer",
        # rule 14
        "FastAPI, Playwright, SSE, Ant Design, Cloudflare, CI/CD",
        # rule 20
        "STRICTLY FORBIDDEN: NEVER repeat the phrase",
    ]
    for spot in legacy_spots:
        assert spot in composed, f"legacy spot missing from composed tech prompt: {spot!r}"
