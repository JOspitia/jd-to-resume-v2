"""
backend.application.paths
========================

Filesystem paths that the FastAPI app serves from. Lives in
``application/`` (not ``main.py``) so the routers can import these
constants at module top — completing the MP-02 split that removes the
``from main import ...`` circular pattern.

The values are derived from ``backend/__init__.py``'s location; if the
deployment layout changes (e.g. the backend moves under a different
package), only this file needs updating.

Backward-compat re-exports in ``main.py`` preserve the
``main._OUTPUT_DIR`` and ``main._PHOTOS_DIR`` names that pre-date this
split, so existing tests and any external script keep working.
"""

from __future__ import annotations

import os


# Backend package root: ``backend/__init__.py`` directory.
_BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Where RenderCV / Playwright write generated PDFs.
OUTPUT_DIR: str = os.path.join(_BACKEND_DIR, "output")

# Where Photos are persisted by ``photo_helpers.save_photo`` and
# ``photo_helpers.persist_uploaded_photo``.
PHOTOS_DIR: str = os.path.join(OUTPUT_DIR, "photos")


__all__ = ["OUTPUT_DIR", "PHOTOS_DIR"]
