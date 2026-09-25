import os
import sys
import io

# Force UTF-8 stdout/stderr on Windows so print() with non-ASCII chars
# (emojis, accented chars, etc.) does not raise UnicodeEncodeError against
# the default cp1252 codec.
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)

import json
import asyncio
from typing import Optional
from fastapi import FastAPI, UploadFile, Form, BackgroundTasks, HTTPException
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

from dotenv import load_dotenv
from render_service import render_cv_with_rendercv
from language import detect_language

load_dotenv()

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Persistent directory for generated PDFs — survives uvicorn hot-reloads
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

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
  <h1>{{ name }}</h1>
  <div class="contact-info">
    {% set items = [] %}
    {% if location %}{% set _ = items.append(location) %}{% endif %}
    {% if phone %}{% set _ = items.append(phone) %}{% endif %}
    {% if email %}{% set _ = items.append(email) %}{% endif %}
    {% if linkedin %}{% set _ = items.append('<a href="' ~ linkedin ~ '">LinkedIn</a>') %}{% endif %}
    {% if github %}{% set _ = items.append('<a href="' ~ github ~ '">GitHub</a>') %}{% endif %}
    {% if portfolio %}{% set _ = items.append('<a href="' ~ portfolio ~ '">' ~ (labels.portfolio if (labels and 'portfolio' in labels) else ('Portafolio' if (labels and labels.summary != 'Professional Summary') else 'Portfolio')) ~ '</a>') %}{% endif %}
    {{ items|join(' | ') }}
  </div>


  
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
    if not gemini_key or gemini_key.startswith("AQ."):
        err_detail = f" (Error en DeepSeek/Primario: {primary_error_msg})" if primary_error_msg else ""
        raise ValueError(f"Fallo en modelo primario{err_detail}. Además, la GEMINI_API_KEY no es válida. Obtén una clave gratuita en https://aistudio.google.com/app/apikey")
        
    genai.configure(api_key=gemini_key)
    generation_config = {"response_mime_type": "application/json"}
    
    models_to_try = ['gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-1.5-pro']
    last_err = None
    
    for m_name in models_to_try:
        try:
            print(f"[LLM INFO] Intentando modelo Gemini de respaldo: '{m_name}'...")
            model = genai.GenerativeModel(m_name, generation_config=generation_config)
            res = await asyncio.wait_for(asyncio.to_thread(model.generate_content, prompt_text), timeout=50.0)
            if res and res.text:
                return res.text
        except Exception as e:
            print(f"[LLM WARN] El modelo Gemini '{m_name}' falló/agotó tiempo: {e}")
            last_err = e
            continue
            
    err_detail = f" (Error primario: {primary_error_msg})" if primary_error_msg else ""
    raise ValueError(f"Fallaron todos los modelos. Gemini: {last_err}{err_detail}")


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
    force_language: Optional[str] = None
):
    """
    The end-to-end generation pipeline. Returns an SSE stream of progress events and
    ends with a `Finished` event containing the download URL.

    When `force_language='en'`, prepends AND appends a LANGUAGE OVERRIDE block to the
    system prompt so the output CV is generated in English regardless of the source
    JD language. See _build_language_override for the exact wording.
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
            prompt = f"""
{language_override_block}
You are a professional technical recruiter and resume writer specialized in ATS optimization.
You are provided with a 'Base Resume' of a candidate and a target 'Job Description' (JD).
Your goal is to tailor the candidate's actual experience to align perfectly with the target role and achieve maximum ATS scores on platforms like CompuTrabajo, Workday, LinkedIn, and Greenhouse.

