"""
backend.adapters.storage
========================

The only adapter today is ``FilesystemStorage``, which persists generated
PDFs and candidate photos to ``backend/output/`` and
``backend/output/photos/`` on the local disk.

Future adapters (S3, GCS, in-memory for tests) would implement the
``ResumeStorage`` port declared in ``backend/ports/``.
"""