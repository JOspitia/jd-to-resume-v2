"""
backend.domain.entities
=======================

Value objects that flow through the use cases.

Why TypedDict and not dataclass for ``Resume``?
    The LLM returns a JSON dict that the rest of the codebase (rendercv,
    html_template) consumes as a ``dict``. Wrapping that in a dataclass
    would force a conversion at every boundary without buying type safety
    the callers actually use. TypedDict gives editor/type-checker support
    while keeping the runtime representation zero-cost.

Why dataclass for the other entities?
    ``JobDescription``, ``AuditResult``, and ``TailoredResume`` are outputs
    of use cases that downstream code reads field-by-field. The dataclass
    makes that contract explicit and catches typos at static-analysis time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional, TypedDict


# ---------------------------------------------------------------------------
# Resume — the canonical dict shape produced by the LLM and consumed by
# RenderCV / the HTML fallback renderer.
# ---------------------------------------------------------------------------


class ContactInfo(TypedDict, total=False):
    """Subset of Resume keys that hold contact details. All optional."""

    email: str
    phone: str
    location: str
    portfolio: str
    linkedin: str
    github: str


class ExperienceEntry(TypedDict, total=False):
    company: str
    position: str
    start_date: str  # "2020-01" or "2020"
    end_date: str    # "2023-08" or "present"
    highlights: list[str]


class EducationEntry(TypedDict, total=False):
    institution: str
    degree: str
    start_date: str
    end_date: str
    details: str


class SkillEntry(TypedDict, total=False):
    """A skill belongs to a category. Either ``label`` or ``category`` is the
    bucket the renderer groups under (RenderCV's design schema accepts either)."""

    label: str
    category: str
    details: list[str]  # individual skills under the category


class ProjectEntry(TypedDict, total=False):
    name: str
    start_date: str
    end_date: str
    highlights: list[str]
    url: str


class SectionLabels(TypedDict, total=False):
    """Localized section headers. Falls back to English defaults if absent."""

    summary: str
    education: str
    skills: str
    experience: str
    projects: str
    achievements: str


class Resume(TypedDict, total=False):
    """The canonical resume dict. Output of the LLM, input to the PDF renderer.

    Every field is optional because the LLM may omit any of them; the render
    path supplies defensive defaults before handing the dict to RenderCV.
    """

    name: str
    location: str
    phone: str
    email: str
    portfolio: str
    linkedin: str
    github: str
    summary: str
    education: list[EducationEntry]
    skills: list[SkillEntry]
    experience: list[ExperienceEntry]
    projects: list[ProjectEntry]
    achievements: list[str]
    section_labels: SectionLabels


# ---------------------------------------------------------------------------
# Use case input/output value objects.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class JobDescription:
    """The user's input that drives tailoring + audit.

    ``text`` is the JD body (or the placeholder fallback when none is given).
    ``target_role`` is the role title the user is applying for; the LLM
    uses it to anchor bullets toward that title's vocabulary.
    ``custom_instructions`` is free-form refinement text from the user
    ("emphasize leadership", "rewrite as senior").
    """

    text: str
    target_role: Optional[str] = None
    custom_instructions: Optional[str] = None


@dataclass(frozen=True)
class AuditResult:
    """Structured ATS audit output. Mirrors the JSON contract the LLM returns
    (and that the frontend's AuditPanel consumes)."""

    ats_score: int
    match_level: str
    matched_keywords: list[str]
    missing_keywords: list[str]
    ai_detection_score: int
    ai_tone_verdict: str
    ai_humanize_tips: list[str]
    ats_formatting_score: int
    actionable_tips: list[str]

    @classmethod
    def from_llm_dict(cls, data: dict[str, Any]) -> "AuditResult":
        """Defensive factory that handles missing keys and bad types."""
        return cls(
            ats_score=int(data.get("ats_score", 0)),
            match_level=str(data.get("match_level", "unknown")),
            matched_keywords=list(data.get("matched_keywords", [])),
            missing_keywords=list(data.get("missing_keywords", [])),
            ai_detection_score=int(data.get("ai_detection_score", 0)),
            ai_tone_verdict=str(data.get("ai_tone_verdict", "")),
            ai_humanize_tips=list(data.get("ai_humanize_tips", [])),
            ats_formatting_score=int(data.get("ats_formatting_score", 0)),
            actionable_tips=list(data.get("actionable_tips", [])),
        )


@dataclass(frozen=True)
class TailoredResume:
    """Output of the GenerateResumeUseCase.

    ``pdf_path`` is the absolute path of the rendered PDF (or None if
    edit_before_generate stopped at the YAML-ready step).
    ``yaml_text`` is the YAML serialization of ``parsed_data`` — always set,
    even when a PDF is also rendered (so the user can re-open the editor).
    """

    pdf_path: Optional[str]
    yaml_text: str
    parsed_data: Resume  # typed as Resume but at runtime it's a plain dict


__all__ = [
    "ContactInfo",
    "ExperienceEntry",
    "EducationEntry",
    "SkillEntry",
    "ProjectEntry",
    "SectionLabels",
    "Resume",
    "JobDescription",
    "AuditResult",
    "TailoredResume",
]