STRICT RULES (CRITICAL — ALL MUST BE FOLLOWED):
1. ZERO HALLUCINATION & NO INVENTING DATA: You MUST ONLY use the candidate's real experiences, companies, education, degrees, dates, and projects provided in the 'Base Resume' and the 'Extracted LinkedIn Profile Data' (if provided). Absolutely DO NOT invent, hallucinate, or import fake or third-party companies, internships, jobs, dates, or projects (e.g. DO NOT add ZScore, Hackumi, Resume Analyzer, or any experience not in the Base Resume or LinkedIn data).
2. TAILOR AND RESTRUCTURE ONLY: Rephrase, reorganize, merge, and emphasize the candidate's real existing achievements, skills, and experience from the Base Resume and extracted LinkedIn profile using strong action verbs and relevant keywords from the Job Description.
3. PAGE LENGTH & COMPACTNESS RULE:
   - If candidate has less than 5 years of experience, strictly fit into a 1-page layout.
   - If candidate has more than 5 years of experience, maximum 2 pages.
   - Provide 2 to 3 concise bullet points per role. Ensure bullet points are self-contained (1-2 lines) so they never leave solitary orphan lines.
4. PROFESSIONAL SUMMARY ENGAGEMENT:
   - Provide an engaging, high-impact professional summary of exactly 3 lines that hooks the recruiter in seconds, incorporating the target role and key value proposition.
5. WORK EXPERIENCE REWRITING & ACHIEVEMENT FORMULA (CRITICAL - MANDATORY FOR EVERY BULLET POINT):
   - You MUST aggressively rewrite EVERY SINGLE bullet point in the `experience` list (`points` array). DO NOT copy-paste raw text from the base resume.
   - Redact all achievements and bullet points strictly using Google's XYZ Formula: "Accomplished [X] as measured by [Y], by doing [Z]" (ACCIÓN + CONTEXTO/MÉTODO + RESULTADO MEDIBLE en números, %, o ahorro de tiempo/costos).
   - Every single bullet point in `experience` MUST start with a strong high-impact action verb:
     * Spanish: Diseñé, Implementé, Refactoricé, Desplegué, Migré, Optimicé, Automaticé, Incrementé, Reduje, Agilicé, Maximicé, Consolidé, Lideré, Construí.
     * English: Engineered, Architected, Implemented, Spearheaded, Optimized, Automated, Streamlined, Reduced, Scaled, Deployed, Refactored.
   - ABSOLUTELY PROHIBITED: Passive or lazy phrasing like "Responsable de...", "Encargado de...", "Trabajé en...", "Desarrollo de...", or "Responsibilities included...". You must convert all passive duties into active quantifiable accomplishments.
   - If exact metrics/numbers are not provided in the base text, estimate or frame the realistic positive impact (e.g., "mejorando la eficiencia operativa", "reduciendo errores de despliegue", "optimizando tiempos de respuesta") while keeping all candidate facts accurate.
6. TONE & HUMANITY:
   - Professional, authoritative, yet authentic and human tone without sounding like a robotic generic template.
7. ATS KEYWORD DENSITY & INTEGRATION:
   - Naturally integrate key technical and domain keywords from the target job description into bullet points and summary. Prioritize exact matches.
8. LANGUAGE MATCHING (CRITICAL): Detect the dominant language of the Job Description. Generate ALL text content (summary, bullet points, skill categories, achievements) in THAT SAME language. If the JD is in English → output everything in English. If the JD is in Spanish → output everything in Spanish. Default to the JD language; never mix languages in the same document. Also output the correct localized 'section_labels' accordingly. [OVERRIDDEN when force_language is set — see LANGUAGE OVERRIDE block at the end of this prompt.]
9. ATS FORMATTING COMPLIANCE: Clean, single-column layout parseable by ATS parsers. Standard section headings.
10. DOMAIN-AWARE INTELLIGENT SKILLS CATEGORIZATION:
   - Categorize skills strictly according to the candidate's actual profession/domain and the target role (e.g. tech vs non-tech).
11. CANDIDATE LOCATION & PHONE FORMAT:
   - City and Country (e.g., 'Medellín, Colombia') and phone number with international dialing prefix.
12. PROJECTS & LINKS:
   - Support links for live demos, GitHub, and portfolio websites.
   - NEVER put the exact same GitHub URL into both 'url' and 'github_url'. 'url' is strictly for live demo sites (e.g. Vercel/Netlify); if no live site exists, leave 'url': ''.
