"""
Tests for date-range parsing and RenderCV date validation.

Regression coverage for the silent Playwright fallback: ``dates_str.split("-")``
split on *every* hyphen, so the standard ``YYYY-MM - YYYY-MM`` shape lost its
end date and fell back to the hardcoded "2020" placeholder. When the start
year was greater than 2020 RenderCV rejected the whole CV ("start_date cannot
be after end_date") and the render silently fell back to the slower Playwright
HTML renderer, ignoring the theme the user picked.

Covers:
    * ``split_date_range`` handles the shapes the LLM actually emits.
    * ``clean_date_optional`` never fabricates a placeholder year.
    * ``resolve_date_pair`` guarantees an ordered pair (or drops the end date).
    * The rendered dict passes RenderCV's own model validation.
"""

from __future__ import annotations

import json
import sys

import pytest

sys.path.insert(0, ".")

from render_service import (
    clean_date_optional,
    convert_llm_json_to_rendercv_dict,
    resolve_date_pair,
    split_date_range,
)


# ---------------------------------------------------------------------------
# split_date_range
# ---------------------------------------------------------------------------


class TestSplitDateRange:
    @pytest.mark.parametrize(
        "raw,expected",
        [
            ("2018-08 - 2021-05", ("2018-08", "2021-05")),
            ("2021 - hoy", ("2021", "hoy")),
            ("2018", ("2018", "")),
            ("2018-2021", ("2018", "2021")),
            ("Sept 2019 - Feb 2021", ("Sept 2019", "Feb 2021")),
            ("2021/05 - 2023/08", ("2021/05", "2023/08")),
            ("2016 to 2018", ("2016", "2018")),
            ("2016 hasta 2018", ("2016", "2018")),
        ],
    )
    def test_splits_without_breaking_year_month(self, raw, expected):
        assert split_date_range(raw) == expected

    def test_empty_string(self):
        assert split_date_range("") == ("", "")
        assert split_date_range("   ") == ("", "")

    def test_hyphen_inside_year_month_is_not_a_separator(self):
        """The regression: '2018-08 - 2021-05' used to yield end '05'."""
        start, end = split_date_range("2018-08 - 2021-05")
        assert start == "2018-08"
        assert end == "2021-05"


# ---------------------------------------------------------------------------
# clean_date_optional
# ---------------------------------------------------------------------------


class TestCleanDateOptional:
    def test_parses_year_month(self):
        assert clean_date_optional("2018-08") == "2018-08"

    def test_parses_year(self):
        assert clean_date_optional("2018") == "2018"

    def test_parses_present(self):
        assert clean_date_optional("hoy") == "present"
        assert clean_date_optional("Present") == "present"

    def test_never_fabricates_a_year(self):
        """Unparseable input must yield None, not the '2020' placeholder."""
        assert clean_date_optional("") is None
        assert clean_date_optional("   ") is None
        assert clean_date_optional("sin fecha") is None


# ---------------------------------------------------------------------------
# resolve_date_pair
# ---------------------------------------------------------------------------


class TestResolveDatePair:
    def test_keeps_a_valid_range(self):
        assert resolve_date_pair("2018-08", "2021-05") == ("2018-08", "2021-05")

    def test_drops_the_end_date_when_the_range_is_inverted(self):
        """RenderCV rejects start > end; dropping the end date keeps it valid."""
        start, end = resolve_date_pair("2026-08", "2020-05")
        assert start == "2026-08"
        assert end is None

    def test_default_end_is_used_when_no_end_is_given(self):
        assert resolve_date_pair("2021", "", default_end="present") == (
            "2021",
            "present",
        )

    def test_omits_unparseable_dates(self):
        start, end = resolve_date_pair("sin fecha", "", default_end="present")
        assert start is None
        assert end is None


# ---------------------------------------------------------------------------
# convert_llm_json_to_rendercv_dict
# ---------------------------------------------------------------------------


class TestRendercvDictDates:
    def _sections(self, parsed):
        return convert_llm_json_to_rendercv_dict(parsed)["cv"]["sections"]

    def test_education_keeps_both_dates(self):
        sections = self._sections(
            {
                "name": "Test",
                "education": [
                    {"school": "U", "degree": "CS", "dates": "2018-08 - 2021-05"}
                ],
            }
        )
        entry = sections["Education"][0]
        assert entry["start_date"] == "2018-08"
        assert entry["end_date"] == "2021-05"

    def test_experience_keeps_both_dates(self):
        sections = self._sections(
            {
                "name": "Test",
                "experience": [
                    {"company": "C", "role": "P", "dates": "2021-05 - 2023-08"}
                ],
            }
        )
        entry = sections["Work Experience"][0]
        assert entry["start_date"] == "2021-05"
        assert entry["end_date"] == "2023-08"

    def test_experience_without_dates_has_no_fabricated_year(self):
        sections = self._sections(
            {"name": "Test", "experience": [{"company": "C", "role": "P"}]}
        )
        entry = sections["Work Experience"][0]
        assert "start_date" not in entry
        assert "end_date" not in entry

    def test_inverted_range_drops_the_end_date(self):
        sections = self._sections(
            {
                "name": "Test",
                "education": [
                    {"school": "U", "degree": "CS", "dates": "2026-08 - 2020-05"}
                ],
            }
        )
        entry = sections["Education"][0]
        assert entry["start_date"] == "2026-08"
        assert "end_date" not in entry

    def test_project_without_dates_has_no_fabricated_year(self):
        sections = self._sections(
            {"name": "Test", "projects": [{"name": "P", "points": ["x"]}]}
        )
        entry = sections["Projects"][0]
        assert "date" not in entry


# ---------------------------------------------------------------------------
# RenderCV's own validation — the guarantee that matters
# ---------------------------------------------------------------------------


class TestRendercvAcceptsGeneratedDates:
    """The real bug was not a wrong date but a *rejected* CV."""

    @staticmethod
    def _validates(parsed) -> bool:
        from rendercv.schema.rendercv_model_builder import (
            build_rendercv_dictionary_and_model,
        )

        payload = convert_llm_json_to_rendercv_dict(parsed)
        build_rendercv_dictionary_and_model(json.dumps(payload, ensure_ascii=False))
        return True

    def test_inverted_education_range_still_validates(self):
        assert self._validates(
            {
                "name": "Test",
                "email": "jane@gmail.com",
                "education": [
                    {"school": "U", "degree": "CS", "dates": "2026-08 - 2020-05"}
                ],
            }
        )

    def test_inverted_experience_range_still_validates(self):
        assert self._validates(
            {
                "name": "Test",
                "email": "jane@gmail.com",
                "experience": [
                    {
                        "company": "C",
                        "role": "P",
                        "dates": "2026-08 - 2020-05",
                        "points": ["x"],
                    }
                ],
            }
        )

    def test_entries_without_dates_still_validate(self):
        assert self._validates(
            {
                "name": "Test",
                "email": "jane@gmail.com",
                "education": [{"school": "U", "degree": "CS"}],
                "experience": [{"company": "C", "role": "P", "points": ["x"]}],
                "projects": [{"name": "P", "points": ["x"]}],
            }
        )

    def test_realistic_mixed_cv_validates(self):
        assert self._validates(
            {
                "name": "Test",
                "email": "jane@gmail.com",
                "education": [
                    {"school": "U", "degree": "CS", "dates": "2018-08 - 2021-05"},
                    {"school": "V", "degree": "MSc", "dates": "2024 - 2026"},
                ],
                "experience": [
                    {
                        "company": "C",
                        "role": "P",
                        "dates": "2021-05 - 2023-08",
                        "points": ["x"],
                    }
                ],
            }
        )
