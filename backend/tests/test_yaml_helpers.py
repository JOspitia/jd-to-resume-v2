"""
backend.tests.test_yaml_helpers
================================

Tests for the YAML editor helpers in `backend/yaml_helpers.py`.

Covers:
  * `serialize_resume_data_as_text` — narrative output, missing fields
    handled gracefully, all sections rendered, unicode preserved.
  * `yaml_safe_dump_unicode` — roundtrip preserves data and unicode.
  * `yaml_safe_dump_unicode` — order of insertion is preserved
    (sort_keys=False contract, used by the YAML editor to keep human-
    readable order of fields in the textarea).

The `_run_audit_against_text` orchestration lives in main.py (uses
call_llm_api + _build_audit_prompt) so it is tested indirectly through
the existing audit_prompts tests + the upcoming endpoint tests
(test_yaml_endpoints.py in T9).

Run with:
    cd backend && pytest tests/test_yaml_helpers.py -v
"""

import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from yaml_helpers import (  # noqa: E402
    serialize_resume_data_as_text,
    yaml_safe_dump_unicode,
)


# ---------------------------------------------------------------------------
# serialize_resume_data_as_text
# ---------------------------------------------------------------------------


def test_serialize_minimal_data_returns_narrative():
    data = {"name": "Jane Doe"}
    out = serialize_resume_data_as_text(data)
    assert "Name: Jane Doe" in out
    # Even with only a name, the function should not crash and should
    # return a non-empty string.
    assert isinstance(out, str) and out.strip() != ""


def test_serialize_contact_lines_all_present():
    data = {
        "name": "Jane",
        "location": "Buenos Aires, Argentina",
        "phone": "+54 11 1234-5678",
        "email": "jane@example.com",
        "portfolio": "https://jane.dev",
        "linkedin": "https://linkedin.com/in/jane",
        "github": "https://github.com/jane",
    }
    out = serialize_resume_data_as_text(data)
    for line in [
        "Name: Jane",
        "Location: Buenos Aires, Argentina",
        "Phone: +54 11 1234-5678",
        "Email: jane@example.com",
        "Portfolio: https://jane.dev",
        "LinkedIn: https://linkedin.com/in/jane",
        "GitHub: https://github.com/jane",
    ]:
        assert line in out, f"missing contact line: {line!r}"


def test_serialize_skips_empty_contact_fields():
    data = {
        "name": "Jane",
        "location": "",
        "phone": None,
        "email": "jane@example.com",
    }
    out = serialize_resume_data_as_text(data)
    assert "Location:" not in out  # empty was skipped, not blank line
    assert "Phone:" not in out
    assert "Email: jane@example.com" in out


def test_serialize_summary_section_appears_with_blank_line_before():
    data = {"name": "Jane", "summary": "3-line summary here."}
    out = serialize_resume_data_as_text(data)
    # Section header is preceded by a blank line for readability.
    assert "\n\nSummary:\n3-line summary here." in out


