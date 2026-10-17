"""
backend.photo_helpers
=====================
Storage and validation for the optional candidate photo.

RenderCV's `cv.photo` field expects a *filesystem path* (`ExistingPathRelativeToInput`
or an absolute path); it rejects data URIs. So the uploaded image has to be
persisted to disk before it can be handed to the renderer.

Kept in its own module (no fastapi / fitz / rendercv imports) so it stays unit
testable without booting the app, matching `yaml_helpers`.

Public API:
    PHOTO_MAX_BYTES: int
    detect_image_extension(data: bytes) -> str | None
    save_photo(data: bytes, photos_dir: str) -> str
    PHOTO_PLACEHOLDER_SVG: str
"""

from __future__ import annotations

import hashlib
import os
import re
from typing import TYPE_CHECKING, Optional


if TYPE_CHECKING:
    # UploadFile is the FastAPI request type, which we only need for
    # type hints. Avoiding the runtime import keeps this module pure-Python
    # so unit tests in ``tests/`` can exercise it without booting FastAPI.
    from fastapi import UploadFile


# 5 MB. Large enough for a phone photo of a face, small enough that a user
# cannot fill the disk by resending the same image.
PHOTO_MAX_BYTES = 5 * 1024 * 1024

# Magic-byte signatures. Verifying content rather than trusting the uploaded
# filename means a .txt renamed to .png cannot reach the renderer.
_SIGNATURES = (
    (b"\x89PNG\r\n\x1a\n", ".png"),
    (b"\xff\xd8\xff", ".jpg"),
    (b"GIF87a", ".gif"),
    (b"GIF89a", ".gif"),
)

_EXT_BY_FORMAT = {
    "png": ".png",
    "jpeg": ".jpg",
    "gif": ".gif",
    "webp": ".webp",
}


def detect_image_extension(data: bytes) -> str | None:
    """
    Return the extension implied by the file's magic bytes, or None if the
    payload is not a supported image.

    Content sniffing, not extension trust: an attacker (or a confused user)
    can rename anything to photo.png.
    """
    if not data:
        return None

    for signature, ext in _SIGNATURES:
        if data.startswith(signature):
            return ext

    # WebP: "RIFF" ....size.... "WEBP"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"

    return None


def save_photo(data: bytes, photos_dir: str) -> str:
    """
    Validate and persist an uploaded photo. Returns the absolute path.

    The filename is derived from the SHA-256 of the content, so re-uploading the
    same image reuses the same file instead of accumulating copies, and two
    different uploads can never collide.

    Raises ValueError with a user-facing message when the payload is rejected.
    """
    if not data:
        raise ValueError("La foto está vacía.")

    if len(data) > PHOTO_MAX_BYTES:
        mb = PHOTO_MAX_BYTES / (1024 * 1024)
        raise ValueError(f"La foto supera el límite de {mb:.0f} MB.")

    ext = detect_image_extension(data)
    if ext is None:
        raise ValueError(
            "El archivo no es una imagen válida. Usá PNG, JPG, GIF o WebP."
        )

    os.makedirs(photos_dir, exist_ok=True)
    digest = hashlib.sha256(data).hexdigest()[:20]
    path = os.path.join(photos_dir, f"photo_{digest}{ext}")
    with open(path, "wb") as fh:
        fh.write(data)
    return os.path.abspath(path)


async def persist_uploaded_photo(
    photo: Optional["UploadFile"], photos_dir: str
) -> Optional[str]:
    """Read a FastAPI ``UploadFile`` and persist its bytes via ``save_photo``.

    Returns the absolute filesystem path, or ``None`` if no photo was
    uploaded. The destination directory is passed in by the caller
    (typically the composition root's ``photos_dir`` from
    ``application.paths``) so this module stays pure-Python and does
    not depend on composition-root globals.

    Moved here from ``main.py`` during MP-02 — keeping the helper next
    to its ``save_photo`` sibling makes the photo pipeline easier to
    follow and lets routers import it at module top.
    """
    if photo is None:
        return None
    content = await photo.read()
    return save_photo(content, photos_dir)


def prune_orphaned_photos(photos_dir: str, keep: set[str]) -> int:
    """
    Delete photos in `photos_dir` whose basename is not in `keep`.

    Called when the user hits "Nuevo / Limpiar" so an abandoned upload does not
    linger. Content-addressed names mean re-uploading a kept photo is a no-op.
    """
    if not os.path.isdir(photos_dir):
        return 0
    removed = 0
    for name in os.listdir(photos_dir):
        if not re.fullmatch(r"photo_[0-9a-f]{20}\.(png|jpg|gif|webp)", name):
            continue
        if name in keep:
            continue
        try:
            os.remove(os.path.join(photos_dir, name))
            removed += 1
        except OSError:
            pass
    return removed


# Neutral grey silhouette used by the HTML fallback renderer when no photo was
# supplied but a photo slot was requested. Inline so the Playwright renderer
# needs no extra asset file on disk.
PHOTO_PLACEHOLDER_SVG = (
    "data:image/svg+xml;base64,PHN2ZyB4bWxucz0iaHR0cDovL3d3dy53My5vcmcvMjAwMC9zdmciIH"
    "ZpZXdCb3g9IjAgMCAxMDAgMTAwIj48cmVjdCB3aWR0aD0iMTAwIiBoZWlnaHQ9IjEwMCIgZmlsbD0i"
    "I2VlZWVlZSIvPjxjaXJjbGUgY3g9IjUwIiBjeT0iMzAiIHI9IjIiIGZpbGw9IiNiY2JjM2MiIvPjxw"
    "YXRoIGQ9Ik0zMCA4M2g0ODB2MTggMjR2IDM4eiIvPjwvc3ZnPg=="
)


__all__ = [
    "PHOTO_MAX_BYTES",
    "detect_image_extension",
    "save_photo",
    "persist_uploaded_photo",
    "prune_orphaned_photos",
    "PHOTO_PLACEHOLDER_SVG",
]
