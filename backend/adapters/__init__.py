"""
backend.adapters
================

Concrete implementations of the hexagonal ports (``backend.ports.*``).

Each adapter:
    * Lives in its own subpackage (``adapters/parser``, ``adapters/llm``, ...).
    * Implements one port (sometimes with multiple strategies — see factories).
    * May depend on third-party libraries (fitz, openai, playwright, ...) — that
      is the whole point of the adapter layer.
    * Never imports from ``application/`` or ``routes/``.

Adapters are wired to use cases by the composition root in ``backend/main.py``.
"""