"""One-shot rewrite: collapse GeminiResumeOutput + _build_language_override + _persist_uploaded_photo + assets section of main.py."""
import re
src = open("main.py", encoding="utf-8").read()

# Targets (start_pat, end_pat) tuples. Each tuple identifies a section
# to delete and the "imports to add at the top of main.py instead" for
# the function it provides.
sections = []

# Section 1: inline GeminiResumeOutput class (lines ~447-460).
# Delete from "class GeminiResumeOutput(BaseModel):" through the next blank line before async def.
# Easier: find "class GeminiResumeOutput" and delete until just before "async def call_llm_api".
s1_start = src.find("class GeminiResumeOutput(BaseModel):")
s1_end = src.find("async def call_llm_api")
assert s1_start > 0 and s1_end > s1_start
sections.append((s1_start, s1_end))

# Section 2: inline _build_language_override function (lines ~658-722).
s2_start = src.find("def _build_language_override(")
# Find the next top-level construct after that (the next def or async def that's indented at 0).
after = src[s2_start:]
m = re.search(r"^(async def|def|@app\.)", after[1:], re.MULTILINE)
assert m
s2_end = s2_start + 1 + m.start()
sections.append((s2_start, s2_end))

# Section 3: inline _persist_uploaded_photo function (lines ~99-121).
# The function comes BEFORE the main route block, between the rate-limit
# middleware and the @app.get("/"). Find from "async def _persist_uploaded_photo("
# to the next top-level @app.get or @app.post.
s3_start = src.find("async def _persist_uploaded_photo(")
after3 = src[s3_start:]
m3 = re.search(r"^@app\.", after3[1:], re.MULTILINE)
assert m3
s3_end = s3_start + 1 + m3.start()
sections.append((s3_start, s3_end))

# Section 4: assets endpoints (download_resume + clear_cache).
# Find "@app.get(\"/api/download/{filename}\")" and delete up to the next top-level construct.
s4_start = src.find('@app.get("/api/download/{filename}")')
after4 = src[s4_start:]
m4 = re.search(r"^(def |@app\.|if __name__)", after4[1:], re.MULTILINE)
assert m4
s4_end = s4_start + 1 + m4.start()
sections.append((s4_start, s4_end))

# Section 5: OUTPUT_DIR, PHOTOS_DIR, _DOWNLOAD_FILENAME_RE constants.
# Find "# Persistent directory for generated PDFs" and delete through "_DOWNLOAD_FILENAME_RE = re.compile(...)".
s5_start = src.find("# Persistent directory for generated PDFs")
s5_end_marker = "_DOWNLOAD_FILENAME_RE = re.compile("
s5_end_anchor = src.find(s5_end_marker, s5_start)
assert s5_start > 0 and s5_end_anchor > s5_start
# Find the end of that line.
s5_end = src.find("\n", s5_end_anchor) + 1
sections.append((s5_start, s5_end))

# Sort in reverse order so earlier removals don't shift later indices.
sections.sort(key=lambda t: -t[0])

# Build the new imports block (placed near the top of main.py, after existing imports).
IMPORTS_BLOCK = """
# Hexagonal split: section delegates to dedicated modules.
from schemas.api_models import GeminiResumeOutput  # noqa: F401 — re-exported for backward compat
from application.services.translation_service import build_language_override as _build_language_override
from adapters.storage.filesystem_storage import FilesystemStorage  # noqa: F401 — exposed for tests
from routes.assets_router import build_assets_router  # noqa: F401 — composition root uses it
"""

# Apply removals.
for s, e in sections:
    print(f"removing chars {s}..{e} ({e-s} chars)")
    src = src[:s] + src[e:]

# Insert imports block after the existing import of `re`.
import_anchor = "import re\n"
idx = src.find(import_anchor)
assert idx > 0, "could not find import re anchor"
src = src[:idx + len(import_anchor)] + IMPORTS_BLOCK + src[idx + len(import_anchor):]

# Replace the @app.get('/api/download') registration with the assets router.
# Currently we deleted the endpoint definition, but the @app decorator
# already disappeared too — so nothing to replace here.
open("main.py", "w", encoding="utf-8").write(src)
print(f"wrote {len(src)} chars")