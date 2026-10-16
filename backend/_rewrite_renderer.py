"""One-shot rewrite of main.py: collapse HTML template + helpers."""
import re
src = open("main.py", encoding="utf-8").read()

# The template + 4 helpers occupy lines ~131..417.
start_pat = re.compile(r"HTML_TEMPLATE = \"\"\"", re.DOTALL)
end_pat = re.compile(r"def _render_html_template\(", re.DOTALL)

m_start = start_pat.search(src)
m_end = end_pat.search(src)
assert m_start and m_end, "markers not found"
print(f"removing {m_end.start() - m_start.start()} chars (template + 3 helpers)")

# Find the END of _render_html_template (the next top-level def or @app.)
# It's defined and used; the function ends just before the next top-level
# construct. We'll find the next "def " or "@app." after m_end.start().
after = src[m_end.start():]
m_next = re.search(r"^(?:def |@app\.)", after, re.MULTILINE)
assert m_next, "could not find end of _render_html_template"
end_of_function = m_end.start() + m_next.start()
print(f"_render_html_template ends at char {end_of_function}")

# Replacement: 4 thin wrappers that delegate to the adapter.
NEW = '''# Backward-compatible wrappers for the HTML-template helpers. The
# implementations (template, ATS helpers, photo data URI, render function,
# URL-fragmentation check) live in
# ``adapters/renderer/playwright_html_adapter.py``. These wrappers preserve
# the original function names so existing call sites keep working.

from adapters.renderer.playwright_html_adapter import (
    _ats_link_label,
    _photo_to_data_uri,
    _check_profile_urls_not_fragmented,
    _render_html_template,
)

'''

new_src = src[:m_start.start()] + NEW + src[end_of_function:]
open("main.py", "w", encoding="utf-8").write(new_src)
print(f"wrote {len(new_src)} chars (was {len(src)})")