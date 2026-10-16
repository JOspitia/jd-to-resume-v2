import os
import sys
import io

# Force UTF-8 stdout/stderr on Windows so print() with non-ASCII chars
# (emojis, accented chars, etc.) does not raise UnicodeEncodeError against
# the default cp1252 codec. Skipped under pytest so re-importing this module
# in tests does not leak wrapped streams past the test's captured buffers.
if sys.platform == "win32" and os.getenv("DISABLE_STDIO_REWRAP") != "1" and "pytest" not in sys.modules:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import json
import asyncio
import base64
from html import escape
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, Form, File, BackgroundTasks, HTTPException, Request
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF
import google.generativeai as genai
from jinja2 import Template
from playwright.sync_api import sync_playwright
import tempfile
import time
import re
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIASGIMiddleware
from slowapi.util import get_remote_address

from dotenv import load_dotenv
from render_service import render_cv_with_rendercv
from language import detect_language
from photo_helpers import save_photo as _save_photo, prune_orphaned_photos as _prune_photos
from domain_games import get_game
from audit_prompts import build_audit_prompt as _build_audit_prompt_lib
from yaml_helpers import (
    serialize_resume_data_as_text as _serialize_resume_data_as_text,
    yaml_safe_dump_unicode as _yaml_safe_dump_unicode,
)
import yaml as _pyyaml

load_dotenv()

app = FastAPI()

# CORS: defaults to local Vite dev origins; override with a comma-separated
# CORS_ALLOWED_ORIGINS env var when deploying behind a tunnel or production
# frontend. We deliberately do NOT use a wildcard: combined with the previous
# path-traversal bug in /api/download it would expose any file the server
# process can read to any origin on the public internet.
_cors_origins_raw = os.getenv(
    "CORS_ALLOWED_ORIGINS",
    "http://localhost:5173,http://localhost:5174,http://127.0.0.1:5173,"
    "http://localhost:4173,http://127.0.0.1:4173",
)
_cors_origins = [o.strip() for o in _cors_origins_raw.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
    allow_credentials=False,
)

# Rate limiting (slowapi): protect every endpoint from runaway scripts that
# could drain the user's LLM quota. The default ``RATE_LIMIT_DEFAULT`` is
# conservative (5/minute per remote IP) and override-able via env. Use
# ``RATELIMIT_ENABLED=0`` to disable entirely (e.g. local benchmarking).
_rl_default = os.getenv("RATE_LIMIT_DEFAULT", "5/minute")
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=[_rl_default],
    enabled=os.getenv("RATELIMIT_ENABLED", "1") != "0",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIASGIMiddleware)

# Persistent directory for generated PDFs — survives uvicorn hot-reloads
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Candidate photos. Kept separate from generated PDFs so "Limpiar" can clear
# one without touching the other.
PHOTOS_DIR = os.path.join(OUTPUT_DIR, "photos")

# Only files matching this naming convention are ever written by
# ``generation_pipeline`` and ``render_from_yaml``. /api/download uses it as a
# strict allowlist so path-traversal attempts (e.g. "..\\..\\windows\\...")
# get rejected before touching the filesystem.
_DOWNLOAD_FILENAME_RE = re.compile(r"^tailored_resume_\d+\.pdf$")


async def _persist_uploaded_photo(photo: Optional[UploadFile]) -> Optional[str]:
    """
    Validate and store an optional candidate photo. Returns the absolute path,
    or None when no photo was sent.

    Never raises: a bad photo degrades to "no photo" rather than failing the
    whole generation, which would strand the user with no CV at all.
    """
    if photo is None or not photo.filename:
        return None
    try:
        data = await photo.read()
        return _save_photo(data, PHOTOS_DIR)
    except ValueError as exc:
        print(f"[PHOTO] rejected: {exc}")
        return None
    except Exception as exc:  # pragma: no cover - defensive
        print(f"[PHOTO] unexpected error: {exc}")
        return None

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)

@app.get("/")
def read_root():
    return {"status": "AI Resume Backend is running OK!"}

# Define schemas for Gemini response
from pydantic import BaseModel, Field

