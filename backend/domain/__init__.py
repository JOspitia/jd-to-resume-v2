"""
backend.domain
==============

Pure domain layer — ZERO external dependencies beyond stdlib + pyyaml + dataclasses.

Rules (enforced):
    1. No imports from ``backend.adapters.*``, ``backend.application.*``,
       ``backend.routes.*``, or ``backend.ports.*``.
    2. No imports from third-party I/O libraries (fitz, google.generativeai,
       openai, playwright, jinja2, fastapi).
    3. Domain entities describe the *shape* of business data — they do not
       perform I/O themselves.

This package is the foundation of the hexagonal architecture; every other
layer depends on it, but it depends on nothing else in the project.
"""