def test_serialize_experience_renders_role_company_dates_and_bullets():
    data = {
        "experience": [
            {
                "role": "Senior Psychologist",
                "company": "Acme",
                "dates": "2022-01 - Actualidad",
                "points": [
                    "Evaluated 200+ candidates using 16PF + Wartegg.",
                    "Built assessment center playbook for 12 areas.",
                ],
            }
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "Experience:" in out
    assert "  - Senior Psychologist | Acme (2022-01 - Actualidad)" in out
    assert "    * Evaluated 200+ candidates using 16PF + Wartegg." in out
    assert "    * Built assessment center playbook for 12 areas." in out


def test_serialize_experience_handles_only_role_no_company():
    data = {
        "experience": [
            {"role": "Analista", "dates": "2023-01 - 2023-12", "points": ["Did X."]}
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "  - Analista (2023-01 - 2023-12)" in out


def test_serialize_experience_skips_malformed_entries_without_crashing():
    # Garbage in, no crash out.
    data = {
        "experience": [
            "not a dict",  # should be skipped
            {"role": "Valid", "points": ["Good point."]},
            None,  # should be skipped
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "Valid" in out
    assert "Good point." in out
    # No crash, output is a string.
    assert isinstance(out, str)


def test_serialize_skips_empty_points_in_experience():
    data = {
        "experience": [
            {"role": "Boss", "points": ["Real point.", "", None, "Another real."]}
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "    * Real point." in out
    assert "    * Another real." in out


def test_serialize_skills_grouped_by_category():
    data = {
        "skills": [
            {"category": "Pruebas Psicotécnicas", "items": ["16PF", "DISC", "Wartegg"]},
            {"category": "Evaluación", "items": ["WAIS-IV", "Vineland"]},
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "Skills:" in out
    assert "  - Pruebas Psicotécnicas: 16PF, DISC, Wartegg" in out
    assert "  - Evaluación: WAIS-IV, Vineland" in out


def test_serialize_skills_with_no_items_is_skipped():
    data = {
        "skills": [
            {"category": "Empty", "items": []},
            {"category": "NonEmpty", "items": ["X"]},
        ]
    }
    out = serialize_resume_data_as_text(data)
    # Use the bullet prefix to avoid 'Empty' being a substring of 'NonEmpty'.
    assert "- Empty:" not in out
    assert "- NonEmpty: X" in out


def test_serialize_education_renders_degree_school_dates():
    data = {
        "education": [
            {
                "school": "Universidad de Buenos Aires",
                "degree": "Lic. en Psicología",
                "dates": "2014 - 2019",
            }
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "Education:" in out
    assert "  - Lic. en Psicología — Universidad de Buenos Aires (2014 - 2019)" in out


def test_serialize_projects_renders_name_dates_and_bullets():
    data = {
        "projects": [
            {
                "name": "Assessment Center",
                "dates": "2024-01",
                "points": ["Designed 4-station playbook.", "Cut time-to-hire 30%."],
            }
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "Projects:" in out
    assert "  - Assessment Center (2024-01)" in out
    assert "    * Designed 4-station playbook." in out
    assert "    * Cut time-to-hire 30%." in out


def test_serialize_achievements_renders_as_bullets():
    data = {
        "achievements": [
            "SHRM-CP",
            "Publicación en Revista Latinoamericana de Psicología",
        ]
    }
    out = serialize_resume_data_as_text(data)
    assert "Achievements:" in out
    assert "  - SHRM-CP" in out
    assert "  - Publicación en Revista Latinoamericana de Psicología" in out


def test_serialize_unicode_preserved_throughout():
    data = {
        "name": "María José Núñez",
        "location": "Bogotá, Colombia",
        "summary": "Psicóloga con énfasis en intervención organizacional.",
        "experience": [
            {
                "role": "Psicóloga Clínica",
                "company": "Clínica Alemana",
                "points": [
                    "Aplicó baterías 16PF, DISC y Wartegg a más de 200 candidatos.",
                ],
            }
        ],
    }
    out = serialize_resume_data_as_text(data)
    assert "María José Núñez" in out
    assert "Bogotá, Colombia" in out
    assert "Psicóloga con énfasis en intervención organizacional." in out
    assert "Clínica Alemana" in out
    assert "Psicóloga Clínica" in out
    assert "16PF, DISC y Wartegg" in out


def test_serialize_empty_dict_returns_minimal_output():
    out = serialize_resume_data_as_text({})
    # Just a trailing newline (no name, no sections).
    assert out == "\n"


def test_serialize_full_realistic_payload():
    """Smoke test that walks through a realistic full payload (psychology
    profile) and asserts every section header appears in the output."""
    data = {
        "name": "Ana Pérez",
        "location": "CDMX, México",
        "phone": "+52 55 1234 5678",
        "email": "ana@example.com",
        "linkedin": "https://linkedin.com/in/ana",
        "summary": "Psicóloga organizacional con 8 años de experiencia.",
        "experience": [
            {
                "role": "Senior Consultant",
                "company": "Talent Lab",
                "dates": "2021-03 - Actualidad",
                "points": ["Lideró assessment centers para 15 clientes."],
            }
        ],
        "skills": [
            {"category": "Pruebas Psicotécnicas", "items": ["16PF", "DISC"]},
        ],
        "education": [
            {
                "school": "UNAM",
                "degree": "Lic. en Psicología",
                "dates": "2012 - 2016",
            }
        ],
        "projects": [
            {
                "name": "Clima Organizacional 2023",
                "points": ["Encuestó 1200 colaboradores."],
            }
        ],
        "achievements": ["Publicación en Revista A"],
    }
    out = serialize_resume_data_as_text(data)
    for section in ("Name:", "Location:", "Phone:", "Email:", "LinkedIn:",
                    "Summary:", "Experience:", "Skills:", "Education:",
                    "Projects:", "Achievements:"):
        assert section in out, f"missing section header: {section!r}"


# ---------------------------------------------------------------------------
# yaml_safe_dump_unicode
# ---------------------------------------------------------------------------


def test_yaml_dump_load_roundtrip_preserves_data():
    data = {
        "name": "Jane Doe",
        "experience": [
            {"role": "Engineer", "company": "Acme", "dates": "2020-01 - 2023-12"}
        ],
        "skills": [{"category": "Backend", "items": ["Python", "FastAPI"]}],
    }
    dumped = yaml_safe_dump_unicode(data)
    parsed = yaml.safe_load(dumped)
    assert parsed == data


def test_yaml_dump_preserves_unicode_characters():
    data = {
        "name": "María José Núñez",
        "summary": "Psicóloga — intervención organizacional.",
        "skills": [{"category": "Pruebas", "items": ["16PF", "DISC", "Wartegg"]}],
    }
    dumped = yaml_safe_dump_unicode(data)
    assert "María José Núñez" in dumped
    assert "Psicóloga" in dumped
    assert "16PF" in dumped
    # Roundtrip too.
    parsed = yaml.safe_load(dumped)
    assert parsed == data


def test_yaml_dump_preserves_key_order():
    """sort_keys=False contract: the keys appear in the dumped YAML in
    the same order they were inserted into the dict. This matters for
    the YAML editor — the textarea should look human-curated, not
    alphabetically sorted."""
    data = {
        "name": "Jane",
        "summary": "...",
        "experience": [],
        "skills": [],
        "education": [],
        "achievements": [],
    }
    dumped = yaml_safe_dump_unicode(data)
    # Each top-level key should appear in the order above. We compare
    # relative positions only — the first key can legitimately be at
    # position 0 in the dumped string.
    positions = [
        dumped.find(key + ":")
        for key in ("name", "summary", "experience", "skills", "education", "achievements")
    ]
    assert all(p >= 0 for p in positions), f"missing keys: {positions=}"
    assert positions == sorted(positions), (
        f"keys not in insertion order: {positions=}"
    )


def test_yaml_dump_handles_special_characters_safely():
    """The yaml.safe_dump call must not blow up on values with quotes,
    colons, newlines, etc. — these are realistic in résumé data (e.g.
    bullet points with quotes)."""
    data = {
        "summary": 'Quote: "líder" - Acme: "10y exp".\nNewline above.',
        "experience": [
            {
                "role": "Engineer; Senior",
                "points": [
                    "Handled edge case: foo: bar.",
                    "Used 'single' and \"double\" quotes.",
                ],
            }
        ],
    }
    dumped = yaml_safe_dump_unicode(data)
    # Roundtrip should be lossless.
    parsed = yaml.safe_load(dumped)
    assert parsed == data


def test_yaml_dump_no_unicode_escapes_for_spanish_accents():
    """allow_unicode=True contract: the dump must NOT escape accented
    characters (e.g. 'á' must NOT be escaped to '\\u00e1')."""
    data = {"name": "María", "city": "Bogotá"}
    dumped = yaml_safe_dump_unicode(data)
    assert "María" in dumped
    assert "Bogotá" in dumped
    # The escape '\\u00e1' would be a sign of allow_unicode=False.
    assert "\\u00e1" not in dumped
    assert "\\u00f3" not in dumped


def test_yaml_dump_handles_nested_structures():
    data = {
        "experience": [
            {
                "company": "Acme",
                "points": [
                    "Bullet 1",
                    "Bullet 2",
                ],
            }
        ],
        "skills": [
            {"category": "Cat 1", "items": ["a", "b", "c"]},
            {"category": "Cat 2", "items": ["d"]},
        ],
    }
    dumped = yaml_safe_dump_unicode(data)
    parsed = yaml.safe_load(dumped)
    assert parsed == data


def test_yaml_dump_preserves_empty_lists():
    """The YAML editor shows what the user is editing; if the AI left
    an empty list (e.g. no projects), the dump should keep it."""
    data = {"projects": [], "achievements": []}
    dumped = yaml_safe_dump_unicode(data)
    parsed = yaml.safe_load(dumped)
    assert parsed == {"projects": [], "achievements": []}
    # And the dumped string should mention them as empty lists, not omit them.
    assert "projects: []" in dumped
    assert "achievements: []" in dumped
