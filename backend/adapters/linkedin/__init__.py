"""
backend.adapters.linkedin
=========================

Three implementations of the ``LinkedInScraper`` port:

* ``ProxyCurlAdapter`` — calls an external API (ProxyCurl, or any service
  that accepts ``GET {base}?url=<linkedin-url>`` with bearer auth).
* ``PlaywrightAuthAdapter`` — drives a headless Chromium to log into
  LinkedIn with credentials and scrape the rendered profile.
* ``PublicScraperAdapter`` — anonymous urllib fetch + ``og:description``
  parsing. Returns minimal data (LinkedIn blocks most content for
  unauthenticated visitors).

Selection is driven by env vars (``LINKEDIN_API_URL`` + ``LINKEDIN_API_KEY``
→ ProxyCurl; ``LINKEDIN_EMAIL`` + ``LINKEDIN_PASSWORD`` → Playwright;
otherwise Public).

The service that composes them (``application.services.linkedin_service``)
owns the cache and the LLM cleanup pass that turns each adapter's raw
output into structured Markdown.
"""