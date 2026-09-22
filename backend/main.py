import os
import json
import asyncio
from typing import Optional
from fastapi import FastAPI, UploadFile, Form, BackgroundTasks
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import fitz  # PyMuPDF
import google.generativeai as genai
from jinja2 import Template
from playwright.sync_api import sync_playwright
import tempfile
import time

from dotenv import load_dotenv
from render_service import render_cv_with_rendercv

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
    {% if portfolio %}{% set _ = items.append('<a href="' ~ portfolio ~ '">Portfolio</a>') %}{% endif %}
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
            {% if proj.github_url %} | <a href="{{ proj.github_url }}" style="color:#000;text-decoration:none;font-size:9.5pt;">{{ proj.github_url }}</a>{% endif %}
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
    return " ".join([page.get_text() for page in doc])

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



async def generation_pipeline(
    file_path: str, 
    jd: Optional[str] = None, 
    target_role: Optional[str] = None, 
    github_url: Optional[str] = None, 
    linkedin_url: Optional[str] = None, 
    custom_instructions: Optional[str] = None, 
    base_resume_filename: Optional[str] = None, 
    theme: Optional[str] = "sb2nov",
    fit_single_page: bool = False,
    page_break_section: Optional[str] = None,
    extract_linkedin_info: bool = False
):
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

        yield f"data: {json.dumps({'step': 'Extracting Text from Resume', 'progress': 20})}\n\n"
        resume_text = extract_text(effective_file_path)

        linkedin_extracted_text = ""
        if extract_linkedin_info and linkedin_url and linkedin_url.strip():
            yield f"data: {json.dumps({'step': 'Extrayendo datos del perfil de LinkedIn...', 'progress': 35})}\n\n"
            linkedin_extracted_text = await extract_linkedin_profile_data(linkedin_url.strip())
        
        yield f"data: {json.dumps({'step': 'Analyzing with AI Model', 'progress': 50})}\n\n"
        
        prompt = f"""
You are a professional technical recruiter and resume writer specialized in ATS optimization.
You are provided with a 'Base Resume' of a candidate and a target 'Job Description' (JD).
Your goal is to tailor the candidate's actual experience to align perfectly with the target role and achieve maximum ATS scores on platforms like CompuTrabajo, Workday, LinkedIn, and Greenhouse.

STRICT RULES (CRITICAL — ALL MUST BE FOLLOWED):
1. ZERO HALLUCINATION & NO INVENTING DATA: You MUST ONLY use the candidate's real experiences, companies, education, degrees, dates, and projects provided in the 'Base Resume' and the 'Extracted LinkedIn Profile Data' (if provided). Absolutely DO NOT invent, hallucinate, or import fake or third-party companies, internships, jobs, dates, or projects (e.g. DO NOT add ZScore, Hackumi, Resume Analyzer, or any experience not in the Base Resume or LinkedIn data).
2. TAILOR AND RESTRUCTURE ONLY: Rephrase, reorganize, merge, and emphasize the candidate's real existing achievements, skills, and experience from the Base Resume and extracted LinkedIn profile using strong action verbs and relevant keywords from the Job Description.
3. TARGET ROLE ALIGNMENT: Frame the summary and highlights toward the 'Target Role' if provided. The professional summary MUST include the exact target job title when possible.
4. STRICT 1-PAGE LAYOUT & ANTI-ORPHAN COMPACTNESS:
   - Provide 2 to 3 concise, punchy bullet points per role (do not exceed 3 unless essential).
   - Ensure bullet points are self-contained and max 1 to 2 lines each so they never spill solitary orphan lines onto a next page.
   - Keep the professional summary to 2-3 focused lines.
5. LANGUAGE MATCHING (CRITICAL): Detect the dominant language of the Job Description. Generate ALL text content (summary, bullet points, skill categories, achievements) in THAT SAME language. If the JD is in English → output everything in English. If the JD is in Spanish → output everything in Spanish. Default to the JD language; never mix languages in the same document. Also output the correct localized 'section_labels' accordingly.
6. ATS KEYWORD DENSITY: Naturally integrate the most important technical keywords, tools, and soft-skill terms from the Job Description into the bullet points and summary. Prioritize exact-match keywords over synonyms when possible (e.g. if JD says 'React.js' use 'React.js', not just 'React').
7. STRONG ACTION VERBS: Every bullet point MUST start with a powerful, past-tense action verb (e.g. Desarrollé, Optimicé, Implementé, Lideré, Diseñé, Automaticé, Reduje, Incrementé, Escalé, Migré, Construí, Configuré, Integré). Avoid passive voice and weak starters like 'Responsible for' or 'Helped with'.
8. QUANTIFIABLE METRICS: Include specific numbers, percentages, dollar amounts, or time savings wherever the Base Resume hints at them (e.g. 'Optimicé consultas SQL reduciendo tiempos de respuesta en un 40%', 'Automaticé 15 flujos de trabajo'). If exact numbers are unknown, use plausible specific estimates based on context.
9. ATS FORMATTING COMPLIANCE: The output data must produce a clean, single-column, ATS-parseable layout. Do NOT include tables, graphics, columns, text boxes, headers/footers with contact info, or special characters that confuse ATS parsers. Use standard section names that ATS systems recognize (Experience, Education, Skills, Projects).
10. DOMAIN-AWARE INTELLIGENT SKILLS CATEGORIZATION:
   - Categorize skills strictly according to the candidate's actual profession/domain and the target role:
     * For Psychology / HR / Talent Acquisition / Recruiting: Group into categories such as 'Pruebas Psicotécnicas & Evaluación', 'Metodologías de Selección & Entrevista', 'Legislación Laboral & Contratación', 'Sistemas ATS & Portales de Empleo', 'Gestión del Talento'.
     * For Software / Engineering / Tech: Group into 'Lenguajes de Programación', 'Frameworks & Librerías', 'Bases de Datos & Cloud', 'Herramientas & DevOps'.
     * For Business / Finance / Administration: Group into 'Finanzas & Análisis', 'Herramientas ERP/CRM', 'Gestión de Proyectos', 'Normativa & Auditoría'.
   - NEVER force tech/developer categories onto a non-tech profile (e.g. NEVER put 'Programming Languages' in a psychology resume).
11. CANDIDATE LOCATION (CRITICAL FOR ATS):
   - Extract the candidate's city and country (e.g. 'Medellín, Colombia' or 'Bogotá, D.C.') from the Base Resume if present, and output it in the 'location' field.
12. PHONE NUMBER WITH COUNTRY CODE (CRITICAL):
   - Always output the phone number with its international dialing prefix (e.g. '+57 300 123 4567' for Colombia, '+1 555 123 4567' for USA). If the Base Resume contains a Colombian number without +57, prepend +57. Never strip the country code.
13. PROJECTS WITH LINKS:
   - Each project entry may include an optional 'url' field (live demo or website URL) and/or an optional 'github_url' field (GitHub repository URL). Preserve these links exactly as found in the Base Resume. If not present, omit the field or set it to empty string.
"""
        if custom_instructions and custom_instructions.strip():
            prompt += f"12. USER REFINEMENT FEEDBACK & SELECTED TIPS (HIGHEST PRIORITY): You MUST explicitly apply the following user-selected improvements, tone humanization tips, and custom instructions above all other defaults: {custom_instructions.strip()}\n"

        prompt += f"""
Target Role: {target_role if target_role else 'Not specified'}
GitHub: {github_url if github_url else ''}
LinkedIn: {linkedin_url if linkedin_url else ''}
Portfolio: ''

Base Resume:
{resume_text}
"""
        if linkedin_extracted_text:
            prompt += f"""
Extracted LinkedIn Profile Data (Use to enrich and complement the Base Resume):
{linkedin_extracted_text}
"""

        effective_jd = jd.strip() if (jd and jd.strip()) else "No se especificó una oferta de trabajo concreta. Realizar optimización profesional general para ATS, destacando logros y competencias clave."

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
  "experience": [{"company": "Empresa Ejemplo", "role": "Analista de Selección", "dates": "Ene 2023 - Presente", "points": ["Lideré procesos de selección...", "Evalué candidatos mediante..."]}],
  "projects": [{"name": "Project Name", "dates": "2025-01", "url": "", "github_url": "https://github.com/user/repo", "points": ["Built X using Y..."]}],
  "achievements": [],
  "section_labels": {
    "summary": "Professional Summary",
    "education": "Education",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "achievements": "Achievements"
  }
}
IMPORTANT:
1. All dates in 'dates' fields (education, experience, projects) MUST be formatted using standard numbers or 'present' (e.g. "2019-02 - 2023-08", "2023-02 - present", or "2019 - 2023"). Do NOT use month abbreviations in Spanish (like 'Feb', 'Ago', 'Ene') or Spanish words like 'Presente' in the date strings.
2. If the JD is in Spanish, the section_labels values must be in Spanish (e.g. 'Resumen Profesional', 'Educación', 'Habilidades', 'Experiencia Laboral', 'Proyectos', 'Logros'). If the JD is in English, they must be in English as shown above.
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
        # User input overrides if provided
        if github_url and github_url.strip():
            parsed_data["github"] = github_url.strip()
        elif not github_url:
            # Check if LLM generated dummy or empty github
            gh_val = str(parsed_data.get("github", "")).strip()
            if not gh_val or any(dummy in gh_val.lower() for dummy in ["github.com/janedoe", "github.com/...", "example", "none"]):
                parsed_data["github"] = ""

        if linkedin_url and linkedin_url.strip():
            parsed_data["linkedin"] = linkedin_url.strip()
        elif not linkedin_url:
            li_val = str(parsed_data.get("linkedin", "")).strip()
            if not li_val or any(dummy in li_val.lower() for dummy in ["linkedin.com/in/janedoe", "linkedin.com/in/...", "example", "none"]):
                parsed_data["linkedin"] = ""

        port_val = str(parsed_data.get("portfolio", "")).strip()
        if not port_val or any(dummy in port_val.lower() for dummy in ["janedoe.com", "example.com", "none"]):
            parsed_data["portfolio"] = ""


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
            
        yield f"data: {json.dumps({'step': 'Finished', 'progress': 100, 'download_url': f'/api/download/{output_filename}'})}\n\n"
        
    except Exception as e:
        import traceback
        print(f"[ERROR IN PIPELINE]: {e}")
        traceback.print_exc()
        yield f"data: {json.dumps({'error': str(e)})}\n\n"

@app.post("/api/generate")
async def generate_resume(
    file: UploadFile, 
    jd: Optional[str] = Form(None),
    target_role: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(None),
    base_resume_filename: Optional[str] = Form(None),
    theme: Optional[str] = Form("sb2nov"),
    fit_single_page: Optional[bool] = Form(False),
    page_break_section: Optional[str] = Form(None),
    extract_linkedin_info: Optional[bool] = Form(False)
):
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
            custom_instructions, 
            base_resume_filename, 
            theme,
            fit_single_page or False,
            page_break_section,
            extract_linkedin_info or False
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

