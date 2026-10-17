"""
backend.ports.linkedin_scraper
==============================

Port for any service that turns a LinkedIn URL into a Markdown-ish text dump.

Three adapters today (selected by env vars):
    * ProxyCurlAdapter        (when ``LINKEDIN_API_URL`` is set — external API)
    * PlaywrightAdapter       (when ``LINKEDIN_EMAIL`` + ``LINKEDIN_PASSWORD``
                               are set — authenticated scraping, violates LinkedIn ToS)
    * PublicScraperAdapter    (always — urllib + og:description fallback,
                               returns limited data when auth is required)
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class LinkedInScraper(Protocol):
    """Extracts a public/visible representation of a LinkedIn profile."""

    @property
    def strategy_name(self) -> str:
        """Which strategy this adapter implements (used in logs to make it
        obvious which path produced the data)."""
        ...

    def scrape(self, linkedin_url: str) -> str:
        """Return a Markdown/text dump of the profile.

        The shape is "good enough for an LLM to enrich a CV with the
        profile's headline + about + key experiences + skills + education".
        Not a 1:1 mirror of the LinkedIn UI.

        Returns a string with a leading note explaining the strategy and
        any limits (e.g. *"⚠️ Profile requires authentication..."*) so the
        LLM can acknowledge the source quality.
        """
        ...


__all__ = ["LinkedInScraper"]