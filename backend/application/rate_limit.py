"""
backend.application.rate_limit
==============================

Per-IP, per-scope request-rate limiter for LLM-expensive endpoints.

Why this lives in ``application/`` and not ``main.py``
------------------------------------------------------
The previous implementation was a closure inside ``main.py`` that the
FastAPI routers consumed via ``from main import enforce_rate_limit``
inside each handler — a circular-import workaround. Moving the function
here lets the routers import it at module top (no cycle, no lazy
import) while ``main.py`` keeps a re-export for backwards compatibility
with existing tests and any external scripts.

Why we don't use slowapi's middleware / decorators
--------------------------------------------------
* ``SlowAPIASGIMiddleware`` tries to inject headers AFTER the handler
  has begun streaming — with the SSE endpoints (``/api/generate``,
  ``/api/analyze-ats``, ``/api/render-from-yaml``) this corrupts the
  stream and the browser shows ``net::ERR_FAILED``.
* ``@limiter.limit(...)`` decorators lose their closure when FastAPI
  re-registers the route after composition root wiring.

So we call ``await enforce_rate_limit(request, scope="...")`` explicitly
from each LLM-expensive endpoint with a unique ``scope`` label. The
counter resets when entries fall outside the configured window.

Configuration
-------------
* ``RATE_LIMIT_ENABLED`` (default ``"1"``) — set to ``"0"`` to disable.
* ``RATE_LIMIT_DEFAULT`` (default ``"5/minute"``) — count and unit,
  parsed as ``"<N>/<minute|second|hour>"``.
"""

from __future__ import annotations

import os
from time import monotonic

from fastapi import HTTPException, Request
from slowapi.util import get_remote_address


# Per-scope+per-IP rolling-window counter. Lives at module-scope so all
# requests across the process share the same window budget.
_RL_HITS: dict[str, list[float]] = {}


def _is_enabled() -> bool:
    """Mirror of slowapi ``Limiter.enabled`` so we don't depend on main.py."""
    return os.getenv("RATELIMIT_ENABLED", "1") != "0"


def _parse_rate(raw: str) -> tuple[int, float]:
    """Parse ``"<N>/<unit>"`` env string. Fall back to ``5/minute``."""
    try:
        count_str, _, window_str = raw.partition("/")
        limit = int(count_str)
        if window_str.startswith("minute"):
            return limit, 60.0
        if window_str.startswith("second"):
            return limit, 1.0
        if window_str.startswith("hour"):
            return limit, 3600.0
        return limit, 60.0
    except ValueError:
        return 5, 60.0


async def enforce_rate_limit(request: Request, scope: str) -> None:
    """Raise ``HTTPException(429)`` if the remote IP has exceeded the limit
    in the configured window for ``scope``.

    See module docstring for why this exists alongside slowapi rather
    than using slowapi's middleware or decorators.
    """
    if not _is_enabled():
        return

    raw = os.getenv("RATE_LIMIT_DEFAULT", "5/minute")
    limit, window = _parse_rate(raw)

    ip = get_remote_address(request)
    key = f"{scope}:{ip}"
    now = monotonic()

    # Drop hits outside the window.
    hits = _RL_HITS.get(key, [])
    hits = [t for t in hits if (now - t) < window]

    if len(hits) >= limit:
        # Persist the at-limit snapshot for concurrent requests that
        # share the same window, but pop the key entirely if the
        # filter emptied the list so we don't accumulate dead
        # ``scope:ip`` entries on a long-running server.
        if hits:
            _RL_HITS[key] = hits
        else:
            _RL_HITS.pop(key, None)
        raise HTTPException(
            status_code=429,
            detail=f"Rate limit exceeded for {scope!r}: {limit} requests per {window:.0f}s",
        )

    hits.append(now)
    # Same symmetry cleanup as the 429 branch.
    if hits:
        _RL_HITS[key] = hits
    else:
        _RL_HITS.pop(key, None)


__all__ = ["enforce_rate_limit", "_RL_HITS"]
