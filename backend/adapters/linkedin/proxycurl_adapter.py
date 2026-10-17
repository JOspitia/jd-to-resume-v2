"""
backend.adapters.linkedin.proxycurl_adapter
===========================================

Adapter that calls an external LinkedIn data API (ProxyCurl, Bright Data,
or any service that accepts ``GET {base}?url=<linkedin-url>`` with a
bearer token in the ``Authorization`` header).
"""

from __future__ import annotations

import json
import os
import urllib.parse
import urllib.request


class ProxyCurlAdapter:
    """Adapter for any ProxyCurl-style LinkedIn data API."""

    strategy_name = "proxycurl"

    def scrape(self, linkedin_url: str) -> str:
        """Return the raw JSON returned by the external API, as a string.

        The service layer is responsible for converting this JSON to
        Markdown via the LLM (path 1 in the original code path).
        """
        endpoint = os.getenv("LINKEDIN_API_URL", "").strip()
        api_key = (
            os.getenv("LINKEDIN_API_KEY")
            or os.getenv("PROXYCURL_API_KEY", "")
        ).strip()
        if not endpoint or not api_key:
            raise RuntimeError(
                "ProxyCurlAdapter requires LINKEDIN_API_URL + LINKEDIN_API_KEY. "
                "Both must be set."
            )

        request_url = f"{endpoint}?url={urllib.parse.quote(linkedin_url, safe='')}"
        request = urllib.request.Request(
            request_url,
            headers={"Authorization": f"Bearer {api_key}"},
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        return json.dumps(data, ensure_ascii=False)


__all__ = ["ProxyCurlAdapter"]