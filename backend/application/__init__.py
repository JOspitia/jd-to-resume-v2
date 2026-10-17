"""
backend.application
===================

Use cases + services that orchestrate ports (``backend.ports.*``) to
deliver business outcomes. This layer is the application core of the
hexagonal architecture:

    * Depends on ``domain/`` (for value objects) and ``ports/`` (for
      interfaces). Never on ``adapters/`` directly — adapters are
      injected by the composition root in ``backend/main.py``.
    * Knows nothing about HTTP, FastAPI, or any transport. The routes
      layer adapts HTTP requests to use case method calls.

Layout::

    application/
    ├── use_cases/    orchestrate a full user-facing workflow
    └── services/     smaller helpers that use cases compose (orchestrator,
                      translation, LinkedIn service, ...)
"""