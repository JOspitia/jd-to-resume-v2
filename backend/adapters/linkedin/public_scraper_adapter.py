"""
backend.adapters.linkedin.public_scraper_adapter
================================================

Anonymous urllib fetch + ``og:description`` / ``og:title`` / JSON-LD
parsing. Returns whatever LinkedIn exposes without authentication —
typically just the headline and a short summary, since the rest of the
profile is gated behind a login wall.
"""

from __future__ import annotations

import json
import re
import urllib.request


_HTML_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)


class PublicScraperAdapter:
    """Adapter that fetches the public LinkedIn page without authentication."""

    strategy_name = "public"

    def scrape(self, linkedin_url: str) -> str:
        """Fetch the public HTML and extract og:title / og:description /
        JSON-LD. Returns whatever is available, or an explanation if
        LinkedIn requires authentication."""
        request = urllib.request.Request(
            linkedin_url, headers={"User-Agent": _HTML_USER_AGENT}
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            raw_html = response.read().decode("utf-8", errors="ignore")

        json_ld_match = re.search(
            r'<script type="application/ld\+json">(.*?)</script>',
            raw_html,
            re.DOTALL,
        )
        json_ld_data = ""
        if json_ld_match:
            try:
                json_ld_data = json.dumps(
                    json.loads(json_ld_match.group(1)),
                    ensure_ascii=False,
                    indent=2,
                )
            except Exception:
                pass

        og_desc_match = re.search(
            r'<meta property="og:description" content="([^"]*)"', raw_html
        )
        og_title_match = re.search(
            r'<meta property="og:title" content="([^"]*)"', raw_html
        )

        parts: list[str] = []
        if og_title_match:
            parts.append(f"Nombre / Titular: {og_title_match.group(1)}")
        if og_desc_match:
            parts.append(f"Descripción pública: {og_desc_match.group(1)}")
        if json_ld_data:
            parts.append(f"\nDatos estructurados JSON-LD:\n{json_ld_data[:3000]}")

        if parts:
            return "\n".join(parts)

        # Nothing exposed publicly — LinkedIn required auth.
        return (
            f"Perfil de LinkedIn: {linkedin_url}\n"
            "⚠️ El perfil requiere autenticación para ver el contenido completo. "
            "Configura LINKEDIN_EMAIL y LINKEDIN_PASSWORD en el archivo .env "
            "para extracción completa."
        )


__all__ = ["PublicScraperAdapter"]