"""Regression tests against broken module-level references in route handlers.

Today's debugging session surfaced three bugs of the same shape:

  * commit 6b0936d — ``OUTPUT_DIR`` (without underscore) was left in
    four places inside the ``/api/generate`` and ``/api/render-from-yaml``
    handlers after the path names were renamed to ``_OUTPUT_DIR``. The
    browser saw a 500 ``NameError`` translated by the SSE frontend into
    a generic "Process Failed / network error".

  * commit 6d675f3 — ``HTML_TEMPLATE`` constant was referenced by a
    legacy wrapper of ``_render_html_template`` that re-shadowed the
    adapter import. The constant had been deleted when the template
    moved to ``templates/classic.html.j2``; the leftover reference
    raised ``NameError`` in the render branch.

  * commit 79bd6c7 — ``slowapi.errors.RateLimitExceeded`` was raised with
    a raw string, but the exception class expects a ``Limit`` object.
    FastAPI caught the resulting ``AttributeError`` as a 500; the SSE
    frontend reported "Process Failed / network error". Same symptom
    as above, different cause.

Pytest never caught any of those because there is no end-to-end test of
the ``/api/generate`` happy path. This module is a structural belt-and-
braces that walks the AST of ``backend/main.py`` and fails if any route
handler references a module-level identifier that does not exist when
``main`` is loaded.

The scan is intentionally cheap (no import, no execution of the routes
themselves) so it can run on every push and stay below a second.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest


MAIN_PATH = Path(__file__).resolve().parent.parent / "main.py"
PY_BUILTINS = {
    "True", "False", "None",
    "int", "str", "float", "bool", "list", "dict", "set", "tuple",
    "bytes", "object", "type", "Exception", "ValueError", "TypeError",
    "KeyError", "FileNotFoundError", "RuntimeError", "OSError",
    "Optional", "Any", "Union", "Literal", "Dict", "List", "Set", "Tuple",
}


def _load_main_module_names() -> set[str]:
    """Return every top-level identifier defined in ``backend/main.py``.

    Includes assignments, annotated assignments, function / async-function /
    class defs, and ``from X import Y`` / ``import X`` aliases. This is the
    universe of names the route handlers can legally reference.
    """
    src = MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)

    names: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    names.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
        elif isinstance(node, ast.ImportFrom):
            for alias in node.names:
                names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.asname or alias.name.split(".")[0])
    return names


def _route_handlers(tree: ast.Module) -> list[tuple[str, ast.AST]]:
    """Yield ``(handler_name, ast_node)`` for every FastAPI route handler."""
    ROUTE_METHODS = {"get", "post", "put", "delete", "patch", "route"}
    out: list[tuple[str, ast.AST]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for decorator in node.decorator_list:
            target = decorator.func if isinstance(decorator, ast.Call) else decorator
            if isinstance(target, ast.Attribute) and target.attr in ROUTE_METHODS:
                out.append((node.name, node))
                break
    return out


def _names_referenced(node: ast.AST) -> set[str]:
    """Walk the AST and collect every bare ``Name`` referenced in load context."""
    out: set[str] = set()
    for sub in ast.walk(node):
        if isinstance(sub, ast.Name) and isinstance(sub.ctx, ast.Load):
            out.add(sub.id)
    return out


def test_no_orphan_module_references_in_route_handlers() -> None:
    """Fail if any route handler references a module-level constant that
    is not actually defined in ``backend/main.py``.

    "Module-level constant" heuristic: an identifier matching the
    ``^[A-Z][A-Z0-9_]*$`` pattern (i.e. SCREAMING_SNAKE_CASE). Those are
    the names that historically got renamed during the hexagonal split
    while call sites leaked (OUTPUT_DIR → _OUTPUT_DIR, HTML_TEMPLATE,
    PHOTOS_DIR → _PHOTOS_DIR, ALLOWED_GAMES-mistakes-of-past, etc.).

    References to lowercase names are intentionally NOT checked here
    because the helper functions have well-defined import paths and
    renaming one of them through all call sites is mechanical — if a
    call site ever leaks a lowercase helper, the route will raise
    ``ImportError`` at module import time, which is already covered by
    the existing module-load tests.
    """
    src = MAIN_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    defined = _load_main_module_names()
    screaming_re = re.compile(r"^[A-Z][A-Z0-9_]*$")

    failures: list[tuple[str, int, str]] = []
    for name, node in _route_handlers(tree):
        referenced = _names_referenced(node)
        # Skip constants that the handler itself defines locally
        local_defs: set[str] = set()
        for sub in ast.walk(node):
            if isinstance(sub, ast.Assign):
                for t in sub.targets:
                    if isinstance(t, ast.Name):
                        local_defs.add(t.id)
            elif isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                local_defs.add(sub.target.id)
        for ident in sorted(referenced - local_defs - defined - PY_BUILTINS):
            if screaming_re.match(ident):
                failures.append((name, node.lineno, ident))

    assert not failures, (
        "Found route handlers referencing module-level constants that "
        "are not defined in backend/main.py. This is the class of bug "
        "fixed in commits 6b0936d, 6d675f3, and 79bd6c7 — refuse the merge.\n\n"
        "Offending references:\n"
        + "\n".join(f"  {handler} (line {lineno}): {ident!r}" for handler, lineno, ident in failures)
    )


def test_main_module_imports_without_nameerror_on_helpers() -> None:
    """Smoke check: ensure the module load itself doesn't surface a ``NameError``.

    Equivalent to ``import main`` in a subprocess — catches the "the
    leftover reference is at module-init time" sub-class of the same
    family. The AST scan above catches orphan references inside handler
    bodies, but does not catch constant references that fire during
    import (e.g. ``HTML_TEMPLATE = pathlib.Path(...).read_text()`` at
    the top of the module).
    """
    code = (
        "import sys, importlib\n"
        f"sys.path.insert(0, {str(MAIN_PATH.parent)!r})\n"
        "for m in list(sys.modules):\n"
        "    if m == 'main' or m.startswith('main.'):\n"
        "        del sys.modules[m]\n"
        "try:\n"
        "    importlib.import_module('main')\n"
        "    print('OK')\n"
        "except NameError as e:\n"
        f"    print('FAIL', {str(MAIN_PATH)!r}, e)\n"
        "    sys.exit(2)\n"
    )
    proc = __import__("subprocess").run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        timeout=30,
        cwd=str(MAIN_PATH.parent.parent),
    )
    assert proc.returncode == 0, (
        f"`import main` raised NameError in a clean subprocess. "
        f"stderr: {proc.stderr.strip()!r}  stdout: {proc.stdout.strip()!r}"
    )