13. ATS ADVANCED REFINEMENT & ANTI-SPAM RULES (ats_optimization):
   - AVOID KEYWORD STUFFING: Do NOT repeat the exact same tool or term in more than 2 sections without varying the phrasing/context. Avoid robotic repetition of niche internal names (e.g. generalise or group obscure internal tool names like "Gentle AI" -> "orquestadores de agentes IA").
   - VERIFY TOOL NAMES & RELEVANCE: Ensure every tool or orchestrator mentioned is recognizable, real, and relevant to the target role.
   - DATE CONSISTENCY & ONGOING ROLES: If a degree or job started in the past or current month (e.g. "2026-08" when current date is September 2026) and is ongoing, format it as "2026-08 - Actualidad" (Spanish) or "2026-08 - Present" (English). ONLY use "Inicio: YYYY-MM" if the start date is strictly in a future month that has not arrived yet.
   - PROFESSIONAL HEADLINE MATCH: Integrate a clear professional headline/title right under the name or within the summary header matching the target role (e.g., "Fullstack Developer | Python · React · FastAPI").
   - SEPARATE CERTIFICATIONS: Clearly distinguish between "Certificaciones completadas" and "Certificaciones en curso".
   - VARY PHRASING: Redact mentions of skills/tools using synonyms and varied context across summary, experience, and projects to avoid triggering AI-generated text detectors or spam filters.
   - TARGET ROLE ALIGNMENT IN PREVIOUS ROLES: Reflect the target job title/role (or close industry equivalent) in previous experience aliases where applicable (e.g., adding "Fullstack Developer" if formal title was generic).
14. KEYWORD GAP DETECTION & AUTOMATIC SKILL ENRICHMENT (keyword_gap_detection):
   - Detect every technology, framework, tool, protocol, or testing library mentioned in Experience or Projects (e.g. FastAPI, Playwright, SSE, Ant Design, Cloudflare, CI/CD, REST APIs / Swagger-OpenAPI, Jest, JUnit, Cypress, Selenium, Android/Java) that is NOT listed in the `skills` array.
   - AUTOMATICALLY add these exact technical keyword strings to the `skills` array under their proper category (e.g. "Lenguajes & Frameworks", "DevOps & Automatización", "Bases de Datos & Cloud", "Comunicación & Integraciones").
   - ATS parsers match exact strings: never leave a tool mentioned in projects/experience out of the candidate's explicit `skills` list.
15. HUMAN BURSTINESS & SYNTACTIC DIVERSITY (anti_ai_detector_burstiness):
   - CRITICAL TO PASS AI DETECTORS: Do NOT repeat the exact same sentence pattern (e.g., "Desarrollé [X] mediante [Y] logrando [Z]") across project bullet points or experience entries. Monotonous repetition of syntactic structure drops burstiness/perplexity and triggers AI content detectors.
   - MANDATORY STRUCTURAL ROTATION: Alternate bullet point structures across projects and roles using 4 distinct narrative patterns:
     * Pattern A (Outcome-First): "Incrementé la velocidad de respuesta en 40% al refactorizar los endpoints..."
     * Pattern B (Challenge/Context-First): "Ante cuellos de botella en el procesamiento masivo de datos, diseñé una arquitectura de colas..."
     * Pattern C (Action/Architectural-First): "Lideré el despliegue del sistema distribuido sobre AWS, reduciendo la latencia a menos de 100ms..."
     * Pattern D (Tool/Solution-First): "Mediante FastAPI y PostgreSQL, automaticé los flujos de facturación eliminando 15 horas semanales de trabajo manual..."
   - Vary sentence length and rhythmic cadence naturally (some short 1-line statements, some 2-line contextual achievements) to emulate authentic human authorship.
16. SEPARATE ACHIEVEMENTS VS IN-PROGRESS FORMATION (split_achievements_vs_inprogress):
   - Keep ONLY completed, verifiable certifications or honors in the `achievements` array (e.g. "Diplomado Big Data y BI", "Curso Ágiles Design Thinking y Scrum").
   - Move all certifications or degrees currently in progress (e.g., "AZ-900", "AWS Cloud Practitioner (en curso)") out of `achievements` and place them either in `education` or as a category in `skills` labeled "Formación Complementaria (En Curso)".