HTML_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<style>
  @page { size: letter; margin: 0.4in; }
  body { font-family: 'Times New Roman', Garamond, serif; font-size: 10.5pt; line-height: 1.25; margin: 0; color: #000; }
  h1 { font-size: 24pt; font-weight: bold; text-align: center; margin: 0 0 5px 0; text-transform: uppercase; }
  .contact-info { text-align: center; font-size: 10.5pt; margin-bottom: 8px; }
  .contact-info a { color: #000; text-decoration: none; }

  /* Profile URLs live on their own full-width line.
     Keeping them on the same line as location/phone/email means a photo
     squeezes the run and the layout wraps the URL at one of its hyphens:
     "linkedin.com/in/julieth-andrea-caicedo-" / "goyeneche". The link
     annotation survives but the extracted text does not, and ATS parsers
     read the text layer, so a wrapped URL parses as a broken one.

     `nowrap` keeps each URL from breaking mid-token, which is what protects
     the slug. The links are separated with a flex gap so that when they do not
     all fit they wrap BETWEEN links — a new line starting at a clean URL — and
     never inside one. Using inline-block plus nowrap instead made the block
     overflow its centred container, which defeats text-align and stacks the
     links on separate internal lines. */
  .profile-links {
    display: flex; flex-wrap: wrap; justify-content: center; align-items: baseline;
    gap: 0 6pt; font-size: 10.5pt; margin-bottom: 8px;
  }
  .profile-links a {
    color: #000; text-decoration: none; white-space: nowrap;
  }
  /* Explicit "|" between URLs. Drawn with ::after so it cannot affect layout —
     the flex gap already handles spacing — while still landing in the extracted
     text layer as a delimiter a naive parser can split on. */
  .profile-links a:not(:last-child)::after { content: " |"; }

  /* Optional candidate photo. Laid out as a bordered circle in the header row
     so it matches what RenderCV's photo_position:left renders. */
  .header-row { display: flex; align-items: center; justify-content: center; gap: 14pt; }
  .header-row .photo {
    width: 3.2cm; height: 3.2cm; border-radius: 50%; object-fit: cover;
    border: 1pt solid #000; flex: 0 0 auto;
  }
  .header-row .header-text { flex: 1 1 auto; }
  
  h2 { font-size: 12pt; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid black; padding-bottom: 2px; margin-top: 12px; margin-bottom: 6px; color: #000; page-break-after: avoid; break-after: avoid; }
  
  p { margin: 0 0 4px 0; }
  ul { margin: 0 0 8px 0; padding-left: 20px; }
  li { margin-bottom: 2px; orphans: 3; widows: 3; }
  
  .flex-container { display: flex; justify-content: space-between; align-items: baseline; }
  
  .item-title { font-weight: bold; }
  .item-subtitle { font-style: italic; }
  .item-right { text-align: right; }
  
  .skills-list { margin: 0 0 8px 0; }

  /* Anti-orphan block protection */
  .resume-entry {
    page-break-inside: avoid !important;
    break-inside: avoid !important;
    margin-bottom: 6px;
  }
  .manual-page-break {
    page-break-before: always !important;
    break-before: page !important;
  }
</style>
</head>
<body>
  <div class="header-row">
    {% if photo_uri %}
      <img class="photo" src="{{ photo_uri }}" alt="" />
    {% endif %}
    <div class="header-text">
  <h1>{{ name }}</h1>
  <div class="contact-info">
    {% set items = [] %}
    {% if location %}{% set _ = items.append(location) %}{% endif %}
    {% if phone %}{% set _ = items.append(phone) %}{% endif %}
    {% if email %}{% set _ = items.append(email) %}{% endif %}
    {{ items|join(' | ') }}
  </div>
    </div>
  </div>

  {# Profile URLs on a dedicated full-width line — see .profile-links in the
     stylesheet for why a photo must not share the line with them. The flex
     gap supplies the separator, so no pipe markup is needed. #}
  {% set links = [] %}
  {% if linkedin %}{% set _ = links.append('<a href="' ~ (linkedin | e) ~ '">' ~ (linkedin | ats_link('linkedin')) ~ '</a>') %}{% endif %}
  {% if github %}{% set _ = links.append('<a href="' ~ (github | e) ~ '">' ~ (github | ats_link('github')) ~ '</a>') %}{% endif %}
  {% if portfolio %}{% set _ = links.append('<a href="' ~ (portfolio | e) ~ '">' ~ (portfolio | ats_link('portfolio')) ~ '</a>') %}{% endif %}
  {% if links %}
  <div class="profile-links">{{ links|join('')|safe }}</div>
  {% endif %}

  {% if summary %}
  <div class="resume-entry {% if page_break_section == 'summary' %}manual-page-break{% endif %}">
    <h2>{{ labels.summary }}</h2>
    <p>{{ summary }}</p>
  </div>
  {% endif %}
  
  {% if education and education|length > 0 %}
  <div class="{% if page_break_section == 'education' %}manual-page-break{% endif %}">
    <h2>{{ labels.education }}</h2>
    {% for ed in education %}
      <div class="resume-entry">
        <div class="flex-container">
          <div><span class="item-title">{{ ed.school }}</span></div>
          <div class="item-right">{{ ed.dates }}</div>
        </div>
        <div class="flex-container">
          <div><span class="item-subtitle">{{ ed.degree }}</span>{% if ed.gpa %} (GPA: {{ ed.gpa }}){% endif %}</div>
          <div class="item-right"></div>
        </div>
      </div>
    {% endfor %}
  </div>
  {% endif %}
  
  {% if skills and skills|length > 0 %}
  <div class="{% if page_break_section == 'skills' %}manual-page-break{% endif %}">
    <h2>{{ labels.skills }}</h2>
    <div class="skills-list resume-entry">
      {% for skill in skills %}
        <span class="item-title">{{ skill.category }}:</span> {{ skill['items']|join(', ') }}<br>
      {% endfor %}
    </div>
  </div>
  {% endif %}
  
  {% if experience and experience|length > 0 %}
  <div class="{% if page_break_section == 'experience' %}manual-page-break{% endif %}">
    <h2>{{ labels.experience }}</h2>
    {% for exp in experience %}
      <div class="resume-entry">
        <div class="flex-container">
          <div><span class="item-title">{{ exp.role }}</span> | <span class="item-subtitle">{{ exp.company }}</span></div>
          <div class="item-right">{{ exp.dates }}</div>
        </div>
        <ul>
          {% for point in exp.points %}
            <li>{{ point }}</li>
          {% endfor %}
        </ul>
      </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if projects and projects|length > 0 %}
  <div class="{% if page_break_section == 'projects' %}manual-page-break{% endif %}">
    <h2>{{ labels.projects }}</h2>
    {% for proj in projects %}
      <div class="resume-entry">
        <div class="flex-container">
          <div>
            <span class="item-title">{{ proj.name }}</span>
            {% if proj.url %} | <a href="{{ proj.url }}" style="color:#000;text-decoration:none;font-size:9.5pt;">{{ proj.url }}</a>{% endif %}
            {% if proj.github_url and proj.github_url != proj.url %} | <a href="{{ proj.github_url }}" style="color:#000;text-decoration:none;font-size:9.5pt;">{{ proj.github_url }}</a>{% endif %}
          </div>
          <div class="item-right">{{ proj.dates }}</div>
        </div>
        <ul>
          {% for point in proj.points %}
            <li>{{ point }}</li>
          {% endfor %}
        </ul>
      </div>
    {% endfor %}
  </div>
  {% endif %}

  {% if achievements and achievements|length > 0 %}
  <div class="resume-entry {% if page_break_section == 'achievements' %}manual-page-break{% endif %}">
    <h2>{{ labels.achievements }}</h2>
    <ul>
      {% for ach in achievements %}
        <li>{{ ach }}</li>
      {% endfor %}
    </ul>
  </div>
  {% endif %}
</body>
</html>
"""

def _ats_link_label(url: str, network: str) -> str:
    """
    Render a profile URL as machine-readable visible text.

    ATS crawlers read the PDF's extracted text layer, not its link
    annotations. An anchor whose visible text is just "LinkedIn" therefore
    hides the URL from them: the crawler sees the word and has nothing to
    follow. This produces the same label RenderCV already emits —
    `linkedin.com/in/<slug>` — so both renderers agree and the URL survives
    text extraction while remaining a clickable link.

    HTML-escaped: the result is injected into the template as raw markup.
    """
    cleaned = (url or "").strip()
    if not cleaned:
        return ""
    no_scheme = re.sub(r"^https?://", "", cleaned, flags=re.IGNORECASE)
    no_scheme = re.sub(r"^www\.", "", no_scheme, flags=re.IGNORECASE)
    no_scheme = no_scheme.rstrip("/")

    if network == "linkedin" and "linkedin.com/" in no_scheme:
        slug = no_scheme.split("linkedin.com/", 1)[1].strip("/")
        return escape(f"linkedin.com/{slug or 'in'}")
    if network == "github" and "github.com/" in no_scheme:
        slug = no_scheme.split("github.com/", 1)[1].strip("/")
        return escape(f"github.com/{slug}" if slug else "github.com")
    return escape(no_scheme)


def _check_profile_urls_not_fragmented(pdf_path: str, parsed_data: dict) -> None:
    """
    Warn when a profile URL was split across lines in the rendered PDF.

    ATS parsers read the extracted text layer, not the link annotations, so a
    URL the layout engine wrapped at a hyphen looks broken to them even though
    the annotation is intact. The fix is a layout change; this is the
    canary that tells us when the layout regresses, since a silent wrap is
    invisible to every other check.
    """
    try:
        text = extract_text(pdf_path)
    except Exception as err:  # pragma: no cover - defensive
        print(f"[WARN] Could not verify profile URLs in {pdf_path}: {err}")
        return

    flat = re.sub(r"\s+", "", text)
    for key in ("linkedin", "github", "portfolio"):
        url = (parsed_data.get(key) or "").strip()
        if not url:
            continue
        slug = re.sub(r"^https?://", "", url, flags=re.IGNORECASE)
        slug = re.sub(r"^www\.", "", slug, flags=re.IGNORECASE).rstrip("/")
        if slug and slug not in flat:
            print(
                f"[WARN] ATS: the {key} URL was fragmented in the rendered PDF "
                f"and may parse as broken: {slug}"
            )


def _photo_to_data_uri(photo_path: Optional[str]) -> str:
    """
    Inline the candidate photo as a data URI for the Playwright renderer.

    RenderCV takes a filesystem path, but the HTML engine has no file access of
    its own, so the bytes are embedded directly. Returns "" when there is no
    usable photo, which makes the template skip the <img> entirely.
    """
    if not photo_path or not os.path.isfile(photo_path):
        return ""
    import mimetypes
    mime = mimetypes.guess_type(photo_path)[0] or "image/png"
    try:
        with open(photo_path, "rb") as fh:
            payload = base64.b64encode(fh.read()).decode("ascii")
    except OSError:
        return ""
    return f"data:{mime};base64,{payload}"


def _render_html_template(
    parsed_data: dict,
    labels: dict,
    page_break_section: Optional[str],
    photo_path: Optional[str] = None,
) -> str:
    """Render the Playwright HTML template with the ATS helpers registered."""
    template = Template(HTML_TEMPLATE)
    template.globals["ats_link"] = _ats_link_label
    # Also expose it as a filter so the template can write `url | ats_link('linkedin')`.
    template.environment.filters["ats_link"] = lambda url, network: _ats_link_label(url, network)
    return template.render(
        **parsed_data,
        labels=labels,
        page_break_section=page_break_section,
        photo_uri=_photo_to_data_uri(photo_path),
    )


def extract_text(file_path: str) -> str:
    doc = fitz.open(file_path)
    # Concatenate plain text plus all /Link annotations so that PDF hyperlinks
    # that render as bare labels (e.g. "LinkedIn") are also surfaced as their
    # real URLs in the extracted text. The LLM and our header extractor can
    # then see them.
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
        try:
            for link in page.get_links():
                uri = link.get("uri", "").strip()
                if uri:
                    text_parts.append(" " + uri)
        except Exception:
            # Some PDFs have malformed link structures; skip silently.
            pass
    extracted = " ".join(text_parts)
    # Debug: log any linked URLs we found so the user can verify their PDF
    # actually has the /Link annotations we expect.
    urls_found = []
    for page in doc:
        try:
            for link in page.get_links():
                uri = link.get("uri", "").strip()
                if uri:
                    urls_found.append(uri)
        except Exception:
            pass
    if urls_found:
        print(f"[EXTRACT] PDF /Link URIs found ({len(urls_found)}): {urls_found[:10]}")
    return extracted


# --- Header extraction from a Base Resume ----------------------------------------
# Pulls contact fields out of the raw PDF text so they survive regeneration even
# when the user does not retype them in the form. Uses targeted regex patterns
# that bias toward precision over recall — a missed field is better than a wrong
# one, since the LLM can still see the full text in the prompt and the user can
# correct any false negative manually.
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PHONE_RE = re.compile(r"(\+?\d{1,3}[\s.-]?)?\(?\d{2,4}\)?[\s.-]?\d{3,4}[\s.-]?\d{3,4}")
_GITHUB_RE = re.compile(r"(?:https?://)?(?:www\.)?github\.com/[A-Za-z0-9._-]+/?", re.IGNORECASE)
_LINKEDIN_RE = re.compile(r"(?:https?://)?(?:www\.)?linkedin\.com/in/[A-Za-z0-9._-]+/?", re.IGNORECASE)
_PORTFOLIO_RE = re.compile(r"(?:https?://)?(?:www\.)?[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)?\.(?:com|net|org|io|dev|me|co|app|page|site|xyz|store|portfolio)(?:/[A-Za-z0-9._~:/?#@!$&'()*+,;=-]*)?", re.IGNORECASE)
# Common email providers that look like domains but are not portfolio sites.
# When matching _PORTFOLIO_RE, exclude any candidate whose host matches one of these.
_PORTFOLIO_EXCLUDE_DOMAINS = {
    "gmail.com", "yahoo.com", "yahoo.es", "hotmail.com", "outlook.com",
    "live.com", "icloud.com", "me.com", "aol.com", "protonmail.com",
    "mail.com", "zoho.com", "yandex.com", "yandex.ru",
}


def _extract_header_from_pdf_text(resume_text: str) -> dict:
    """
    Best-effort extraction of contact fields from the Base Resume plain text.
    Returns a dict with keys: email, phone, github, linkedin, portfolio,
    has_placeholder_github, has_placeholder_linkedin, has_placeholder_portfolio.
    Each value is a string (possibly empty) — callers decide how to merge with
    form-provided values. The *_placeholder booleans flag words like "GitHub"
    or "LinkedIn" appearing as bare tokens (no URL) so the UI can warn the user
    that the resume had placeholders but no real URLs were found.
    """
    if not resume_text:
        return {
            "email": "", "phone": "", "github": "", "linkedin": "", "portfolio": "",
            "has_placeholder_github": False, "has_placeholder_linkedin": False, "has_placeholder_portfolio": False,
        }

    # Email: prefer the first match that doesn't look like an example/noreply
    email_match = ""
    for m in _EMAIL_RE.finditer(resume_text):
        candidate = m.group(0)
        if "example" in candidate.lower() or "noreply" in candidate.lower():
            continue
        email_match = candidate
        break

    # Phone: prefer + prefix and 10+ digits
    phone_match = ""
    for m in _PHONE_RE.finditer(resume_text):
        candidate = m.group(0)
        digits = re.sub(r"\D", "", candidate)
        if len(digits) >= 10:
            phone_match = candidate.strip()
            break

    github_match = _GITHUB_RE.search(resume_text)
    linkedin_match = _LINKEDIN_RE.search(resume_text)

    # Portfolio: scan URL-like strings, exclude github/linkedin/email domains
    portfolio_match = ""
    seen_domains = set(_PORTFOLIO_EXCLUDE_DOMAINS)
    if github_match:
        seen_domains.add("github.com")
    if linkedin_match:
        seen_domains.add("linkedin.com")
    # Always exclude the email's domain — it will appear in the text as
    # `something@gmail.com` and our regex will match the bare `gmail.com`.
    if email_match and "@" in email_match:
        email_domain = email_match.split("@", 1)[1].strip().lower()
        if email_domain:
            seen_domains.add(email_domain)
    print(f"[EXTRACT] portfolio exclusion set: {sorted(seen_domains)}")
    for m in _PORTFOLIO_RE.finditer(resume_text):
        candidate = m.group(0)
        candidate_lower = candidate.lower()
        # Pull the host portion (between optional scheme and first /)
        host_match = re.match(r"(?:https?://)?(?:www\.)?([^/]+)", candidate_lower)
        host = host_match.group(1) if host_match else candidate_lower
        # Filter out matches that are part of an email address (preceded by '@' or '.' or alphanumeric)
        match_start = m.start()
        if match_start > 0:
            char_before = resume_text[match_start - 1]
            if char_before in "@.0123456789abcdefghijklmnopqrstuvwxyz":
                # Part of a longer string (probably email or path). Skip.
                continue
        if host in seen_domains:
            print(f"[EXTRACT] portfolio skip (excluded domain): '{candidate}' host='{host}'")
            continue
        if any(skip in candidate_lower for skip in ["example.com", "test.com", "yourname", "placeholder"]):
            print(f"[EXTRACT] portfolio skip (skip word): '{candidate}'")
            continue
        # Normalize to https:// if no scheme
        if not candidate_lower.startswith("http"):
            candidate = "https://" + candidate
        print(f"[EXTRACT] portfolio MATCHED: '{candidate}' (host='{host}')")
        portfolio_match = candidate
        break

    # Detect placeholder words: a line containing only "LinkedIn | GitHub | Portafolio"
    # or similar where each platform is just a token, not a URL. We flag them so
    # the UI can warn the user to fill the form.
    has_placeholder_github = False
    has_placeholder_linkedin = False
    has_placeholder_portfolio = False
    if not github_match:
        # Look for the word "github" alone in a header-ish context (first 5 lines).
        # Use word boundary + not part of "github.io" or similar domains.
        first_lines = "\n".join(resume_text.split("\n")[:8])
        has_placeholder_github = bool(re.search(r"\bgithub\b", first_lines, re.IGNORECASE)) and not github_match
    if not linkedin_match:
        first_lines = "\n".join(resume_text.split("\n")[:8])
        has_placeholder_linkedin = bool(re.search(r"\blinkedin\b", first_lines, re.IGNORECASE)) and not linkedin_match
    if not portfolio_match:
        first_lines = "\n".join(resume_text.split("\n")[:8])
        has_placeholder_portfolio = bool(re.search(r"\bportafolio\b|\bportfolio\b", first_lines, re.IGNORECASE)) and not portfolio_match

    return {
        "email": email_match,
        "phone": phone_match,
        "github": github_match.group(0) if github_match else "",
        "linkedin": linkedin_match.group(0) if linkedin_match else "",
        "portfolio": portfolio_match,
        "has_placeholder_github": has_placeholder_github,
        "has_placeholder_linkedin": has_placeholder_linkedin,
        "has_placeholder_portfolio": has_placeholder_portfolio,
    }

class GeminiResumeOutput(BaseModel):
    name: str = Field(description="Full Name")
    phone: str = Field(description="Phone Number")
    email: str = Field(description="Email Address")
    portfolio: str = Field(description="Portfolio Website URL")
    linkedin: str = Field(description="LinkedIn URL")
    github: str = Field(description="GitHub URL")
    summary: str = Field(description="Concise professional summary")
    education: list[dict] = Field(description="List with school, degree, dates, gpa")
    skills: list[dict] = Field(description="List with category and items (strings)")
    experience: list[dict] = Field(description="List of dicts with: company, role, dates, points (list)")
    projects: list[dict] = Field(description="List of dicts with: name, dates, points (list), url (optional live URL), github_url (optional GitHub repo URL)")
    achievements: list[str] = Field(description="List of specific achievements or awards")

async def call_llm_api(prompt_text: str) -> str:
    provider = os.getenv("LLM_PROVIDER", "gemini").lower().strip()
    primary_error_msg = None
    
    # 1. Try Primary Provider (DeepSeek / OpenAI Compatible) if configured
    if provider in ["openai", "openai_compatible", "minimax", "kimi", "moonshot", "deepseek", "openrouter", "groq"]:
        try:
            from openai import OpenAI
            api_key = os.getenv("LLM_API_KEY") or os.getenv("OPENAI_API_KEY")
            base_url = os.getenv("OPENAI_BASE_URL") or os.getenv("LLM_BASE_URL") or "https://api.openai.com/v1"
            model_name = os.getenv("OPENAI_MODEL") or os.getenv("LLM_MODEL") or "gpt-4o-mini"
            
            if not api_key:
                raise ValueError(f"Falta la clave API para {provider}.")
                
            print(f"[LLM INFO] Intentando proveedor primario '{provider}' ({model_name}) en {base_url}...")
            # Set explicit 45s timeout on HTTP client to give DeepSeek enough time under high load
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=45.0)
            
            def _run_openai():
                extra_args = {}
                if "minimax" not in base_url and "moonshot" not in base_url and "kimi" not in base_url:
                    extra_args["response_format"] = {"type": "json_object"}
                    
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": "You are a professional technical recruiter and resume writer. Always respond strictly in valid JSON format."},
                        {"role": "user", "content": prompt_text}
                    ],
                    temperature=0.3,
                    **extra_args
                )
                return response.choices[0].message.content
                
            return await asyncio.wait_for(asyncio.to_thread(_run_openai), timeout=50.0)
        except Exception as primary_err:
            primary_error_msg = str(primary_err)
            print(f"[LLM WARN] El proveedor primario '{provider}' falló/agotó tiempo ({primary_err})")
            print("[LLM INFO] Activando respaldo automático a Gemini...")

    # 2. Fallback Provider: Gemini
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    gemini_error_msg = None
    
    if gemini_key and not gemini_key.startswith("AQ."):
        genai.configure(api_key=gemini_key)
        generation_config = {"response_mime_type": "application/json"}
        
        models_to_try = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
        
        for m_name in models_to_try:
            try:
                print(f"[LLM INFO] Intentando modelo Gemini de respaldo: '{m_name}'...")
                model = genai.GenerativeModel(m_name, generation_config=generation_config)
                res = await asyncio.wait_for(asyncio.to_thread(model.generate_content, prompt_text), timeout=50.0)
                if res and res.text:
                    print(f"[LLM INFO] Gemini '{m_name}' funcionó correctamente.")
                    return res.text
            except Exception as e:
                print(f"[LLM WARN] El modelo Gemini '{m_name}' falló/agotó tiempo: {e}")
                gemini_error_msg = e
                continue
    else:
        gemini_error_msg = "GEMINI_API_KEY no configurada o no válida"
        print("[LLM WARN] Gemini no disponible, continuando al siguiente fallback...")

    # 3. Fallback Provider: DeepSeek directo (no a través de OpenAI compat)
    print("[LLM INFO] Activando fallback a DeepSeek directo...")
    deepseek_key = os.getenv("DEEPSEEK_API_KEY", "").strip()
    
    if not deepseek_key:
        deepseek_key = os.getenv("LLM_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip()
        print(f"[LLM INFO] Usando LLM_API_KEY como fallback de DeepSeek: {'Sí' if deepseek_key else 'No'}")
    
    if not deepseek_key:
        err_detail = f" (Primario: {primary_error_msg}, Gemini: {gemini_error_msg})" if primary_error_msg or gemini_error_msg else ""
        raise ValueError(f"Fallaron todos los modelos.{err_detail} Necesitas configurar al menos una API key válida (LLM_API_KEY, GEMINI_API_KEY, o DEEPSEEK_API_KEY).")
    
    try:
        from openai import OpenAI
        print(f"[LLM INFO] Intentando DeepSeek directo con modelo deepseek-chat...")
        deepseek_client = OpenAI(
            api_key=deepseek_key,
            base_url="https://api.deepseek.com/v1",
            timeout=60.0
        )
        
        def _run_deepseek():
            response = deepseek_client.chat.completions.create(
                model="deepseek-chat",
                messages=[
                    {"role": "system", "content": "You are a professional technical recruiter and resume writer. Always respond strictly in valid JSON format."},
                    {"role": "user", "content": prompt_text}
                ],
                temperature=0.3,
                response_format={"type": "json_object"}
            )
            return response.choices[0].message.content
            
        return await asyncio.wait_for(asyncio.to_thread(_run_deepseek), timeout=55.0)
    except Exception as deepseek_err:
        err_detail = f" (Primario: {primary_error_msg}, Gemini: {gemini_error_msg})" if primary_error_msg or gemini_error_msg else ""
        raise ValueError(f"Fallaron todos los modelos: {deepseek_err}{err_detail}")


# In-memory cache to avoid re-extracting LinkedIn on every refinement pass
# key: linkedin_url, value: extracted text
_linkedin_cache: dict = {}

async def extract_linkedin_profile_data(linkedin_url: str) -> str:
    """
    Extract LinkedIn profile data using:
    1. External API (ProxyCurl or similar) if LINKEDIN_API_URL + LINKEDIN_API_KEY are set.
    2. Authenticated Playwright scraping if LINKEDIN_EMAIL + LINKEDIN_PASSWORD are set.
    3. Public/anonymous fallback scraping (limited data, as LinkedIn blocks most content).
    """
    if not linkedin_url or not linkedin_url.strip():
        return ""

    url = linkedin_url.strip()
    # Normalize: ensure it points to /in/username and not a sub-section
    if "linkedin.com/in/" not in url:
        print(f"[LINKEDIN EXTRACTOR WARN] URL no parece ser un perfil de LinkedIn válido: {url}")
        return f"LinkedIn URL proporcionada: {url}"

    print(f"[LINKEDIN EXTRACTOR] Iniciando extracción para: {url}")

    # --- Cache: return previously extracted data if available ---
    if url in _linkedin_cache:
        print(f"[LINKEDIN EXTRACTOR] ✅ Usando datos en caché para: {url}")
        return _linkedin_cache[url]

    # Re-read .env on each call so credentials added after server start are picked up
    load_dotenv(override=True)

    # --- Path 1: External API (ProxyCurl / Custom) ---
    api_endpoint = os.getenv("LINKEDIN_API_URL", "").strip()
    api_key = (os.getenv("LINKEDIN_API_KEY") or os.getenv("PROXYCURL_API_KEY") or "").strip()

    if api_endpoint and api_key:
        try:
            import urllib.request, urllib.parse
            req_url = f"{api_endpoint}?url={urllib.parse.quote(url, safe='')}"
            req = urllib.request.Request(req_url, headers={"Authorization": f"Bearer {api_key}"})
            with urllib.request.urlopen(req, timeout=15) as response:
                data = json.loads(response.read().decode("utf-8"))
                print("[LINKEDIN EXTRACTOR] ✅ Datos obtenidos desde API externa.")
                return json.dumps(data, ensure_ascii=False)
        except Exception as api_err:
            print(f"[LINKEDIN EXTRACTOR WARN] API externa falló: {api_err}. Continuando con Playwright...")

    # --- Path 2: Authenticated Playwright scraping ---
    li_email = os.getenv("LINKEDIN_EMAIL", "").strip()
    li_password = os.getenv("LINKEDIN_PASSWORD", "").strip()
    print(f"[LINKEDIN EXTRACTOR] Credenciales configuradas: email={'\u2705 S\u00ed' if li_email else '\u274c No (configura LINKEDIN_EMAIL en .env)'}  password={'\u2705 S\u00ed' if li_password else '\u274c No (configura LINKEDIN_PASSWORD en .env)'}")

    def _scrape_authenticated() -> str:
        """Login to LinkedIn and extract full profile via Playwright."""
        with sync_playwright() as p:
            # Launch with stealth-friendly args to bypass bot detection
            browser = p.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-blink-features=AutomationControlled",
                    "--disable-infobars",
                    "--window-size=1280,900",
                ]
            )
            context = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
                viewport={"width": 1280, "height": 900},
                locale="es-ES",
                extra_http_headers={
                    "Accept-Language": "es-ES,es;q=0.9,en;q=0.8",
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                }
            )
            # Mask navigator.webdriver to reduce bot detection
            context.add_init_script("""
                Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
                window.chrome = { runtime: {} };
            """)
            page = context.new_page()

            try:
                # Step 1: Login
                print("[LINKEDIN EXTRACTOR] Iniciando sesión en LinkedIn...")
                page.goto("https://www.linkedin.com/login", wait_until="domcontentloaded", timeout=25000)
                time.sleep(2)

                # Try multiple selector strategies for username/password (LinkedIn sometimes A/B tests UI)
                username_sel = "#username, input[name='session_key'], input[autocomplete='username']"
                password_sel = "#password, input[name='session_password'], input[autocomplete='current-password']"
                submit_sel   = "button[type='submit'], .btn__primary--large"

                page.wait_for_selector(username_sel, timeout=8000)
                page.fill(username_sel, li_email)
                time.sleep(0.8)
                page.fill(password_sel, li_password)
                time.sleep(0.5)
                page.click(submit_sel)

                # Wait for navigation after login
                try:
                    page.wait_for_url(lambda u: "feed" in u or "mynetwork" in u or "/in/" in u or "checkpoint" in u or "challenge" in u, timeout=25000)
                except Exception:
                    page.wait_for_load_state("networkidle", timeout=20000)
                time.sleep(2)

                current_url = page.url
                print(f"[LINKEDIN EXTRACTOR] URL post-login: {current_url}")

                # Verify login succeeded
                if "checkpoint" in current_url or "challenge" in current_url or "security" in current_url:
                    print("[LINKEDIN EXTRACTOR WARN] LinkedIn solicitó verificación adicional (CAPTCHA/2FA). No se puede continuar automáticamente.")
                    browser.close()
                    return ""

                if "login" in current_url or "authwall" in current_url:
                    print(f"[LINKEDIN EXTRACTOR ERROR] Login falló. Aún en página de login. URL: {current_url}")
                    browser.close()
                    return ""

                print("[LINKEDIN EXTRACTOR] ✅ Sesión iniciada correctamente.")

                # Step 2: Navigate to profile
                page.goto(url, wait_until="domcontentloaded", timeout=20000)
                time.sleep(3)

                # Step 3: Scroll down to load all lazy sections
                for _ in range(6):
                    page.keyboard.press("End")
                    time.sleep(1.2)

                # Step 4: Extract structured sections using selectors
                js_extractor = """
                () => {
                    const getText = (el) => el ? el.innerText.trim() : '';
                    const getAll = (sel) => Array.from(document.querySelectorAll(sel)).map(e => e.innerText.trim()).filter(Boolean);

                    // --- Name & Headline ---
                    const name = getText(document.querySelector('h1'));
                    const headline = getText(document.querySelector('.text-body-medium.break-words'));
                    const location = getText(document.querySelector('.text-body-small.inline.t-black--light.break-words'));

                    // --- About / Summary ---
                    const aboutSection = document.querySelector('#about ~ div .visually-hidden, section[data-section="about"] .display-flex.ph5 span');
                    const about = aboutSection ? aboutSection.innerText.trim() : '';

                    // --- Experience ---
                    const expContainer = document.querySelector('#experience');
                    let experiences = [];
                    if (expContainer) {
                        const expParent = expContainer.closest('section') || expContainer.parentElement?.parentElement?.parentElement;
                        if (expParent) {
                            const items = expParent.querySelectorAll('li.artdeco-list__item');
                            items.forEach(item => {
                                const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                                experiences.push(lines.join(' | '));
                            });
                        }
                    }

                    // --- Education ---
                    const eduContainer = document.querySelector('#education');
                    let education = [];
                    if (eduContainer) {
                        const eduParent = eduContainer.closest('section') || eduContainer.parentElement?.parentElement?.parentElement;
                        if (eduParent) {
                            const items = eduParent.querySelectorAll('li.artdeco-list__item');
                            items.forEach(item => {
                                const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                                education.push(lines.join(' | '));
                            });
                        }
                    }

                    // --- Skills ---
                    const skillsContainer = document.querySelector('#skills');
                    let skills = [];
                    if (skillsContainer) {
                        const skillsParent = skillsContainer.closest('section') || skillsContainer.parentElement?.parentElement?.parentElement;
                        if (skillsParent) {
                            const items = skillsParent.querySelectorAll('li .t-bold span, li .mr1 span');
                            items.forEach(item => skills.push(item.innerText.trim()));
                        }
                    }
                    if (skills.length === 0) {
                        // fallback: try top skills from profile card
                        document.querySelectorAll('[data-field="skill_card_skill_topic"]').forEach(el => skills.push(el.innerText.trim()));
                    }

                    // --- Certifications / Licenses ---
                    const certContainer = document.querySelector('#licenses_and_certifications, #certifications');
                    let certifications = [];
                    if (certContainer) {
                        const certParent = certContainer.closest('section') || certContainer.parentElement?.parentElement?.parentElement;
                        if (certParent) {
                            const items = certParent.querySelectorAll('li.artdeco-list__item');
                            items.forEach(item => {
                                const lines = item.innerText.split('\\n').map(l => l.trim()).filter(Boolean);
                                certifications.push(lines.join(' | '));
                            });
                        }
                    }

                    // --- Languages ---
                    const langContainer = document.querySelector('#languages');
                    let languages = [];
                    if (langContainer) {
                        const langParent = langContainer.closest('section') || langContainer.parentElement?.parentElement?.parentElement;
                        if (langParent) {
                            const items = langParent.querySelectorAll('li.artdeco-list__item');
                            items.forEach(item => languages.push(item.innerText.trim()));
                        }
                    }

                    return {
                        name, headline, location, about,
                        experiences, education, skills, certifications, languages
                    };
                }
                """
                data = page.evaluate(js_extractor)

                # Build structured text output
                def fmt_section(title, items):
                    if not items: return ""
                    body = "\\n".join(f"  - {i}" for i in items if i)
                    return f"### {title}\\n{body}\\n" if body.strip() else ""

                parts = [f"# Perfil LinkedIn Extraído"]
                if data.get("name"): parts.append(f"**Nombre:** {data['name']}")
                if data.get("headline"): parts.append(f"**Titular:** {data['headline']}")
                if data.get("location"): parts.append(f"**Ubicación:** {data['location']}")
                if data.get("about"): parts.append(f"\\n### Resumen / Acerca de\\n{data['about']}\\n")

                parts.append(fmt_section("Experiencia Laboral", data.get("experiences", [])))
                parts.append(fmt_section("Educación", data.get("education", [])))
                parts.append(fmt_section("Habilidades", data.get("skills", [])))
                parts.append(fmt_section("Certificaciones y Licencias", data.get("certifications", [])))
                parts.append(fmt_section("Idiomas", data.get("languages", [])))

                result = "\\n".join(p for p in parts if p)
                print(f"[LINKEDIN EXTRACTOR] ✅ Secciones extraídas: exp={len(data.get('experiences',[]))}, skills={len(data.get('skills',[]))}, certs={len(data.get('certifications',[]))}")
                return result

            except Exception as scrape_err:
                print(f"[LINKEDIN EXTRACTOR ERROR] Error durante scraping autenticado: {scrape_err}")
                return ""
            finally:
                browser.close()

    # Try authenticated scraping if credentials available
    if li_email and li_password:
        try:
            raw_data = await asyncio.to_thread(_scrape_authenticated)
            if raw_data and len(raw_data) > 100:
                # Pass through LLM to clean and normalize
                extraction_prompt = f"""
Tienes el siguiente contenido extraído del perfil de LinkedIn de un candidato usando automatización de navegador.
El contenido puede tener texto duplicado, artefactos HTML o texto crudo de la interfaz.

CONTENIDO EXTRAÍDO DE LINKEDIN:
{raw_data[:6000]}

Estructura y limpia esta información para enriquecer y complementar el CV del candidato.
Genera un resumen profesional estructurado en Markdown con las siguientes secciones (omite las vacías):
- Nombre y Titular profesional
- Ubicación
- Resumen / Acerca de
- Experiencia Laboral (con empresa, cargo, fechas y descripción de responsabilidades)
- Educación (institución, título, fechas)
- Habilidades (lista completa de skills mencionadas)
- Certificaciones y Licencias (nombre, institución, fecha)
- Idiomas

IMPORTANTE: Conserva TODA la información de experiencias, cargos y certificaciones que encuentres, sin omitir ninguna.
"""
                structured = await call_llm_api(extraction_prompt)
                print("[LINKEDIN EXTRACTOR] ✅ Datos de LinkedIn procesados y estructurados correctamente.")
                _linkedin_cache[url] = structured  # Cache the result
                return structured
        except Exception as auth_err:
            print(f"[LINKEDIN EXTRACTOR WARN] Scraping autenticado falló: {auth_err}. Continuando con modo público...")

    # --- Path 3: Anonymous public fallback ---
    print("[LINKEDIN EXTRACTOR] ⚠️ Sin credenciales o scraping autenticado fallido. Intentando acceso público (datos limitados)...")
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"}
        )
        with urllib.request.urlopen(req, timeout=10) as res:
            html_bytes = res.read()
            raw_html = html_bytes.decode("utf-8", errors="ignore")

            # Extract JSON-LD structured data if available
            import re
            json_ld_match = re.search(r'<script type="application/ld\+json">(.*?)</script>', raw_html, re.DOTALL)
            json_ld_data = ""
            if json_ld_match:
                try:
                    json_ld_data = json.dumps(json.loads(json_ld_match.group(1)), ensure_ascii=False, indent=2)
                except Exception:
                    pass

            # Extract og:description meta
            og_desc = re.search(r'<meta property="og:description" content="([^"]*)"', raw_html)
            og_title = re.search(r'<meta property="og:title" content="([^"]*)"', raw_html)

            public_text = ""
            if og_title: public_text += f"Nombre / Titular: {og_title.group(1)}\n"
            if og_desc: public_text += f"Descripción pública: {og_desc.group(1)}\n"
            if json_ld_data: public_text += f"\nDatos estructurados JSON-LD:\n{json_ld_data[:3000]}"

            if not public_text:
                return (
                    f"Perfil de LinkedIn: {url}\n"
                    "⚠️ El perfil requiere autenticación para ver el contenido completo. "
                    "Configura LINKEDIN_EMAIL y LINKEDIN_PASSWORD en el archivo .env para extracción completa."
                )

            extraction_prompt = f"""
Tienes datos públicos limitados del perfil de LinkedIn de un candidato.
Extrae toda la información profesional disponible para complementar su CV.

DATOS PÚBLICOS DE LINKEDIN:
{public_text}

Genera un resumen en Markdown con la información disponible. Indica claramente si la información es limitada por ser pública.
"""
            return await call_llm_api(extraction_prompt)

    except Exception as public_err:
        print(f"[LINKEDIN EXTRACTOR ERROR] Acceso público falló: {public_err}")
        return (
            f"Perfil de LinkedIn: {url}\n"
            "⚠️ No fue posible extraer datos. Configura LINKEDIN_EMAIL y LINKEDIN_PASSWORD en el .env para extracción completa."
        )

def _build_language_override(target_language: str, source_language: str) -> str:
    """
    Build the LANGUAGE OVERRIDE block prepended AND appended to the system prompt when
    force_language is set. Priority is absolute over rule 8 (LANGUAGE MATCHING).

    The block is intentionally aggressive: it ignores the JD language even if the JD
    is in Spanish, because the user explicitly requested a forced translation via
    the Translate to English button.
    """
    return f"""
LANGUAGE OVERRIDE (ABSOLUTE PRIORITY — overrides rule 8 LANGUAGE MATCHING):
- The user explicitly requested the output CV in English ({target_language}).
- IGNORE the source JD language and the base resume source language ({source_language}).
- Produce ALL text fields (summary, experience[*].points, projects[*].points, skills[*].category,
  skills[*].items, education[*].degree, achievements[*], section_labels) in ENGLISH.
- Never mix languages in the same document.
- Even if the JD is in Spanish, English wins. Even if rule 8 says otherwise, this wins.

DO NOT TRANSLATE (keep verbatim):
- Brand names: BBVA, Mercadona, Carrefour, Google, Microsoft, Amazon, Mercado Libre, Rappi, Glovo, etc.
- Product names: iPhone, Android, RenderCV, Typst, Playwright, FastAPI, LangGraph, LangChain, etc.
- Tech stack: React, Python, TypeScript, JavaScript, FastAPI, AWS, Docker, Kubernetes, PostgreSQL,
  Postgres, Redis, GraphQL, REST, OpenAI, Gemini, Vite, Tailwind, shadcn/ui, etc.
  NEVER use Spanish variants (e.g. "Reaccionar", "Pitón") — always English canonical names.
- Proper nouns (cities): keep in local script (Medellín, Bogotá, Madrid, Sevilla, A Coruña).
  Do NOT anglicise accents.
- Proper nouns (countries): use EN convention (España → Spain, México → Mexico; Colombia and
  Argentina stay the same in EN).
- Certification credential codes: AZ-900, AWS Cloud Practitioner, PMP, CISSP, etc. Keep verbatim.

MUST TRANSLATE / ADAPT:
- Honorifics: Sr. / Sra. → OMIT (do not render).
- Ongoing dates: "Actualmente", "Presente", "Hoy" → "Present".
- Spanish vocational training degrees:
    * "Ciclo Formativo de Grado Superior" / "CFGS" → "Higher Vocational Training".
    * "Formación Profesional" / "FP" (generic) → "Vocational Degree".
    * "Grado Medio" → "Vocational Degree (Intermediate level)".
    * "Grado Superior" → "Higher Vocational Training".
- National IDs:
    * "DNI" → "National ID (DNI)".
    * "Cédula de ciudadanía" → "National ID (Cédula)".
    * "Cédula de identidad" → "National ID".
    * "NIE" → "Foreign Resident ID (NIE)".
- Driver's license: "Carnet de conducir B" / "Licencia de conducir B" → "Driver's license (Category B)".
- Phone numbers: keep the original digits verbatim. Do NOT invent a +1 US prefix when the digits
  are Spanish/Colombian/etc. — the existing sanitize_phone in render_service.py handles prefix.

ANTI-AI REAFFIRMATION (applies EQUALLY to English output):
- burstiness, vary_bullet_syntax, anti_repetition_project_footprint, natural_language_markers
  (rules 15, 17, 18, 20) continue to apply with equal force.
- DO NOT substitute the Spanish pattern examples with English AI clichés:
  NEVER use: "spearheaded", "delved into", "tackled", "orchestrated synergy",
  "navigated complexities", "synergized", "leveraged stakeholder value", "testament to".
- USE the four EN-native narrative patterns instead, varied across consecutive bullets:
  * Pattern A (Outcome-First): "Reduced response latency by 40% by refactoring the FastAPI endpoints..."
  * Pattern B (Challenge-First): "Faced with 8s p99 latency on the checkout flow, I rebuilt the queue layer with Redis Streams..."
  * Pattern C (Action-First): "Led the migration of the legacy monolith to Kubernetes, decommissioning 12 services over 4 months..."
  * Pattern D (Tool-First): "Through Playwright + FastAPI + SSE, automated E2E coverage for 40 critical user paths..."
- Vary sentence length and cadence: mix 1-line statements with 2-line contextual achievements.

SECTION LABELS:
- section_labels MUST be in English: "Professional Summary", "Education", "Skills",
  "Work Experience", "Projects", "Achievements", "Portfolio".
"""


# Per-game audit prompt configuration lives in `audit_prompts.py` (imported
# above) so the prompt builder is testable without importing main.py (which
# pulls in fastapi, fitz, google.generativeai, etc). The wrapper kept below
# preserves the original underscore-prefixed name used by the call sites.
def _build_audit_prompt(resume_text: str, jd_text: str, audit_game) -> str:
    """
    Thin wrapper around `audit_prompts.build_audit_prompt` so call sites
    in main.py keep the original name. The body of the audit prompt
    (per-game taxonomy + seed matched/missing keywords + actionable_tips
    templates) lives in `backend/audit_prompts.py` and is unit-tested
    there.
    """
    return _build_audit_prompt_lib(resume_text, jd_text, audit_game)


async def _run_audit_against_text(
    resume_text: str,
    jd_text: str,
    audit_game,
) -> dict:
    """
    Single source of truth for the ATS-audit LLM call.

    All three audit paths in this app delegate here:
      * `_run_internal_audit` (auto-fired after a forced translate-to-en flow).
      * `POST /api/analyze-ats` (frontend-driven audit on a freshly uploaded CV).
      * `POST /api/analyze-yaml` (audit on a YAML dict the user has edited
        before rendering — T5 of the yaml-editor feature).

    Composes the per-game prompt, calls the LLM, strips any ```json```
    markdown fence and returns the parsed dict. Raises ValueError if the
    response is not a JSON object (caller is responsible for HTTP mapping).
    """
    prompt = _build_audit_prompt(
        resume_text=resume_text,
        jd_text=jd_text,
        audit_game=audit_game,
    )
    content = await call_llm_api(prompt)

    clean_content = content.strip()
    if "```" in clean_content:
        match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
        if match:
            clean_content = match.group(1)

    try:
        parsed = json.loads(clean_content)
    except Exception:
        parsed = json.loads(content)

    # Some LLM clients wrap the payload in a list; take the first element.
    if isinstance(parsed, list) and len(parsed) > 0:
        parsed = parsed[0]

    if not isinstance(parsed, dict):
        raise ValueError(f"Audit response was not a dict (got {type(parsed).__name__})")
    return parsed



async def generation_pipeline(
    file_path: str,
    jd: Optional[str] = None,
    target_role: Optional[str] = None,
    github_url: Optional[str] = None,
    linkedin_url: Optional[str] = None,
    portfolio_url: Optional[str] = None,
    custom_instructions: Optional[str] = None,
    base_resume_filename: Optional[str] = None,
    theme: Optional[str] = "sb2nov",
    fit_single_page: bool = False,
    page_break_section: Optional[str] = None,
    extract_linkedin_info: bool = False,
    strict_edits_only: bool = False,
    force_language: Optional[str] = None,
    domain_game: Optional[str] = None,
    edit_before_generate: bool = False,
    photo_path: Optional[str] = None,
):
    """
    The end-to-end generation pipeline. Returns an SSE stream of progress events and
    ends with a `Finished` event containing the download URL.

    When `force_language='en'`, prepends AND appends a LANGUAGE OVERRIDE block to the
    system prompt so the output CV is generated in English regardless of the source
    JD language. See _build_language_override for the exact wording.

    When `domain_game` is set, the prompt body is composed from the corresponding
    game in `backend/domain_games/` instead of the legacy tech-only prompt. The
    available games today are: "tech" (default), "hr_recruiting", "psychology".
    Passing None or an unknown value falls back to "tech" (preserves v2.5 behaviour
    exactly because the tech game mirrors the legacy prompt body byte-for-byte).

    When `edit_before_generate=True`, the pipeline stops right after the LLM
    call has been parsed. It serialises `parsed_data` as YAML and emits a
    single SSE event with the form `{"step": "YAML Ready for Review",
    "progress": 100, "yaml": "...", "yaml_ready": true}` before returning
    without rendering a PDF. The frontend is expected to either POST the
    (possibly edited) YAML to `/api/render-from-yaml` (S6) or
    `/api/analyze-yaml` (S8). When False (default, or omitted) the
    existing PDF render path runs unchanged (S7).
    """
    if force_language:
        print(f"[TRANSLATE] force_language='{force_language}' — LANGUAGE OVERRIDE will be applied to system prompt (both preamble and tail).")
    print(f"[INPUT] github_url='{github_url}', linkedin_url='{linkedin_url}', portfolio_url='{portfolio_url}' (received from frontend form)")
    try:
        # Reload .env dynamically so any new API Key is immediately picked up
        load_dotenv(override=True)

        yield f"data: {json.dumps({'step': 'Validating Input', 'progress': 10})}\n\n"
        await asyncio.sleep(0.5)

        # If a previously generated resume filename is provided, use it as the base
        # This enables iterative refinement instead of regenerating from scratch
        effective_file_path = file_path
        if base_resume_filename:
            candidate_path = os.path.join(OUTPUT_DIR, base_resume_filename)
            if os.path.exists(candidate_path):
                effective_file_path = candidate_path
                print(f"[INFO] ✅ Using previously generated resume as base: {candidate_path}")
            else:
                print(f"[WARN] ⚠️ base_resume_filename '{base_resume_filename}' not found in OUTPUT_DIR, falling back to original upload.")
                print(f"[WARN]    Expected path: {candidate_path}")

        # Language-detection guardrail (REQ-3): if the user asked for English but the
        # source CV is already English, short-circuit before any LLM call so the
        # expensive translation round-trip is never executed.
        source_language = "unknown"
        if force_language == "en":
            detection_path = effective_file_path
            try:
                source_language = detect_language(extract_text(detection_path))
            except Exception as detect_err:
                print(f"[WARN] Language detection failed for '{detection_path}': {detect_err}. Falling back to 'unknown'.")
                source_language = "unknown"
            print(f"[INFO] force_language='{force_language}', detected source_language='{source_language}', detection_path='{detection_path}'")
            if source_language == "en":
                raise ValueError("E_CV_ALREADY_ENGLISH::CV already in English")

        yield f"data: {json.dumps({'step': 'Extracting Text from Resume', 'progress': 20})}\n\n"
        resume_text = extract_text(effective_file_path)

        # Extract contact header from the Base Resume so it survives regeneration
        # even when the user does not retype it in the form.
        extracted_header = _extract_header_from_pdf_text(resume_text)
        effective_github = (github_url.strip() if github_url and github_url.strip() else extracted_header["github"])
        effective_linkedin = (linkedin_url.strip() if linkedin_url and linkedin_url.strip() else extracted_header["linkedin"])
        effective_portfolio = (portfolio_url.strip() if portfolio_url and portfolio_url.strip() else extracted_header["portfolio"])
        print(f"[HEADER] github='{effective_github or '(empty)'}', linkedin='{effective_linkedin or '(empty)'}', portfolio='{effective_portfolio or '(empty)'}', email='{extracted_header['email'] or '(empty)'}', phone='{extracted_header['phone'] or '(empty)'}'")
        # Warn if the PDF had placeholder tokens (e.g. "LinkedIn") but no URL was found
        # and the user did not provide one in the form. CV will be missing that link.
        missing_placeholders = []
        if extracted_header["has_placeholder_github"] and not effective_github:
            missing_placeholders.append("github")
        if extracted_header["has_placeholder_linkedin"] and not effective_linkedin:
            missing_placeholders.append("linkedin")
        if extracted_header["has_placeholder_portfolio"] and not effective_portfolio:
            missing_placeholders.append("portfolio")
        if missing_placeholders:
            print(f"[HEADER] WARN: PDF had placeholder tokens but no URLs found for: {', '.join(missing_placeholders)}. User should fill the form with real URLs.")

        linkedin_extracted_text = ""
        if extract_linkedin_info and linkedin_url and linkedin_url.strip():
            yield f"data: {json.dumps({'step': 'Extrayendo datos del perfil de LinkedIn...', 'progress': 35})}\n\n"
            linkedin_extracted_text = await extract_linkedin_profile_data(linkedin_url.strip())
        
        yield f"data: {json.dumps({'step': 'Analyzing with AI Model', 'progress': 50})}\n\n"
        
        if strict_edits_only:
            user_requested_changes = custom_instructions.strip() if (custom_instructions and custom_instructions.strip()) else (jd.strip() if (jd and jd.strip()) else "No explicit changes specified.")
            language_override_block = ""
            if force_language == "en":
                language_override_block = _build_language_override(
                    target_language="en",
                    source_language=source_language,
                )
            prompt = f"""
{language_override_block}
You are an expert resume editor operating strictly in CONSERVATIVE SURGICAL EDIT MODE.
Your task is to take the provided Base Resume and perform ONLY the explicit change(s) requested by the user below.

USER REQUESTED MODIFICATIONS (CRITICAL — APPLY ONLY THESE):
{user_requested_changes}

STRICT SURGICAL EDIT RULES (ABSOLUTE HIGHEST PRIORITY — OVERRIDES ALL OTHER DEFAULTS):
1. DO NOT REWRITE, REPHRASE, OR ALTER THE PROFESSIONAL SUMMARY UNLESS THE USER'S REQUEST EXPLICITLY ASKS TO MODIFY THE SUMMARY. If the summary is not mentioned in the requested modifications, keep the 'summary' field 100% IDENTICAL to the Base Resume text.
2. DO NOT REWRITE OR REPHRASE ANY EXPERIENCE BULLET POINTS, DATES, ROLES, EDUCATION, OR SKILLS THAT WERE NOT EXPLICITLY TARGETED BY THE USER's REQUEST.
3. Keep ALL untouched text, experience entries, dates, education, skills, and section contents 100% EXACTLY IDENTICAL to the provided Base Resume.
4. ZERO HALLUCINATION: Do NOT invent or import any fake data, third-party companies, or fake projects.
5. DATE CONSISTENCY: Format ongoing roles/studies strictly as "YYYY-MM - Actualidad" (Spanish) or "YYYY-MM - Present" (English).
{language_override_block}
"""
        else:
            language_override_block = ""
            if force_language == "en":
                language_override_block = _build_language_override(
                    target_language="en",
                    source_language=source_language,
                )
            game = get_game(domain_game)
            prompt = f"""
{language_override_block}
{game.system_intro}

{game.strict_rules_block}
"""
        if custom_instructions and custom_instructions.strip() and not strict_edits_only:
            prompt += f"12. USER REFINEMENT FEEDBACK & SELECTED TIPS (HIGHEST PRIORITY): You MUST explicitly apply the following user-selected improvements, tone humanization tips, and custom instructions above all other defaults: {custom_instructions.strip()}\n"

        prompt += f"""
{language_override_block}
Target Role: {target_role if target_role else 'Not specified'}
GitHub: {effective_github}
LinkedIn: {effective_linkedin}
Portfolio: {effective_portfolio}

CONTACT HEADER PROTECTED FIELDS (DO NOT MODIFY, REMOVE, OR INVENT):
- email: {extracted_header["email"]}
- phone: {extracted_header["phone"]}
- github: {effective_github}
- linkedin: {effective_linkedin}
- portfolio: {effective_portfolio}
These values were extracted from the Base Resume and MUST be preserved verbatim
in the output JSON. If the Base Resume text does not contain one of them, leave
that field empty (do not invent placeholder URLs like 'github.com/janedoe').

Base Resume:
{resume_text}
"""
        # When force_language='en', strip contradictory language rules from the prompt
        # so the LLM cannot fall back to "use JD language" or "use Spanish verbs".
        # We remove rule 8 (LANGUAGE MATCHING) entirely and the Spanish-verb examples
        # in rule 5/15/17/18/20 — the LANGUAGE OVERRIDE block (preamble + tail) carries
        # the full English-only instruction set.
        if force_language == "en":
            prompt = prompt.replace(
                "8. LANGUAGE MATCHING (CRITICAL): Detect the dominant language of the Job Description. Generate ALL text content (summary, bullet points, skill categories, achievements) in THAT SAME language. If the JD is in English → output everything in English. If the JD is in Spanish → output everything in Spanish. Default to the JD language; never mix languages in the same document. Also output the correct localized 'section_labels' accordingly. [OVERRIDDEN when force_language is set — see LANGUAGE OVERRIDE block at the end of this prompt.]",
                "8. LANGUAGE: ABSOLUTE OVERRIDE APPLIES — see LANGUAGE OVERRIDE block. Do not detect or follow the JD language."
            )
            # Spanish verb examples in rule 5: force English-only examples
            prompt = prompt.replace(
                "Spanish: Diseñé, Implementé, Refactoricé, Despliegué, Migré, Optimicé, Automaticé, Incrementé, Reduje, Agilicé, Maximicé, Consolidé, Lideré, Construí.",
                "English (only): Engineered, Architected, Implemented, Spearheaded, Optimized, Automated, Streamlined, Reduced, Scaled, Deployed, Refactored, Designed, Built, Led, Migrated."
            )
            # Replace Spanish anti-AI examples in rules 15, 17, 18, 20 with English equivalents
            prompt = prompt.replace(
                'e.g., "Desarrollé [X] mediante [Y] logrando [Z]")',
                'e.g., "Engineered [X] through [Y] achieving [Z]")'
            )
            prompt = prompt.replace(
                'e.g., "Incrementé la velocidad de respuesta en 40% al refactorizar los endpoints..."',
                'e.g., "Reduced response latency by 40% through endpoint refactoring..."'
            )
            prompt = prompt.replace(
                'e.g., "Ante cuellos de botella en el procesamiento masivo de datos, diseñé una arquitectura de colas..."',
                'e.g., "Facing throughput bottlenecks in data pipelines, designed a queue-based architecture..."'
            )
            prompt = prompt.replace(
                'e.g., "Lideré el despliegue del sistema distribuido sobre AWS, reduciendo la latencia a menos de 100ms..."',
                'e.g., "Led the deployment of the distributed system on AWS, cutting latency below 100ms..."'
            )
            prompt = prompt.replace(
                'e.g., "Mediante FastAPI y PostgreSQL, automaticé los flujos de facturación eliminando 15 horas semanales de trabajo manual..."',
                'e.g., "Through FastAPI and PostgreSQL, automated billing flows eliminating 15 hours of manual work per week..."'
            )
            prompt = prompt.replace(
                'e.g., "Los equipos de bodega carecían de visibilidad en tiempo real; construí una plataforma con Laravel y React que..."',
                'e.g., "Warehouse teams lacked real-time visibility; built a Laravel + React platform that..."'
            )
            prompt = prompt.replace(
                'e.g., "Reduje en 40% los costos..."',
                'e.g., "Cut costs by 40%..."'
            )
            prompt = prompt.replace(
                'e.g., "Implementé el stack con X, logrando Y en Z%"',
                'e.g., "Built the stack with X, achieving Y in Z%"'
            )
            prompt = prompt.replace(
                'e.g., "Implementé el stack con" or starting 4 consecutive bullets with "Desarrollé"',
                'e.g., "Built the stack with" or starting 4 consecutive bullets with "Engineered"'
            )
            prompt = prompt.replace(
                '"Construí", "Diseñé e implementé", "Lideré el desarrollo de", "Refactoricé", "Desplegué", "Migré"',
                '"Built", "Designed and implemented", "Led the development of", "Refactored", "Deployed", "Migrated"'
            )
            prompt = prompt.replace(
                '"Implementé el stack con...", "Desarrollé una...", or "Construí una..."',
                '"Built the stack with...", "Developed a...", or "Engineered a..."'
            )
            prompt = prompt.replace(
                '* Project 1 (Architectural/Innovation Opening): "Arquitecturé una plataforma de optimización de CVs basada en la orquestación de LLMs y renderizado Typst..."',
                '* Project 1 (Architectural/Innovation Opening): "Architected a CV optimization platform based on LLM orchestration and Typst rendering..."'
            )
            prompt = prompt.replace(
                '* Project 2 (Problem/Business Opening): "Para resolver la falta de visibilidad del inventario en tiempo real, diseñé un sistema de monitoreo..."',
                '* Project 2 (Problem/Business Opening): "To solve the lack of real-time inventory visibility, designed a monitoring system..."'
            )
            prompt = prompt.replace(
                '* Project 3 (Technical Integration Opening): "Mediante la integración de Playwright, FastAPI y SSE, automaticé las pruebas E2E..."',
                '* Project 3 (Technical Integration Opening): "Through Playwright, FastAPI, and SSE integration, automated E2E tests..."'
            )
            prompt = prompt.replace(
                '* Project 4 (Metric/Performance Opening): "Reduje los tiempos de respuesta en 45% al implementar mecanismos de caché con Redis..."',
                '* Project 4 (Metric/Performance Opening): "Reduced response times by 45% through Redis caching mechanisms..."'
            )
            print(f"[TRANSLATE] ✂️ Stripped contradictory language rules from prompt (rule 8 + Spanish verb examples).")
        if linkedin_extracted_text:
            prompt += f"""
Extracted LinkedIn Profile Data (Use to enrich and complement the Base Resume):
{linkedin_extracted_text}
"""

        effective_jd = jd.strip() if (jd and jd.strip()) else "No Job Description provided. Perform a comprehensive ATS resume enhancement focused on impact, Google XYZ achievement formula (Action + Context + Measurable Result), strong action verbs, clean structure, and domain-relevant technical skills."

        prompt += f"""
Job Description / Target Requirements:
{effective_jd}
"""
        
        generation_config = {"response_mime_type": "application/json"}
        prompt += """
Respond ONLY with a JSON object in this exact structure. The 'section_labels' field MUST contain the localized section headings in the SAME language as the Job Description:
{
  "name": "Jane Doe",
  "location": "Medellín, Colombia",
  "phone": "555-1234",
  "email": "jane@example.com",
  "portfolio": "",
  "linkedin": "",
  "github": "",
  "summary": "Concise 2-line summary tailored to JD...",
  "education": [{"school": "Universidad Ejemplo", "degree": "Pregrado en Psicología", "dates": "2018 - 2022", "gpa": ""}],
  "skills": [{"category": "Pruebas Psicotécnicas", "items": ["16PF", "DISC", "Wartegg", "Valanti"]}],
  "experience": [{"company": "Empresa Ejemplo", "role": "Analista de Selección", "dates": "2023-01 - Actualidad", "points": ["Lideré procesos de selección...", "Evalué candidatos mediante..."]}],
  "projects": [{"name": "Project Name", "dates": "2025-01", "url": "", "github_url": "https://github.com/user/repo", "points": ["Built X using Y..."]}],
  "achievements": [],
  "section_labels": {
    "summary": "Professional Summary",
    "education": "Education",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "achievements": "Achievements",
    "portfolio": "Portfolio"
  }
}
IMPORTANT:
1. DATE FORMATTING & LOCALIZATION (CRITICAL FOR ATS PARSING):
   - Active / Ongoing Studies & Jobs: If a job or degree started in the past or current date (e.g. "2026-08" when current date is September 2026) and is ongoing, format it as "2026-08 - Actualidad" (Spanish) or "2026-08 - Present" (English).
   - Future Studies & Jobs ONLY: ONLY use "Inicio: YYYY-MM" if the start date is strictly in a future month that has not arrived yet. Do NOT use "Presente" or "Hoy".
2. If the JD is in Spanish, the section_labels values must be in Spanish (e.g. 'Resumen Profesional', 'Educación', 'Habilidades', 'Experiencia Laboral', 'Proyectos', 'Logros', 'Portafolio'). If the JD is in English, they must be in English ('Professional Summary', 'Education', 'Skills', 'Work Experience', 'Projects', 'Achievements', 'Portfolio').
"""

        
        yield f"data: {json.dumps({'step': 'Generating Tailored Resume Content', 'progress': 75})}\n\n"
        try:
            content = await asyncio.wait_for(call_llm_api(prompt), timeout=60.0)
        except asyncio.TimeoutError:
            raise TimeoutError("La generación del CV excedió el límite de 60 segundos. Intenta con un CV más simple o una descripción de trabajo más corta.")
        
        clean_content = content.strip()
        if "```" in clean_content:
            # Extract content inside markdown block if present
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
            if match:
                clean_content = match.group(1)

        try:
            parsed_data = json.loads(clean_content)
        except Exception:
            parsed_data = json.loads(content)
            
        if isinstance(parsed_data, list) and len(parsed_data) > 0:
            parsed_data = parsed_data[0]
            
        if not isinstance(parsed_data, dict):
            raise ValueError("El formato de respuesta de la IA no fue un diccionario válido.")

        # Ensure all expected keys exist to prevent template render errors
        defaults = {
            "name": "", "location": "", "phone": "", "email": "", "portfolio": "", "linkedin": "", "github": "",
            "summary": "", "education": [], "skills": [], "experience": [], "projects": [], "achievements": [],
            "section_labels": {}
        }
        for k, v in defaults.items():
            if k not in parsed_data or parsed_data[k] is None:
                parsed_data[k] = v


        # If user explicitly left GitHub / LinkedIn / Portfolio empty or they contain dummy placeholders, remove them
        # User input overrides if provided; if not provided, fall back to values extracted from the Base Resume
        # so the contact header survives regeneration even when the user does not retype it.
        gh_val = str(parsed_data.get("github", "")).strip()
        is_dummy_gh = any(dummy in gh_val.lower() for dummy in ["github.com/janedoe", "github.com/...", "example", "none"]) if gh_val else True
        if effective_github:
            parsed_data["github"] = effective_github
        elif is_dummy_gh or not gh_val:
            parsed_data["github"] = ""

        li_val = str(parsed_data.get("linkedin", "")).strip()
        is_dummy_li = any(dummy in li_val.lower() for dummy in ["linkedin.com/in/janedoe", "linkedin.com/in/...", "example", "none"]) if li_val else True
        if effective_linkedin:
            parsed_data["linkedin"] = effective_linkedin
        elif is_dummy_li or not li_val:
            parsed_data["linkedin"] = ""

        port_val = str(parsed_data.get("portfolio", "")).strip()
        is_dummy_port = any(dummy in port_val.lower() for dummy in ["janedoe.com", "example.com", "none"]) if port_val else True
        if effective_portfolio:
            parsed_data["portfolio"] = effective_portfolio
        elif is_dummy_port or not port_val:
            parsed_data["portfolio"] = ""

        # Same fallback for email and phone if the LLM dropped them
        em_val = str(parsed_data.get("email", "")).strip()
        if not em_val or any(d in em_val.lower() for d in ["example.com", "your.email", "placeholder"]):
            if extracted_header.get("email"):
                parsed_data["email"] = extracted_header["email"]

        ph_val = str(parsed_data.get("phone", "")).strip()
        if not ph_val or all(c in "0-" for c in ph_val):
            if extracted_header.get("phone"):
                parsed_data["phone"] = extracted_header["phone"]


        # Extract localized section headings from LLM output. The fallback
        # chain is: LLM output (if any) → game's localized labels (ES, then EN)
        # → hardcoded English defaults. Using the game's labels as the fallback
        # ensures the printed headers reflect the domain (e.g. psy 'Formación
        # Académica' instead of generic 'Education').
        default_labels = {
            **game.section_labels_en,   # always available; non-empty for every game
            **(game.section_labels_es if force_language != "en" else {}),
            "summary": "Professional Summary",
            "education": "Education",
            "skills": "Skills",
            "experience": "Work Experience",
            "projects": "Projects",
            "achievements": "Achievements"
        }
        labels = {**default_labels, **parsed_data.get("section_labels", {})}

        # Edit-before-generate path (S2 of yaml-editor feature): stop here,
        # serialise the parsed data as YAML, and stream it back to the
        # frontend so the user can review/edit it before the (separate,
        # LLM-free) render step. No PDF is produced; the frontend can then
        # POST the (possibly edited) YAML to /api/render-from-yaml or
        # /api/analyze-yaml.
        if edit_before_generate:
            try:
                yaml_payload = _yaml_safe_dump_unicode(parsed_data)
            except Exception as yaml_err:
                yield f"data: {json.dumps({'error': f'YAML serialization failed: {yaml_err}'})}\n\n"
                return
            yield f"data: {json.dumps({'step': 'YAML Ready for Review', 'progress': 100, 'yaml': yaml_payload, 'yaml_ready': True})}\n\n"
            return

        yield f"data: {json.dumps({'step': 'Formatting Professional PDF', 'progress': 90})}\n\n"
        
        output_filename = f"tailored_resume_{int(time.time())}.pdf"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        use_rendercv = theme and theme != "classic_html"
        rendered = False
        if use_rendercv:
            try:
                print(f"[INFO] 🎨 Rendering PDF with RenderCV theme '{theme}' (fit_single_page={fit_single_page}, page_break_section={page_break_section}, photo={bool(photo_path)})...")
                await asyncio.to_thread(
                    render_cv_with_rendercv, 
                    parsed_data, 
                    output_path, 
                    theme, 
                    fit_single_page, 
                    page_break_section,
                    photo_path
                )
                rendered = True
            except Exception as r_err:
                print(f"[WARN] ⚠️ RenderCV theme '{theme}' failed: {r_err}. Falling back to Playwright HTML renderer.")

        if not rendered:
            print(f"[INFO] 📄 Rendering PDF with Playwright HTML engine (page_break_section={page_break_section})...")
            html_content = _render_html_template(parsed_data, labels, page_break_section, photo_path)
            
            def render_pdf_sync():
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.set_content(html_content)
                    page.pdf(path=output_path, prefer_css_page_size=True, print_background=True)
                    browser.close()

            await asyncio.to_thread(render_pdf_sync)

        _check_profile_urls_not_fragmented(output_path, parsed_data)

        # Auto re-audit (REQ-4): when force_language='en' triggered the translation
        # path, internally invoke the ATS audit against the freshly rendered PDF so
        # the user sees new ats_score / ai_detection_score in the same response.
        # Graceful degradation: audit failure leaves audit_scores=None (additive
        # payload keeps back-compat for old clients that only read download_url).
        audit_scores = None
        translation_meta = None
        if force_language == "en":
            yield f"data: {json.dumps({'step': 'Auditing translated CV', 'progress': 95})}\n\n"
            try:
                audit_scores = await _run_internal_audit(output_path, jd=jd, custom_instructions=custom_instructions, domain_game=domain_game)
            except Exception as audit_err:
                print(f"[WARN] Auto re-audit failed: {audit_err}")
            translation_meta = {"source_language": source_language, "target_language": "en", "forced": True}

        # Emit the YAML alongside `download_url` so the frontend can capture it
        # as `lastGeneratedYaml` and the user can re-open the YAML editor
        # after a non-edit-before-generate flow. ~2-5KB on the wire.
        # In the edit_before_generate path we returned earlier with the YAML
        # on its own SSE event, so this branch only runs for the direct flow.
        yaml_payload = _yaml_safe_dump_unicode(parsed_data)
        yield f"data: {json.dumps({'step': 'Finished', 'progress': 100, 'download_url': f'/api/download/{output_filename}', 'audit_scores': audit_scores, 'translation': translation_meta, 'yaml': yaml_payload})}\n\n"
        
    except Exception as e:
        import traceback
        print(f"[ERROR IN PIPELINE]: {e}")
        traceback.print_exc()
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _run_internal_audit(
    pdf_path: str,
    jd: Optional[str],
    custom_instructions: Optional[str],
    domain_game: Optional[str] = None,
) -> dict:
    """
    Re-invoke the ATS audit internally against the freshly rendered PDF.
    Reuses the same prompt body as POST /api/analyze-ats (the audit prompt
    in /api/analyze-ats above), but additionally accepts a `domain_game`
    so the audit vocabulary lines up with the CV domain (the audit_scores
    auto-fired after a Translate-to-English flow otherwise carry tech-only
    keywords into actionable_tips for HR / Psychology CVs).
    Returns the parsed dict (already with defensive defaults).
    """
    resume_text = extract_text(pdf_path)
    effective_jd = jd.strip() if (jd and jd.strip()) else (
        custom_instructions.strip() if (custom_instructions and custom_instructions.strip()) else
        "Optimización general y mejoramiento de calidad del CV"
    )
    audit_game = get_game(domain_game)
    return await _run_audit_against_text(
        resume_text=resume_text,
        jd_text=effective_jd,
        audit_game=audit_game,
    )

    return parsed


@app.post("/api/generate")
async def generate_resume(
    file: UploadFile,
    jd: Optional[str] = Form(None),
    target_role: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    portfolio_url: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(None),
    base_resume_filename: Optional[str] = Form(None),
    theme: Optional[str] = Form("sb2nov"),
    fit_single_page: Optional[bool] = Form(False),
    page_break_section: Optional[str] = Form(None),
    extract_linkedin_info: Optional[bool] = Form(False),
    strict_edits_only: Optional[bool] = Form(False),
    force_language: Optional[str] = Form(None),
    domain_game: Optional[str] = Form(None),
    edit_before_generate: Optional[bool] = Form(False),
    photo: Optional[UploadFile] = File(None),
):
    # Validate force_language early so unsupported values are rejected with HTTP 422
    # before any upload work or LLM call happens.
    if force_language is not None and force_language not in {"en"}:
        raise HTTPException(
            status_code=422,
            detail=f"force_language must be 'en' or omitted, got {force_language!r}"
        )

    # Validate domain_game early. The frontend selector offers:
    #   "tech" (default, preserves v2.5 behaviour),
    #   "hr_recruiting", "psychology".
    # Unknown values fall back to "tech" inside get_game(), but we reject them at
    # the edge so misconfigured clients surface the typo explicitly.
    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}
    if domain_game is not None and domain_game not in ALLOWED_GAMES:
        raise HTTPException(
            status_code=422,
            detail=f"domain_game must be one of {sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
        )

    # Save the original uploaded file temporarily (used as fallback if no base_resume_filename)
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, file.filename)
    with open(file_path, "wb") as f:
         f.write(await file.read())

    photo_path = await _persist_uploaded_photo(photo)

    return StreamingResponse(
        generation_pipeline(
            file_path,
            jd,
            target_role,
            github_url,
            linkedin_url,
            portfolio_url,
            custom_instructions,
            base_resume_filename,
            theme,
            fit_single_page or False,
            page_break_section,
            extract_linkedin_info or False,
            strict_edits_only or False,
            force_language,
            domain_game,
            edit_before_generate or False,
            photo_path,
        ),
        media_type="text/event-stream"
    )


@app.post("/api/analyze-ats")
async def analyze_ats(
    file: UploadFile,
    jd: Optional[str] = Form(None),
    domain_game: Optional[str] = Form(None)
):
    # Validate domain_game (same contract as /api/generate).
    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}
    if domain_game is not None and domain_game not in ALLOWED_GAMES:
        raise HTTPException(
            status_code=422,
            detail=f"domain_game must be one of {sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
        )

    try:
        load_dotenv(override=True)
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())

        resume_text = extract_text(file_path)

        effective_jd = jd.strip() if (jd and jd.strip()) else "Optimización general y mejoramiento de calidad del CV"

        # Audit prompt is composed from the selected game's vocabulary so the
        # 'actionable_tips' stop suggesting tech-only artifacts (e.g. 'Add Docker')
        # for HR or Psychology CVs. The single source of truth for the
        # LLM call lives in `_run_audit_against_text` (shared with
        # `_run_internal_audit` and the upcoming `/api/analyze-yaml`).
        audit_game = get_game(domain_game)
        return await _run_audit_against_text(
            resume_text=resume_text,
            jd_text=effective_jd,
            audit_game=audit_game,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


@app.post("/api/render-from-yaml")
async def render_from_yaml(
    yaml_content: str = Form(...),
    theme: Optional[str] = Form("sb2nov"),
    fit_single_page: Optional[bool] = Form(False),
    page_break_section: Optional[str] = Form(None),
    jd: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(None),
    domain_game: Optional[str] = Form(None),
    photo: Optional[UploadFile] = File(None),
):
    """
    Render-only endpoint: takes the YAML edited by the user, parses it, and
    renders the PDF using the same RenderCV / Playwright path that
    /api/generate uses after the LLM call. No LLM call.

    Spec coverage:
      S6 (yaml-editor feature): yaml_content (required), theme,
        fit_single_page, page_break_section, jd, custom_instructions,
        domain_game. Reuses RenderCV/Playwright path. No LLM call.
      S10 (multi-domain integration): domain_game propagates so the
        section_labels fallback uses the selected game's localized
        headers (e.g. psychology's "Formación Académica").
    """
    # Validate domain_game against the same contract as the other endpoints.
    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}
    if domain_game is not None and domain_game not in ALLOWED_GAMES:
        raise HTTPException(
            status_code=422,
            detail=f"domain_game must be one of {sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
        )

    # Parse the YAML.
    if not yaml_content or not yaml_content.strip():
        raise HTTPException(
            status_code=400,
            detail="yaml_content is required and must not be empty"
        )
    try:
        parsed_data = _pyyaml.safe_load(yaml_content)
    except _pyyaml.YAMLError as ye:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {ye}")
    if not isinstance(parsed_data, dict):
        raise HTTPException(
            status_code=400,
            detail=f"Expected a YAML mapping at the top level, got {type(parsed_data).__name__}"
        )

    photo_path = await _persist_uploaded_photo(photo)

    # Compose labels using the same fallback chain as /api/generate so the
    # rendered PDF is consistent regardless of which path produced the
    # parsed_data (LLM vs YAML). Order: game ES (preferred, the user's
    # primary locale is LATAM Spanish), game EN, hardcoded EN defaults.
    game = get_game(domain_game)
    default_labels = {
        **game.section_labels_es,
        **game.section_labels_en,
        "summary": "Professional Summary",
        "education": "Education",
        "skills": "Skills",
        "experience": "Work Experience",
        "projects": "Projects",
        "achievements": "Achievements",
    }
    labels = {**default_labels, **parsed_data.get("section_labels", {})}

    # Render PDF. Reuses the same RenderCV / Playwright path as
    # /api/generate. We intentionally do NOT call any LLM here.
    output_filename = f"tailored_resume_{int(time.time())}.pdf"
    output_path = os.path.join(OUTPUT_DIR, output_filename)

    use_rendercv = theme and theme != "classic_html"
    rendered = False
    if use_rendercv:
        try:
            print(f"[INFO] 🎨 Render-from-YAML: RenderCV theme '{theme}' (fit_single_page={fit_single_page}, page_break_section={page_break_section}, photo={bool(photo_path)})...")
            await asyncio.to_thread(
                render_cv_with_rendercv,
                parsed_data,
                output_path,
                theme,
                fit_single_page or False,
                page_break_section,
                photo_path,
            )
            rendered = True
        except Exception as r_err:
            print(f"[WARN] ⚠️ RenderCV theme '{theme}' failed: {r_err}. Falling back to Playwright HTML renderer.")

    if not rendered:
        print(f"[INFO] 📄 Render-from-YAML: Playwright HTML engine (page_break_section={page_break_section})...")
        html_content = _render_html_template(parsed_data, labels, page_break_section, photo_path)
        def render_pdf_sync():
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_content(html_content)
                page.pdf(path=output_path, prefer_css_page_size=True, print_background=True)
                browser.close()
        await asyncio.to_thread(render_pdf_sync)

    _check_profile_urls_not_fragmented(output_path, parsed_data)

    return {
        "download_url": f"/api/download/{output_filename}",
        "filename": output_filename,
    }


@app.post("/api/analyze-yaml")
async def analyze_yaml(
    yaml_content: str = Form(...),
    jd: Optional[str] = Form(None),
    domain_game: Optional[str] = Form(None),
):
    """
    Audit-only endpoint for a user-edited YAML. No PDF render.

    The frontend uses this when the user clicks `VALIDAR YAML` in the
    YAML editor panel: it serializes the parsed dict back to a
    plain-text narrative via `_serialize_resume_data_as_text` and
    runs the same per-game audit prompt as `/api/analyze-ats`
    (delegated to `_run_audit_against_text`).

    Spec coverage:
      S8 (yaml-editor feature): accepts yaml_content (required) and
        optional jd. Serializes the parsed dict into a narrative and
        runs the same audit LLM prompt as /api/analyze-ats. No PDF
        render. The frontend takes care of adding a 'YAML vN' entry
        to scoreHistory on success.
      S10 (multi-domain integration): domain_game propagates so the
        audit uses the selected game's vocabulary (no 'add Docker'
        on HR / Psychology CVs).
    """
    # Validate domain_game against the same contract as the other endpoints.
    ALLOWED_GAMES = {"tech", "hr_recruiting", "psychology"}
    if domain_game is not None and domain_game not in ALLOWED_GAMES:
        raise HTTPException(
            status_code=422,
            detail=f"domain_game must be one of {sorted(ALLOWED_GAMES)} or omitted, got {domain_game!r}"
        )

    # Parse the YAML.
    if not yaml_content or not yaml_content.strip():
        raise HTTPException(
            status_code=400,
            detail="yaml_content is required and must not be empty"
        )
    try:
        parsed_data = _pyyaml.safe_load(yaml_content)
    except _pyyaml.YAMLError as ye:
        raise HTTPException(status_code=400, detail=f"Invalid YAML: {ye}")
    if not isinstance(parsed_data, dict):
        raise HTTPException(
            status_code=400,
            detail=f"Expected a YAML mapping at the top level, got {type(parsed_data).__name__}"
        )

    # Serialize the parsed dict to a plain-text narrative that mirrors
    # what `extract_text` would yield from a rendered PDF. The audit
    # LLM sees the same shape regardless of whether the input is a
    # rendered PDF or a user-edited YAML dict.
    narrative = _serialize_resume_data_as_text(parsed_data)

    # Compose jd_text: prefer the JD the user supplied, fall back to a
    # generic Spanish default.
    effective_jd = (jd or "").strip() or "Optimización general y mejoramiento de calidad del CV"

    # Resolve the domain game and run the audit.
    audit_game = get_game(domain_game)
    try:
        return await _run_audit_against_text(
            resume_text=narrative,
            jd_text=effective_jd,
            audit_game=audit_game,
        )
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# YAML repair: ask the LLM to fix a damaged YAML back into the schema the
# render path expects. Two-pass strategy:
#   1. Local syntactic validation (yaml.safe_load) — if it fails, capture the
#      parser error and ask the LLM for a syntax repair.
#   2. Local schema validation against GeminiResumeOutput (Pydantic) — if it
#      fails, capture the validation errors and ask the LLM for a structural
#      repair, with the previous YAML + domain_game as context.
#   3. Both pass → return the YAML untouched with {repaired: False}.
# Always returns 200 with a JSON envelope so the frontend can distinguish
# "no repairs needed" from "LLM fixed it" from "could not fix".
# ---------------------------------------------------------------------------
_YAML_SCHEMA_DESCRIPTION = """
{
  "name": "Full Name (string)",
  "location": "City, Country (string)",
  "phone": "Phone Number (string)",
  "email": "Email Address (string)",
  "portfolio": "Portfolio URL (string)",
  "linkedin": "LinkedIn URL (string)",
  "github": "GitHub URL (string)",
  "summary": "Concise professional summary (string)",
  "education": [
    {
      "school": "string",
      "degree": "string",
      "dates": "string (e.g. '2020 - 2024' or '2018-01 - Presente')",
      "gpa": "string (optional)"
    }
  ],
  "skills": [
    { "category": "string (e.g. 'Backend', 'Bases de Datos')", "items": ["tool1", "tool2"] }
  ],
  "experience": [
    {
      "company": "string",
      "role": "string",
      "dates": "string",
      "points": ["Achievement 1", "Achievement 2", "Achievement 3"]
    }
  ],
  "projects": [
    {
      "name": "string",
      "dates": "string",
      "url": "string (live demo URL — optional)",
      "github_url": "string (repo URL — optional)",
      "points": ["Achievement 1", "Achievement 2"]
    }
  ],
  "achievements": ["Award 1", "Certification 2"],
  "section_labels": {
    "summary": "string (e.g. 'Resumen Profesional')",
    "education": "string",
    "skills": "string (e.g. 'Habilidades')",
    "experience": "string",
    "projects": "string",
    "achievements": "string",
    "portfolio": "string"
  }
}

CRITICAL RULES (your output MUST honor):
1. Output ONLY a valid YAML document. No prose, no ``` fences, no comments.
2. lists MUST be YAML lists (lines starting with `- `), not inline `[a, b, c]`.
3. Strings inside lists MUST be quoted with double quotes if they contain
   colons, hashes, or special YAML characters.
4. NEVER invent new top-level keys. NEVER drop required keys.
5. Preserve all present candidate facts verbatim (real names, dates, schools,
   tool names, metrics). Only fix structure, indentation, and types.
"""


def _parse_yaml_safe(text: str):
    """Returns (parsed_dict | None, error_message | None)."""
    try:
        parsed = _pyyaml.safe_load(text)
    except _pyyaml.YAMLError as e:
        return None, f"YAML syntax error: {e}"
    if not isinstance(parsed, dict):
        return None, f"Top-level must be a YAML mapping (got {type(parsed).__name__})"
    return parsed, None


def _validate_yaml_schema(parsed: dict):
    """Returns (cleaned_dict | None, error_message | None) using Pydantic.

    Pre-populates all fields with the same defaults that `render_from_yaml`
    applies, so a YAML missing optional contact fields does NOT fail this
    check — only structural mismatches (wrong types, missing required
    sub-keys on lists, etc.) will.
    """
    defaults = {
        "name": "", "location": "", "phone": "", "email": "",
        "portfolio": "", "linkedin": "", "github": "",
        "summary": "", "education": [], "skills": [],
        "experience": [], "projects": [], "achievements": [],
        "section_labels": {},
    }
    populated = {**defaults, **parsed}  # parsed wins over defaults
    try:
        cleaned = GeminiResumeOutput(**populated).model_dump()
    except Exception as e:
        return None, f"Schema mismatch: {e}"
    return cleaned, None


def _content_tokens(text: str) -> set:
    """
    Extract the meaningful tokens (words, numbers) from a YAML document so two
    versions can be compared for content drift. YAML syntax itself — indentation,
    colons, quotes, list dashes — is deliberately discarded.
    """
    # Drop line-leading list markers so "- Python" and "Python" tokenize alike.
    cleaned = re.sub(r"^\s*-\s+", " ", text, flags=re.MULTILINE)
    # Numbers are kept at any length, including bare percentages and counts.
    # A previous `{3,}` threshold silently dropped "30%", "40" and "15", which
    # meant the drift check could not see a model swapping one metric for
    # another — the single most damaging edit it could make to a CV.
    numbers = re.findall(r"\d+(?:[.,]\d+)*", cleaned)
    # Words keep the 3-character floor to suppress noise, while still
    # capturing accented letters used throughout Spanish.
    words = re.findall(r"[^\W\d_]{3,}", cleaned, flags=re.UNICODE)
    return {w.lower() for w in words} | {n for n in numbers}


def _content_drift(original: str, repaired: str) -> Optional[str]:
    """
    Returns None when a repair preserved the user's text, or a human-readable
    reason when it did not.

    This is the programmatic guarantee behind the product promise: editing the
    YAML by hand and pressing "Generar CV" never rewrites what the user wrote.
    The LLM is asked to fix structure only; this check enforces it, because a
    prompt instruction alone is not a guarantee.

    Returns a reason string when content was lost or invented.
    """
    before = _content_tokens(original)
    after = _content_tokens(repaired)
    if not before:
        return None

    # A word the user split across two lines ("selecci\n  ón") is rejoined by the
    # repair, so test substring presence against a whitespace-stripped blob
    # instead of exact token equality.
    after_flat = re.sub(r"\s+", "", repaired).lower()

    lost = sorted(w for w in before if w not in after and w not in after_flat)
    if lost:
        sample = ", ".join(lost[:8])
        # A lost number is a changed metric, which reads very differently to the
        # user than a lost word, so name it as such.
        has_number = any(any(ch.isdigit() for ch in w) for w in lost)
        noun = "dato" if has_number else ("palabra" if len(lost) == 1 else "palabras")
        return (
            f"la reparación cambió o perdió {len(lost)} "
            f"{'datos' if has_number and len(lost) > 1 else noun} de tu texto "
            f"({sample}{'…' if len(lost) > 8 else ''})"
        )

    # A pure syntax fix (indentation, quoting, list markers, colons) adds zero
    # words by definition. Anything new is therefore invented content, so the
    # allowance is exactly zero. There is no legitimate structural token a
    # YAML syntax repair would introduce.
    added = sorted(after - before)
    if added:
        sample = ", ".join(added[:8])
        noun = "palabra" if len(added) == 1 else "palabras"
        verb = "estaba" if len(added) == 1 else "estaban"
        return (
            f"la reparación agregó {len(added)} {noun} que no {verb} en tu texto "
            f"({sample}{'…' if len(added) > 8 else ''})"
        )

    return None


async def _ask_llm_to_repair_yaml_async(broken_yaml: str, schema_errors: list[str], domain_game: Optional[str]) -> str:
    domain_line = f"\nTARGET DOMAIN (structural hint only — do not change any wording): {domain_game}\n" if domain_game else ""
    prompt = f"""You are a YAML SYNTAX repair engine. The user hand-edited a YAML document and broke its structure. Your job is to make it parse. You are NOT a writing assistant.

CONTEXT — WHY THIS MATTERS
This document is a finished resume the user wrote by hand. They pressed "Generar CV" and want a PDF of EXACTLY what they wrote. You exist only because the file will not parse. Once it parses, your work is done.

THE ONLY THINGS YOU MAY CHANGE
  - Indentation.
  - Quoting and escaping of values (wrap a value in double quotes if it contains a colon, a leading dash, a `#`, or a quote).
  - Multiline values: convert a value the user split across lines into a block scalar. Use `>-` for prose, `|-` when the line breaks are meaningful. Example:
      WRONG: `summary: Psicóloga Organizacional con más de 2 años\n  de experiencia en selección`
      RIGHT: `summary: >-\n    Psicóloga Organizacional con más de 2 años\n    de experiencia en selección`
  - List markers, so every item starts with `- `.
  - Colons and separators.
  - Empty lists written as `key: []` on one line.

THE THINGS YOU MUST NOT DO
  - Do not rewrite, rephrase, translate, or "improve" any sentence.
  - Do not shorten, expand, summarize, or reorder.
  - Do not change dates, numbers, names, companies, tools, or URLs.
  - Do not add information the user did not write.
  - Do not delete information, even if it looks redundant or misspelled.
  - Do not change the language of any value.
  - Do not merge or split sections. Do not add or remove keys.
  - Do not convert one sentence into a list of sentences, or a list into a sentence.

SELF-CHECK BEFORE ANSWERING
Re-read your output and confirm every word of the input appears, unchanged. If you cannot fix the structure without altering a single word, output the original text with only the indentation and quoting corrected.

OUTPUT
Only the repaired YAML. No prose, no markdown fences, no explanation.{domain_line}

VALIDATION ERRORS:
{chr(10).join(f"- {e}" for e in schema_errors)}

EXPECTED STRUCTURE:
{_YAML_SCHEMA_DESCRIPTION}

BROKEN YAML:
```yaml
{broken_yaml}
```
"""
    return await call_llm_api(prompt)


@app.post("/api/repair-yaml")
async def repair_yaml(
    yaml_content: str = Form(...),
    domain_game: Optional[str] = Form(None),
):
    """
    Repair a damaged YAML that the user edited in the YAML editor panel.

    Two-pass validation:
      1. yaml.safe_load  → catches indentation, quoting, missing colons, etc.
      2. GeminiResumeOutput (Pydantic) → catches structural mismatch (e.g. a
         list that became a string, or a missing `points` key inside experience).

    If either validation fails, send the YAML + the error report to the LLM
    asking for a strict-yet-faithful structural repair. The LLM response is
    parsed and re-validated. If the second pass ALSO fails, return the partial
    repair with `repairs: [...]` AND `schema_errors: [...]` so the user can
    finish manually.

    Returns:
        {
          "ok": bool,             # True if final YAML passes both validations
          "yaml": str,            # the YAML text to put back in the textarea
          "repairs": list[str],   # human-readable summary of what was changed
          "schema_errors": list[str]  # remaining issues (empty if ok=True)
        }
    """
    try:
        original_yaml = yaml_content
        repairs: list[str] = []

        # Pass 1 — local syntactic validation
        parsed, syntax_err = _parse_yaml_safe(original_yaml)
        if syntax_err or parsed is None:
            repairs.append(f"Local validation rejected the YAML: {syntax_err}")
            llm_response = await _ask_llm_to_repair_yaml_async(
                original_yaml, [syntax_err or "unknown syntax error"], domain_game,
            )
            # Strip markdown fences if present
            llm_yaml = _strip_yaml_fences(llm_response)
            # Re-validate the LLM response
            parsed2, syntax_err2 = _parse_yaml_safe(llm_yaml)
            if syntax_err2 or parsed2 is None:
                return {
                    "ok": False,
                    "yaml": llm_yaml,
                    "repairs": repairs + [f"LLM still returned invalid YAML: {syntax_err2}"],
                    "schema_errors": [syntax_err2 or "yaml.safe_load failed"],
                    "error": (
                        f"La IA no pudo producir YAML con sintaxis válida. "
                        f"Editá el YAML manualmente. Error del parser: {syntax_err2 or 'yaml.safe_load failed'}"
                    ),
                }
            repairs.append("LLM produced valid YAML syntax.")
            yaml_text = llm_yaml
            parsed = parsed2
            # Hard guarantee: the repair must not have rewritten the user's
            # text. A prompt instruction is not enough on its own.
            drift = _content_drift(original_yaml, llm_yaml)
            if drift:
                return {
                    "ok": False,
                    "yaml": original_yaml,
                    "repairs": repairs,
                    "schema_errors": [f"El texto fue modificado: {drift}"],
                    "error": (
                        f"La IA reparó la sintaxis pero {drift}. "
                        f"Se devolvió tu texto original sin tocar — corregí la sintaxis a mano."
                    ),
                }
            repairs.append("Texto verificado: sin cambios de contenido.")
        else:
            yaml_text = original_yaml

        # Pass 2 — schema validation against GeminiResumeOutput
        cleaned, schema_err = _validate_yaml_schema(parsed)
        if schema_err or cleaned is None:
            repairs.append(f"Local schema check rejected the YAML: {schema_err}")
            llm_response = await _ask_llm_to_repair_yaml_async(
                yaml_text, [schema_err or "unknown schema error"], domain_game,
            )
            llm_yaml = _strip_yaml_fences(llm_response)
            parsed2, syntax_err2 = _parse_yaml_safe(llm_yaml)
            if syntax_err2 or parsed2 is None:
                return {
                    "ok": False,
                    "yaml": llm_yaml,
                    "repairs": repairs + [f"LLM returned YAML that still fails syntax: {syntax_err2}"],
                    "schema_errors": [syntax_err2 or "yaml.safe_load failed"],
                    "error": (
                        f"La IA no pudo arreglar la sintaxis del YAML. "
                        f"Error del parser: {syntax_err2 or 'yaml.safe_load failed'}"
                    ),
                }
            cleaned2, schema_err2 = _validate_yaml_schema(parsed2)
            if schema_err2 or cleaned2 is None:
                # Best-effort: return the partial YAML so the user can finish manually
                return {
                    "ok": False,
                    "yaml": llm_yaml,
                    "repairs": repairs + ["LLM returned YAML that still fails schema validation."],
                    "schema_errors": [schema_err2 or "schema validation failed"],
                    "error": (
                        f"La IA no pudo arreglar el schema del YAML. "
                        f"Editá manualmente. Error de schema: {schema_err2 or 'schema validation failed'}"
                    ),
                }
            repairs.append("LLM produced YAML that passes schema validation.")
            yaml_text = llm_yaml
            # Same content guarantee on the schema-repair pass. Compare against
            # what we actually sent (the locally-valid text) so the original
            # user's words are never lost across two chained repairs.
            drift = _content_drift(yaml_text, llm_yaml)
            if drift:
                return {
                    "ok": False,
                    "yaml": original_yaml,
                    "repairs": repairs,
                    "schema_errors": [f"El texto fue modificado: {drift}"],
                    "error": (
                        f"La IA reparó la estructura pero {drift}. "
                        f"Se devolvió tu texto original sin tocar — corregí a mano."
                    ),
                }
            repairs.append("Texto verificado: sin cambios de contenido.")

        # Both validations passed (either locally or after an LLM repair).
        # Re-serialize through yaml.safe_dump so the output is ALWAYS block-style
        # and human-readable. The LLM frequently answers with JSON (technically
        # valid YAML) which renders as one unreadable line in the textarea.
        # yaml_text is guaranteed parseable at this point, and safe_dump is
        # faithful to the parsed structure, so this cannot alter content.
        try:
            normalized = _yaml_safe_dump_unicode(_pyyaml.safe_load(yaml_text))
            if normalized.strip() != yaml_text.strip():
                repairs.append("Re-formateado a YAML legible (bloques y saltos de línea).")
            yaml_text = normalized
        except Exception as fmt_err:
            print(f"[WARN] Could not normalize repaired YAML formatting: {fmt_err}")

        # Final belt-and-braces check against the user's original input.
        final_drift = _content_drift(original_yaml, yaml_text)
        if final_drift:
            return {
                "ok": False,
                "yaml": original_yaml,
                "repairs": repairs,
                "schema_errors": [f"El texto fue modificado: {final_drift}"],
                "error": (
                    f"La reparación alteró tu texto ({final_drift}). "
                    f"Se devolvió tu texto original sin tocar."
                ),
            }

        return {
            "ok": True,
            "yaml": yaml_text,
            "repairs": repairs,
            "schema_errors": [],
        }
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"ok": False, "yaml": yaml_content, "repairs": [], "schema_errors": [f"Repair endpoint error: {e}"]}


def _strip_yaml_fences(text: str) -> str:
    """Strip ```yaml ... ``` markdown fences if the LLM added them despite instructions."""
    t = text.strip()
    if t.startswith("```"):
        # Take the content between the first line and the last ```
        first_newline = t.find("\n")
        if first_newline != -1:
            t = t[first_newline + 1:]
        if t.endswith("```"):
            t = t[:-3].rstrip()
    return t


@app.get("/api/download/{filename}")
async def download_resume(filename: str):
    """Serve a generated PDF from the persistent output directory.

    Two layers of defence against path traversal:

    1. Strict regex on the URL segment so callers can only ask for files
       matching the exact naming convention that ``generation_pipeline``
       writes (``tailored_resume_<unix_ts>.pdf``).
    2. ``Path.resolve()`` + ``is_relative_to(OUTPUT_DIR)`` to catch any
       segment that survives the regex (defence in depth).
    """
    if not _DOWNLOAD_FILENAME_RE.fullmatch(filename):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    output_dir_resolved = Path(OUTPUT_DIR).resolve()
    file_path = (output_dir_resolved / filename).resolve()

    if not file_path.is_relative_to(output_dir_resolved):
        raise HTTPException(status_code=400, detail="Invalid filename format")

    if not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")

    return FileResponse(file_path, filename=filename, media_type="application/pdf")

@app.post("/api/clear-cache")
async def clear_cache():
    try:
        deleted_count = 0
        if os.path.exists(OUTPUT_DIR):
            for fname in os.listdir(OUTPUT_DIR):
                fpath = os.path.join(OUTPUT_DIR, fname)
                if os.path.isfile(fpath):
                    try:
                        os.remove(fpath)
                        deleted_count += 1
                    except Exception as err:
                        print(f"Could not remove {fpath}: {err}")
        # Candidate photos live in a subdirectory, so the loop above (which
        # only unlinks files) never reached them. Drop the whole directory.
        photos_removed = _prune_photos(PHOTOS_DIR, keep=set())
        return {
            "status": "ok",
            "deleted_files": deleted_count,
            "deleted_photos": photos_removed,
            "message": "Cache, CVs generados y fotos eliminados correctamente.",
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


