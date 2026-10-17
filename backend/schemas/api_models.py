"""
backend.schemas.api_models
==========================

Pydantic models for HTTP request/response payloads and the structured
output the LLM is expected to return.

Moved from ``backend/main.py`` (the inline ``GeminiResumeOutput`` model)
in commit 6 of the hexagonal refactor.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class GeminiResumeOutput(BaseModel):
    """Structured JSON the LLM must return from a tailoring call."""

    name: str = Field(description="Full Name")
    phone: str = Field(description="Phone Number")
    email: str = Field(description="Email Address")
    portfolio: str = Field(description="Portfolio Website URL")
    linkedin: str = Field(description="LinkedIn URL")
    github: str = Field(description="GitHub URL")
    summary: str = Field(description="Concise professional summary")
    education: list[dict] = Field(description="List with school, degree, dates, gpa")
    skills: list[dict] = Field(description="List with category and items (strings)")
    experience: list[dict] = Field(
        description="List of dicts with: company, role, dates, points (list)"
    )
    projects: list[dict] = Field(
        description=(
            "List of dicts with: name, dates, points (list), url (optional "
            "live URL), github_url (optional GitHub repo URL)"
        )
    )
    achievements: list[str] = Field(
        description="List of specific achievements or awards"
    )


__all__ = ["GeminiResumeOutput"]