17. SYNTACTIC VARIATION IN PROJECTS & EXPERIENCE (vary_bullet_syntax):
   - PROHIBITED: Do NOT use the exact same template "Verbo + objeto + mediante/con + tecnología... Implementé el stack con X, logrando Y en Z%" in more than 2 consecutive bullet points across projects or experience.
   - Use problem-first openings (e.g., "Los equipos de bodega carecían de visibilidad en tiempo real; construí una plataforma con Laravel y React que..."), metric-first openings ("Reduje en 40% los costos..."), and alternate short vs long sentences between projects.
18. NATURAL HUMAN LANGUAGE MARKERS (natural_language_markers):
   - Introduce subtle natural human phrasing without losing professionalism.
   - Avoid monotonous repetitive transitions like "Implementé el stack con" or starting 4 consecutive bullets with "Desarrollé".
   - Rotate opening action phrases: "Construí", "Diseñé e implementé", "Lideré el desarrollo de", "Refactoricé", "Desplegué", "Migré".
19. CERTIFICATION EVIDENCE & VERIFIABLE LINKS (certification_evidence_link):
   - Whenever verifiable links or badges (Credly, LinkedIn Learning, university credentials) exist in the base text for certifications/achievements, explicitly preserve and format them (e.g. "Diplomado en Big Data y BI [Credly Badge / Link]") to maximize human credibility and pass external ATS verification.
20. STRICT REPETITION BAN IN PROJECTS (anti_repetition_project_footprint):
   - STRICTLY FORBIDDEN: NEVER repeat the phrase "Implementé el stack con...", "Desarrollé una...", or "Construí una..." across multiple project bullet points. Repeating identical transition phrases across projects is the #1 footprint detected by AI content checkers.
   - MANDATORY UNIQUE NARRATIVE PER PROJECT: Every project MUST use a completely distinct opening and transition structure:
     * Project 1 (Architectural/Innovation Opening): "Arquitecturé una plataforma de optimización de CVs basada en la orquestación de LLMs y renderizado Typst..."
     * Project 2 (Problem/Business Opening): "Para resolver la falta de visibilidad del inventario en tiempo real, diseñé un sistema de monitoreo..."
     * Project 3 (Technical Integration Opening): "Mediante la integración de Playwright, FastAPI y SSE, automaticé las pruebas E2E..."
     * Project 4 (Metric/Performance Opening): "Reduje los tiempos de respuesta en 45% al implementar mecanismos de caché con Redis..."
   - NO REPEATED WORDS OR PHRASES: Ensure zero phrase overlap or repeated opening verbs between projects to achieve high human perplexity and burstiness.
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
        content = await call_llm_api(prompt)
        
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


        # Extract localized section headings from LLM output (fallback to English if missing)
        default_labels = {
            "summary": "Professional Summary",
            "education": "Education",
            "skills": "Skills",
            "experience": "Work Experience",
            "projects": "Projects",
            "achievements": "Achievements"
        }
        labels = {**default_labels, **parsed_data.get("section_labels", {})}

        yield f"data: {json.dumps({'step': 'Formatting Professional PDF', 'progress': 90})}\n\n"
        
        output_filename = f"tailored_resume_{int(time.time())}.pdf"
        output_path = os.path.join(OUTPUT_DIR, output_filename)
        
        use_rendercv = theme and theme != "classic_html"
        rendered = False
        if use_rendercv:
            try:
                print(f"[INFO] 🎨 Rendering PDF with RenderCV theme '{theme}' (fit_single_page={fit_single_page}, page_break_section={page_break_section})...")
                await asyncio.to_thread(
                    render_cv_with_rendercv, 
                    parsed_data, 
                    output_path, 
                    theme, 
                    fit_single_page, 
                    page_break_section
                )
                rendered = True
            except Exception as r_err:
                print(f"[WARN] ⚠️ RenderCV theme '{theme}' failed: {r_err}. Falling back to Playwright HTML renderer.")

        if not rendered:
            print(f"[INFO] 📄 Rendering PDF with Playwright HTML engine (page_break_section={page_break_section})...")
            template = Template(HTML_TEMPLATE)
            html_content = template.render(**parsed_data, labels=labels, page_break_section=page_break_section)
            
            def render_pdf_sync():
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.set_content(html_content)
                    page.pdf(path=output_path, prefer_css_page_size=True, print_background=True)
                    browser.close()

            await asyncio.to_thread(render_pdf_sync)

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
                audit_scores = await _run_internal_audit(output_path, jd=jd, custom_instructions=custom_instructions)
            except Exception as audit_err:
                print(f"[WARN] Auto re-audit failed: {audit_err}")
            translation_meta = {"source_language": source_language, "target_language": "en", "forced": True}

        yield f"data: {json.dumps({'step': 'Finished', 'progress': 100, 'download_url': f'/api/download/{output_filename}', 'audit_scores': audit_scores, 'translation': translation_meta})}\n\n"
        
    except Exception as e:
        import traceback
        print(f"[ERROR IN PIPELINE]: {e}")
        traceback.print_exc()
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


