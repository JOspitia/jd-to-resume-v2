"""
backend.ports
========

Hexagonal ports — Protocol interfaces for every external dependency.

Rules:
    1. No imports from ``backend.adapters.*``, ``backend.application.*``,
       ``backend.routes.*``, or ``backend.domain.*`` (except for the
       type-only imports the Protocols reference).
    2. Protocols use structural subtyping — any class that implements the
       right methods is implicitly compatible. No inheritance required.

Use cases depend on these Protocols, never on concrete adapters.
The composition root (``backend/main.py``) wires concrete adapters to
the use cases at startup.
"""