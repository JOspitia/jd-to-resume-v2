"""
backend.routes
=============

Thin FastAPI HTTP layer. Each module exposes a ``build_*_router(...)``
factory that takes the dependencies it needs (use cases or storage
adapters) and returns an ``APIRouter``.

Routes know nothing about LLM prompts, LinkedIn scraping, or PDF
rendering — they just translate HTTP → use case calls and back.
"""