async def _run_internal_audit(pdf_path: str, jd: Optional[str], custom_instructions: Optional[str]) -> dict:
    """
    Re-invoke the ATS audit internally against the freshly rendered PDF.
    Reuses the same prompt body as POST /api/analyze-ats (lines ~988-1020).
    Returns the parsed dict (already with defensive defaults).
    """
    resume_text = extract_text(pdf_path)
    effective_jd = jd.strip() if (jd and jd.strip()) else (
        custom_instructions.strip() if (custom_instructions and custom_instructions.strip()) else
        "Optimización general y mejoramiento de calidad del CV"
    )
    prompt = f"""
You are an expert Applicant Tracking System (ATS) auditor and recruitment AI analyst (like CompuTrabajo, Workday, and Greenhouse ATS screeners).
Your task is to analyze the candidate's Base Resume against the target Job Description (JD) or General Professional Standards if no JD is provided.

Perform 3 comprehensive evaluations:
1. ATS MATCH SCORE (%): Calculate direct keyword and skill alignment between the Resume and Job Description/Professional Standards.
2. AI WRITING DETECTION SCORE (%): Analyze the writing style of the resume. Identify if it sounds natural/human or overly robotic/AI-generated (detect AI buzzwords like 'spearheaded revolutionary synergy', 'delved into', 'testament to', etc.). Provide a risk score (0-20% = Low AI Risk/Natural, 21-50% = Medium, 51-100% = High AI Risk) and advice to humanize the tone.
3. ATS FORMATTING & KEYWORD CHECK: Extract matched keywords, missing keywords, and actionable tips for ranking higher on platforms like CompuTrabajo.

STRICT INSTRUCTION: Detect the language of the Job Description/Resume (e.g. Spanish). Generate ALL feedback, tips, and verdicts strictly in that language.

Respond ONLY with a JSON object in this exact structure:
{{
  "ats_score": 85,
  "match_level": "Alto",
  "matched_keywords": ["Python", "FastAPI", "React", "SQL"],
  "missing_keywords": ["Docker", "Pytest", "CI/CD"],
  "ai_detection_score": 15,
  "ai_tone_verdict": "Bajo Riesgo de IA - Redacción Humana y Natural",
  "ai_humanize_tips": ["El lenguaje es directo, conciso y fácil de leer por reclutadores."],
  "ats_formatting_score": 95,
  "actionable_tips": [
    "Añade la palabra clave 'Docker' si posees conocimientos en contenedores.",
    "Destaca métricas de rendimiento en tus experiencias clave."
  ]
}}

Base Resume:
{resume_text}

Job Description / Requirements:
{effective_jd}
"""
    content = await call_llm_api(prompt)

    clean_content = content.strip()
    if "```" in clean_content:
        import re as _re
        match = _re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
        if match:
            clean_content = match.group(1)

    try:
        parsed = json.loads(clean_content)
    except Exception:
        parsed = json.loads(content)

    if isinstance(parsed, list) and len(parsed) > 0:
        parsed = parsed[0]

    if not isinstance(parsed, dict):
        raise ValueError("Internal audit response was not a dict")

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
    force_language: Optional[str] = Form(None)
):
    # Validate force_language early so unsupported values are rejected with HTTP 422
    # before any upload work or LLM call happens.
    if force_language is not None and force_language not in {"en"}:
        raise HTTPException(
            status_code=422,
            detail=f"force_language must be 'en' or omitted, got {force_language!r}"
        )

    # Save the original uploaded file temporarily (used as fallback if no base_resume_filename)
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, file.filename)
    with open(file_path, "wb") as f:
         f.write(await file.read())

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
        ),
        media_type="text/event-stream"
    )


