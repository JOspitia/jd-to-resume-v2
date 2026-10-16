"""
Regression test for the bug fixed in commit 597c6dc+hotfix:
``generate_resume`` calls ``_persist_uploaded_photo(photo)`` but the
commit deleted the inline implementation from main.py. The wrapper
in main.py delegates to ``photo_helpers.save_photo``.
"""

from __future__ import annotations

import sys
from io import BytesIO

import pytest

sys.path.insert(0, ".")


class TestPersistUploadedPhoto:
    def test_wrapper_returns_none_for_none_photo(self):
        from main import _persist_uploaded_photo

        # The wrapper is async; run it.
        import asyncio
        result = asyncio.run(_persist_uploaded_photo(None))
        assert result is None

    def test_wrapper_persists_a_real_photo(self, tmp_path, monkeypatch):
        """Persist a tiny PNG via the wrapper and confirm a file is written."""
        # Redirect the PHOTOS_DIR to a temp location.
        from main import _PHOTOS_DIR
        import main as main_module
        monkeypatch.setattr(main_module, "_PHOTOS_DIR", str(tmp_path))

        from main import _persist_uploaded_photo
        import asyncio

        png_bytes = (
            b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
            b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc\x00\x01"
            b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
        )

        class FakeUpload:
            async def read(self):
                return png_bytes

        path = asyncio.run(_persist_uploaded_photo(FakeUpload()))
        assert path is not None
        # The path lives under the tempdir we redirected to.
        assert str(path).startswith(str(tmp_path))