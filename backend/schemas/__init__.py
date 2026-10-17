"""
backend.schemas
===============

Pydantic models that live at the HTTP boundary. Distinguished from
``backend.domain.entities`` (which are pure business value objects):

* ``schemas/``            — request/response DTOs, validated by FastAPI.
* ``domain/entities.py``  — business objects that flow through use cases.

Schemas are the only types in the project that depend on FastAPI or
pydantic's HTTP integration features.
"""