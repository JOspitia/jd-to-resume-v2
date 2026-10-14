"""
Regression tests for the content-drift guard that enforces the product
promise: when the user hand-edits the YAML and presses "Generar CV", the
render must be of exactly what they wrote. The LLM may fix YAML syntax, but
it may not touch the words — including the metrics.

`_content_drift` is the enforcement. These tests exist because the first
version tokenized with a `{3,}` character threshold, which silently dropped
"30%", "40" and "15" and therefore let a model swap one metric for another. A
CV that reports 45% when the candidate achieved 30% is worse than no CV.

Written without pytest so it runs on a bare interpreter:

    backend/venv/Scripts/python.exe backend/tests/test_content_drift.py

and is still collectable by pytest when it is available.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import _content_drift, _content_tokens  # noqa: E402


ORIGINAL = """name: Julieth Andrea Caicedo Goy
experience:
- company: Consultora XYZ
  role: Analista de Contratación
  points:
  - Reduje el tiempo de contratación en 30%
  - Diseñé 40 entrevistas por competencias
  - Coordiné la gestión de 120 candidatos
skills:
- category: Evaluación
  items:
  - 16PF
"""


def _cases():
    """(name, callable) pairs — shared by the pytest and standalone runners."""
    return [
        # ---- tokenization -------------------------------------------------
        ("number: 15", lambda: "15" in _content_tokens("reducimos 15%")),
        ("number: 30", lambda: "30" in _content_tokens("reducimos 30%")),
        ("number: 40", lambda: "40" in _content_tokens("40 entrevistas")),
        ("number: 99", lambda: "99" in _content_tokens("99 casos")),
        ("number: 1.5", lambda: "1.5" in _content_tokens("1.5 puntos")),
        ("number: 2,000", lambda: "2,000" in _content_tokens("2,000 casos")),
        ("short words suppressed", lambda: "de" not in _content_tokens("de la gestion")),
        ("long word kept", lambda: "gestión" in _content_tokens("de la gestión")),
        ("accented word", lambda: "psicóloga" in _content_tokens("psicóloga,(organización)")),
        ("accented word 2", lambda: "organización" in _content_tokens("psicóloga,(organización)")),

        # ---- formatting-only changes: ACCEPT ------------------------------
        ("format: reindent", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("  points:", "    points:")) is None),
        ("format: list marker", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("- company:", "-  company:")) is None),
        ("format: blank lines", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("\nskills:", "\n\n\nskills:")) is None),
        ("format: quoting", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("  - 16PF", '  - "16PF"')) is None),
        ("format: identical", lambda: _content_drift(ORIGINAL, ORIGINAL) is None),
        (
            "format: word split and rejoined",
            lambda: _content_drift(ORIGINAL.replace("contratación", "contrataci\n  ón"), ORIGINAL) is None,
        ),
        ("edge: empty original", lambda: _content_drift("", "name: X") is None),

        # ---- content changes: REJECT --------------------------------------
        ("drift: 30% -> 45%", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("30%", "45%")) is not None),
        ("drift: 40 -> 60", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("40 entrevistas", "60 entrevistas")) is not None),
        ("drift: 120 -> 80", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("120 candidatos", "80 candidatos")) is not None),
        ("drift: verb inverted", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("Reduje", "Aumenté")) is not None),
        ("drift: skill dropped", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("  - 16PF\n", "")) is not None),
        ("drift: skill invented", lambda: _content_drift(ORIGINAL, ORIGINAL + "  - Workday\n") is not None),
        ("drift: role reworded", lambda: _content_drift(ORIGINAL, ORIGINAL.replace("Analista de Contratación", "Psicología organizacional")) is not None),
        (
            "drift: translated",
            lambda: _content_drift(
                ORIGINAL,
                ORIGINAL.replace("Reduje el tiempo de contratación en 30%", "Reduced the hiring time by 30%"),
            ) is not None,
        ),
    ]


def _assert_messages_name_the_token():
    """The rejection message must name the offending token, or it is useless."""
    reason = _content_drift(ORIGINAL, ORIGINAL.replace("30%", "45%"))
    assert reason is not None, "metric change was not detected"
    assert "30" in reason, f"message does not name the changed number: {reason}"
    assert "dato" in reason, f"metric change should be phrased as data: {reason}"


def test_content_drift_guard():
    failures = []
    for name, fn in _cases():
        try:
            ok = bool(fn())
        except Exception as exc:  # noqa: BLE001
            failures.append(f"{name}: raised {type(exc).__name__}: {exc}")
            continue
        if not ok:
            failures.append(name)
    _assert_messages_name_the_token()
    assert not failures, "FAILED: " + "; ".join(failures)


if __name__ == "__main__":
    test_content_drift_guard()
    print(f"test_content_drift_guard: PASS ({len(_cases())} cases)")