@app.post("/api/analyze-ats")
async def analyze_ats(
    file: UploadFile,
    jd: Optional[str] = Form(None)
):
    try:
        load_dotenv(override=True)
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        resume_text = extract_text(file_path)
        
        effective_jd = jd.strip() if (jd and jd.strip()) else "Optimización general y mejoramiento de calidad del CV"
        
        prompt = f"""
You are an expert Applicant Tracking System (ATS) auditor and recruitment AI analyst (like CompuTrabajo, Workday, and Greenhouse ATS screeners).
Your task is to analyze the candidate's Base Resume against the target Job Description (JD) or General Professional Standards if no JD is provided.

Perform 3 comprehensive evaluations:
1. ATS MATCH SCORE (%): Calculate direct keyword and skill alignment between the Resume and Job Description/Professional Standards.
2. AI WRITING DETECTION SCORE (%): Analyze the writing style of the resume. Identify if it sounds natural/human or overly robotic/AI-generated (detect AI buzzwords like 'spearheaded revolutionary synergy', 'delved into', 'testament to', etc.). Provide a risk score (0-20% = Low AI Risk/Natural, 21-50% = Medium, 51-100% = High AI Risk) and advice to humanize the tone.
3. ATS FORMATTING & KEYWORD CHECK: Extract matched keywords, missing keywords, and actionable tips for ranking higher on platforms like CompuTrabajo.

STRICT INSTRUCTION: Detect the language of the Job Description/Resume (e.g. Spanish). Generate ALL feedback, tips, and verdicts strictly in that language.

Respond ONLY with a JSON object in this exact structure:
{{
  "ats_score": 85,
  "match_level": "Alto",
  "matched_keywords": ["Python", "FastAPI", "React", "SQL"],
  "missing_keywords": ["Docker", "Pytest", "CI/CD"],
  "ai_detection_score": 15,
  "ai_tone_verdict": "Bajo Riesgo de IA - Redacción Humana y Natural",
  "ai_humanize_tips": ["El lenguaje es directo, conciso y fácil de leer por reclutadores."],
  "ats_formatting_score": 95,
  "actionable_tips": [
    "Añade la palabra clave 'Docker' si posees conocimientos en contenedores.",
    "Destaca métricas de rendimiento en tus experiencias clave."
  ]
}}

Base Resume:
{resume_text}

Job Description / Requirements:
{effective_jd}
"""
        content = await call_llm_api(prompt)
        
        clean_content = content.strip()
        if "```" in clean_content:
            import re
            match = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", clean_content)
            if match:
                clean_content = match.group(1)

        try:
            parsed = json.loads(clean_content)
        except Exception:
            parsed = json.loads(content)
            
        if isinstance(parsed, list) and len(parsed) > 0:
            parsed = parsed[0]
            
        return parsed
    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"error": str(e)}

@app.get("/api/download/{filename}")
async def download_resume(filename: str):
    file_path = os.path.join(OUTPUT_DIR, filename)
    if os.path.exists(file_path):
        return FileResponse(file_path, filename=filename, media_type="application/pdf")
    return {"error": "File not found"}

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
        return {"status": "ok", "deleted_files": deleted_count, "message": "Cache y CVs generados eliminados correctamente."}
    except Exception as e:
        return {"status": "error", "error": str(e)}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)


