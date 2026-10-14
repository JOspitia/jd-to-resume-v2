"""
backend.yaml_helpers
====================

Pure helpers for the YAML editor feature (feat/yaml-editor).

Lives in its own module (no fastapi / fitz / google.generativeai deps) so
it is unit-testable without importing main.py. main.py imports from here
for the /api/render-from-yaml and /api/analyze-yaml endpoints (T4-T5 of
the yaml-editor feature).

Public API:
    serialize_resume_data_as_text(parsed_data: dict) -> str
    yaml_safe_dump_unicode(parsed_data: dict) -> str
"""

from __future__ import annotations

import yaml


def serialize_resume_data_as_text(parsed_data: dict) -> str:
    """
    Render a parsed LLM JSON resume dict into a plain-text narrative that
    mirrors what `extract_text` would return from a rendered PDF.

    Used by `POST /api/analyze-yaml` (S8 of yaml-editor feature) so the
    audit LLM sees the user-edited YAML in the same shape it would see
    a rendered PDF. Output is plain ASCII-ish text — section labels,
    contact lines, experience entries with bullet points, skills
    grouped by category, education, projects, achievements.

    Designed to be robust to missing fields (everything wrapped in
    `.get(...)` with safe defaults) so a partially-edited YAML still
    produces a coherent narrative instead of crashing the audit.
    """
    lines: list[str] = []

    name = parsed_data.get("name") or ""
    if name:
        lines.append(f"Name: {name}")

    for label, key in (
        ("Location", "location"),
        ("Phone", "phone"),
        ("Email", "email"),
        ("Portfolio", "portfolio"),
        ("LinkedIn", "linkedin"),
        ("GitHub", "github"),
    ):
        value = parsed_data.get(key)
        if value:
            lines.append(f"{label}: {value}")

    summary = parsed_data.get("summary")
    if summary:
        lines.append("")
        lines.append("Summary:")
        lines.append(str(summary).strip())

    experiences = parsed_data.get("experience") or []
    if experiences:
        lines.append("")
        lines.append("Experience:")
        for exp in experiences:
            if not isinstance(exp, dict):
                continue
            role = exp.get("role") or ""
            company = exp.get("company") or ""
            dates = exp.get("dates") or ""
            head_bits = [b for b in (role, company) if b]
            if head_bits:
                head = "  - " + " | ".join(head_bits)
                if dates:
                    head += f" ({dates})"
                lines.append(head)
            for point in exp.get("points") or []:
                if not point:
                    continue
                lines.append(f"    * {str(point).strip()}")

    skills = parsed_data.get("skills") or []
    if skills:
        lines.append("")
        lines.append("Skills:")
        for sk in skills:
            if not isinstance(sk, dict):
                continue
            category = sk.get("category") or "Skills"
            items = sk.get("items") or []
            if items:
                lines.append(
                    f"  - {category}: {', '.join(str(i) for i in items)}"
                )

    educations = parsed_data.get("education") or []
    if educations:
        lines.append("")
        lines.append("Education:")
        for edu in educations:
            if not isinstance(edu, dict):
                continue
            school = edu.get("school") or ""
            degree = edu.get("degree") or ""
            dates = edu.get("dates") or ""
            bits = [b for b in (degree, school) if b]
            line = "  - " + " — ".join(bits) if bits else "  - (entry)"
            if dates:
                line += f" ({dates})"
            lines.append(line)

    projects = parsed_data.get("projects") or []
    if projects:
        lines.append("")
        lines.append("Projects:")
        for proj in projects:
            if not isinstance(proj, dict):
                continue
            name_p = proj.get("name") or ""
            dates = proj.get("dates") or ""
            if name_p:
                head = f"  - {name_p}"
                if dates:
                    head += f" ({dates})"
                lines.append(head)
            for point in proj.get("points") or []:
                if not point:
                    continue
                lines.append(f"    * {str(point).strip()}")

    achievements = parsed_data.get("achievements") or []
    if achievements:
        lines.append("")
        lines.append("Achievements:")
        for ach in achievements:
            if ach:
                lines.append(f"  - {str(ach).strip()}")

    return "\n".join(lines).rstrip() + "\n"


def yaml_safe_dump_unicode(parsed_data: dict) -> str:
    """
    Serialize a parsed LLM JSON resume dict to YAML preserving unicode and
    insertion order. Used by /api/generate?edit_before_generate=true to
    stream the parsed_data to the frontend (S2 of yaml-editor feature).
    """
    return yaml.safe_dump(
        parsed_data,
        allow_unicode=True,
        sort_keys=False,
        default_flow_style=False,
        width=120,
    )


__all__ = ["serialize_resume_data_as_text", "yaml_safe_dump_unicode"]
