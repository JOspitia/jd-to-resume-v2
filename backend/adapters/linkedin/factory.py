"""
backend.adapters.linkedin.factory
=================================

Builds the ordered list of LinkedIn strategies based on env vars.

Selection logic:
    * If ``LINKEDIN_API_URL`` + ``LINKEDIN_API_KEY`` are set → ProxyCurlAdapter.
    * Else if ``LINKEDIN_EMAIL`` + ``LINKEDIN_PASSWORD`` are set → PlaywrightAuthAdapter.
    * Always include ``PublicScraperAdapter`` last (it works without any config
      but returns limited data).
"""

from __future__ import annotations

import os

from adapters.linkedin.playwright_auth_adapter import PlaywrightAuthAdapter
from adapters.linkedin.proxycurl_adapter import ProxyCurlAdapter
from adapters.linkedin.public_scraper_adapter import PublicScraperAdapter
from ports.linkedin_scraper import LinkedInScraper


def build_linkedin_strategies() -> list[LinkedInScraper]:
    """Return the ordered list of strategies that the LinkedIn service will try."""
    strategies: list[LinkedInScraper] = []

    api_url = os.getenv("LINKEDIN_API_URL", "").strip()
    api_key = os.getenv("LINKEDIN_API_KEY") or os.getenv("PROXYCURL_API_KEY", "")
    if api_url and api_key:
        strategies.append(ProxyCurlAdapter())

    li_email = os.getenv("LINKEDIN_EMAIL", "").strip()
    li_password = os.getenv("LINKEDIN_PASSWORD", "").strip()
    if li_email and li_password:
        strategies.append(PlaywrightAuthAdapter())

    strategies.append(PublicScraperAdapter())
    return strategies


__all__ = ["build_linkedin_strategies"]