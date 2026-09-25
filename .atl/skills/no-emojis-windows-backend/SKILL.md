---
name: no-emojis-windows-backend
description: "Trigger: emoji print, UnicodeEncodeError cp1252, Windows console encoding, emoji in log, print emoji Python Windows. Avoid emojis in backend logs and force UTF-8 stdout on Windows."
license: Apache-2.0
metadata:
  author: "JOspitia"
  version: "1.0"
---

## Activation Contract

When writing Python backend code that runs on Windows (uvicorn, FastAPI, scripts, scheduled tasks, etc.) and you are tempted to add emojis to `print()` calls for visual debugging or status messages — STOP. Use this skill.

## Hard Rules

1. **NEVER** use emojis in `print()` statements on Windows. The default console encoding is `cp1252` and emojis raise `UnicodeEncodeError`, which kills SSE streams, async generators, and asyncio tasks.
2. **NEVER** use non-ASCII characters (accented letters, en-dashes, smart quotes, etc.) in `print()` on Windows unless you have already forced UTF-8 stdout.
3. If you need a visual marker, use ASCII prefixes: `[OK]`, `[WARN]`, `[ERROR]`, `[INFO]`, `[DEBUG]`, `>>>`.
4. If you absolutely must emit emojis (e.g. user-facing CLI output), wrap stdout in UTF-8 at module top BEFORE any other code runs.

## Decision Gates

| Situation | Action |
|---|---|
| Add `print(f"[some-emoji] message")` | Use ASCII tag instead: `print(f"[INFO] message")` |
| Existing log line has an emoji and crashes | Replace emoji with ASCII tag; do not just silence the exception |
| Cross-platform CLI output that needs emojis | Wrap stdout at module top (see snippet below) |
| Frontend `console.log` with emoji | Allowed — browser console is UTF-8 |

## Execution Steps

When starting a new Python module that prints to stdout on Windows, add this at the very top (before any other imports that may print):

```python
import sys
import io

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)
```

For existing modules, prepend the same block and replace every emoji in `print()` with an ASCII tag.

To find offending emojis in a file:

```powershell
Select-String -Path backend/main.py -Pattern "[^\x00-\x7F]"
```

## What Goes Wrong

Symptom in production:

```
UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f310' in position 8: character maps to <undefined>
```

The crash happens inside the SSE stream generator. FastAPI returns HTTP 200 but the stream dies immediately, so the frontend sees "Process Failed / network error" with no useful diagnostic in the browser.

Why existing emojis in the codebase "work": they sit inside blocks that have already wrapped stdout in UTF-8, or they happen to be in codepoints that cp1252 covers. Adding a new emoji outside those blocks breaks things.

## Output Contract

- Print statements: ASCII only (`[INFO]`, `[WARN]`, `[ERROR]`, `[OK]`, `[DEBUG]`).
- Module-level UTF-8 wrap on Windows if any non-ASCII output is required.
- No silent `errors="ignore"` — use `errors="replace"` so a bad byte becomes `?` and you notice.

## References

- `backend/main.py` lines 1-12 — the canonical UTF-8 wrapper in this repo.
- Python docs: `io.TextIOWrapper` encoding parameter.