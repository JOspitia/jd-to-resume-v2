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
  
  h2 { font-size: 12pt; font-weight: bold; text-transform: uppercase; border-bottom: 1px solid black; padding-bottom: 2px; margin-top: 12px; margin-bottom: 6px; color: #000; }
  
  p { margin: 0 0 4px 0; }
  ul { margin: 0 0 8px 0; padding-left: 20px; }
  li { margin-bottom: 2px; }
  
  .flex-container { display: flex; justify-content: space-between; align-items: baseline; }
  
  .item-title { font-weight: bold; }
  .item-subtitle { font-style: italic; }
  .item-right { text-align: right; }
  
  .skills-list { margin: 0 0 8px 0; }
</style>
</head>
<body>
  <h1>{{ name }}</h1>
  <div class="contact-info">
    {{ phone }} | {{ email }} | <a href="{{ portfolio }}">Portfolio</a> | <a href="{{ linkedin }}">LinkedIn</a> | <a href="{{ github }}">GitHub</a>
  </div>
  
  {% if summary %}
  <h2>{{ labels.summary }}</h2>
  <p>{{ summary }}</p>
  {% endif %}
  
  {% if education and education|length > 0 %}
  <h2>{{ labels.education }}</h2>
  {% for ed in education %}
    <div class="flex-container">
      <div><span class="item-title">{{ ed.school }}</span></div>
      <div class="item-right">{{ ed.dates }}</div>
    </div>
    <div class="flex-container">
      <div><span class="item-subtitle">{{ ed.degree }}</span>{% if ed.gpa %} (GPA: {{ ed.gpa }}){% endif %}</div>
      <div class="item-right"></div>
    </div>
  {% endfor %}
  {% endif %}
  
  {% if skills and skills|length > 0 %}
  <h2>{{ labels.skills }}</h2>
  <div class="skills-list">
    {% for skill in skills %}
      <span class="item-title">{{ skill.category }}:</span> {{ skill['items']|join(', ') }}<br>
    {% endfor %}
  </div>
  {% endif %}
  
  {% if experience and experience|length > 0 %}
  <h2>{{ labels.experience }}</h2>
  {% for exp in experience %}
    <div class="flex-container">
      <div><span class="item-title">{{ exp.role }}</span> | <span class="item-subtitle">{{ exp.company }}</span></div>
      <div class="item-right">{{ exp.dates }}</div>
    </div>
    <ul>
      {% for point in exp.points %}
        <li>{{ point }}</li>
      {% endfor %}
    </ul>
  {% endfor %}
  {% endif %}

  {% if projects and projects|length > 0 %}
  <h2>{{ labels.projects }}</h2>
  {% for proj in projects %}
    <div class="flex-container">
      <div><span class="item-title">{{ proj.name }}</span></div>
      <div class="item-right">{{ proj.dates }}</div>
    </div>
    <ul>
      {% for point in proj.points %}
        <li>{{ point }}</li>
      {% endfor %}
    </ul>
  {% endfor %}
  {% endif %}

  {% if achievements and achievements|length > 0 %}
  <h2>{{ labels.achievements }}</h2>
  <ul>
    {% for ach in achievements %}
      <li>{{ ach }}</li>
    {% endfor %}
  </ul>
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
    projects: list[dict] = Field(description="List of dicts with: name, dates, points (list)")
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
            # Set explicit 25s timeout on HTTP client to avoid hanging indefinitely if network stalls
            client = OpenAI(api_key=api_key, base_url=base_url, timeout=25.0)
            
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
                
            return await asyncio.wait_for(asyncio.to_thread(_run_openai), timeout=30.0)
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
    
    models_to_try = ['gemini-1.5-flash', 'gemini-1.5-pro']
    last_err = None
    
    for m_name in models_to_try:
        try:
            print(f"[LLM INFO] Intentando modelo Gemini de respaldo: '{m_name}'...")
            model = genai.GenerativeModel(m_name, generation_config=generation_config)
            res = await asyncio.wait_for(asyncio.to_thread(model.generate_content, prompt_text), timeout=30.0)
            if res and res.text:
                return res.text
        except Exception as e:
            print(f"[LLM WARN] El modelo Gemini '{m_name}' falló/agotó tiempo: {e}")
            last_err = e
            continue
            
    err_detail = f" (Error primario: {primary_error_msg})" if primary_error_msg else ""
    raise ValueError(f"Fallaron todos los modelos. Gemini: {last_err}{err_detail}")


async def generation_pipeline(file_path: str, jd: str, target_role: Optional[str] = None, github_url: Optional[str] = None, linkedin_url: Optional[str] = None, custom_instructions: Optional[str] = None, base_resume_filename: Optional[str] = None, theme: Optional[str] = "sb2nov"):
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

        yield f"data: {json.dumps({'step': 'Extracting Text from Resume', 'progress': 25})}\n\n"
        resume_text = extract_text(effective_file_path)
        
        yield f"data: {json.dumps({'step': 'Analyzing with AI Model', 'progress': 50})}\n\n"
        
        prompt = f"""
You are a professional technical recruiter and resume writer specialized in ATS optimization.
You are provided with a 'Base Resume' of a candidate and a target 'Job Description' (JD).
Your goal is to tailor the candidate's actual experience to align perfectly with the target role and achieve maximum ATS scores on platforms like CompuTrabajo, Workday, LinkedIn, and Greenhouse.

STRICT RULES (CRITICAL — ALL MUST BE FOLLOWED):
1. ZERO HALLUCINATION & NO INVENTING DATA: You MUST ONLY use the candidate's real experiences, companies, education, degrees, dates, and projects provided in the 'Base Resume'. Absolutely DO NOT invent, hallucinate, or import fake or third-party companies, internships, jobs, dates, or projects (e.g. DO NOT add ZScore, Hackumi, Resume Analyzer, or any experience not in the Base Resume).
2. TAILOR AND RESTRUCTURE ONLY: Rephrase, reorganize, and emphasize the candidate's real existing achievements and technical skills using strong action verbs and relevant keywords from the Job Description.
3. TARGET ROLE ALIGNMENT: Frame the summary and highlights toward the 'Target Role' if provided. The professional summary MUST include the exact target job title when possible.
4. STRICT 1-PAGE LAYOUT: Keep all descriptions concise (max 3-4 high-impact bullet points per role) so the resulting resume strictly fits on a single US Letter page.
5. LANGUAGE MATCHING (CRITICAL): Detect the dominant language of the Job Description. Generate ALL text content (summary, bullet points, skill categories, achievements) in THAT SAME language. If the JD is in English → output everything in English. If the JD is in Spanish → output everything in Spanish. Default to the JD language; never mix languages in the same document. Also output the correct localized 'section_labels' accordingly.
6. ATS KEYWORD DENSITY: Naturally integrate the most important technical keywords, tools, and soft-skill terms from the Job Description into the bullet points and summary. Prioritize exact-match keywords over synonyms when possible (e.g. if JD says 'React.js' use 'React.js', not just 'React').
7. STRONG ACTION VERBS: Every bullet point MUST start with a powerful, past-tense action verb (e.g. Desarrollé, Optimicé, Implementé, Lideré, Diseñé, Automaticé, Reduje, Incrementé, Escalé, Migré, Construí, Configuré, Integré). Avoid passive voice and weak starters like 'Responsible for' or 'Helped with'.
8. QUANTIFIABLE METRICS: Include specific numbers, percentages, dollar amounts, or time savings wherever the Base Resume hints at them (e.g. 'Optimicé consultas SQL reduciendo tiempos de respuesta en un 40%', 'Automaticé 15 flujos de trabajo'). If exact numbers are unknown, use plausible specific estimates based on context.
9. ATS FORMATTING COMPLIANCE: The output data must produce a clean, single-column, ATS-parseable layout. Do NOT include tables, graphics, columns, text boxes, headers/footers with contact info, or special characters that confuse ATS parsers. Use standard section names that ATS systems recognize (Experience, Education, Skills, Projects).
10. SKILLS CATEGORIZATION: Group skills into clear, ATS-friendly categories matching the JD requirements (e.g. 'Lenguajes de Programación', 'Frameworks & Librerías', 'Bases de Datos', 'DevOps & Cloud', 'Herramientas'). Include all skills from JD that the candidate demonstrably has.
"""
        if custom_instructions and custom_instructions.strip():
            prompt += f"11. USER REFINEMENT FEEDBACK & SELECTED TIPS (HIGHEST PRIORITY): You MUST explicitly apply the following user-selected improvements, tone humanization tips, and custom instructions above all other defaults: {custom_instructions.strip()}\n"

        prompt += f"""
Target Role: {target_role if target_role else 'Not specified'}
GitHub: {github_url if github_url else ''}
LinkedIn: {linkedin_url if linkedin_url else ''}
Portfolio: ''

Base Resume:
{resume_text}

Job Description:
{jd}
"""
        
        generation_config = {"response_mime_type": "application/json"}
        prompt += """
Respond ONLY with a JSON object in this exact structure. The 'section_labels' field MUST contain the localized section headings in the SAME language as the Job Description:
{
  "name": "Jane Doe",
  "phone": "555-1234",
  "email": "jane@example.com",
  "portfolio": "https://janedoe.com",
  "linkedin": "https://linkedin.com/in/janedoe",
  "github": "https://github.com/janedoe",
  "summary": "Concise 2-line summary tailored to JD...",
  "education": [{"school": "University of Tech", "degree": "B.S. in Computer Science", "dates": "2018 - 2022", "gpa": "3.8"}],
  "skills": [{"category": "Languages", "items": ["Python", "JavaScript"]}],
  "experience": [{"company": "Acme Corp", "role": "Software Engineer", "dates": "Jan 2023 - Present", "points": ["Shipped API...", "Optimized DB..."]}],
  "projects": [{"name": "AI Tool", "dates": "Fall 2023", "points": ["Built cool thing using X", "Improved Y by Z%"]}],
  "achievements": ["Won Hackathon X", "Published paper Y"],
  "section_labels": {
    "summary": "Professional Summary",
    "education": "Education",
    "skills": "Skills",
    "experience": "Work Experience",
    "projects": "Projects",
    "achievements": "Achievements"
  }
}
IMPORTANT: If the JD is in Spanish, the section_labels values must be in Spanish (e.g. 'Resumen Profesional', 'Educación', 'Habilidades', 'Experiencia Laboral', 'Proyectos', 'Logros'). If the JD is in English, they must be in English as shown above.
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
            "name": "", "phone": "", "email": "", "portfolio": "", "linkedin": "", "github": "",
            "summary": "", "education": [], "skills": [], "experience": [], "projects": [], "achievements": [],
            "section_labels": {}
        }
        for k, v in defaults.items():
            if k not in parsed_data or parsed_data[k] is None:
                parsed_data[k] = v

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
                print(f"[INFO] 🎨 Rendering PDF with RenderCV theme '{theme}'...")
                await asyncio.to_thread(render_cv_with_rendercv, parsed_data, output_path, theme)
                rendered = True
            except Exception as r_err:
                print(f"[WARN] ⚠️ RenderCV theme '{theme}' failed: {r_err}. Falling back to Playwright HTML renderer.")

        if not rendered:
            print("[INFO] 📄 Rendering PDF with Playwright HTML engine...")
            template = Template(HTML_TEMPLATE)
            html_content = template.render(**parsed_data, labels=labels)
            
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
    jd: str = Form(...),
    target_role: Optional[str] = Form(None),
    github_url: Optional[str] = Form(None),
    linkedin_url: Optional[str] = Form(None),
    custom_instructions: Optional[str] = Form(None),
    base_resume_filename: Optional[str] = Form(None),
    theme: Optional[str] = Form("sb2nov")
):
    # Save the original uploaded file temporarily (used as fallback if no base_resume_filename)
    temp_dir = tempfile.gettempdir()
    file_path = os.path.join(temp_dir, file.filename)
    with open(file_path, "wb") as f:
         f.write(await file.read())
         
    return StreamingResponse(
        generation_pipeline(file_path, jd, target_role, github_url, linkedin_url, custom_instructions, base_resume_filename, theme),
        media_type="text/event-stream"
    )

@app.post("/api/analyze-ats")
async def analyze_ats(
    file: UploadFile,
    jd: str = Form(...)
):
    try:
        load_dotenv(override=True)
        temp_dir = tempfile.gettempdir()
        file_path = os.path.join(temp_dir, file.filename)
        with open(file_path, "wb") as f:
            f.write(await file.read())
            
        resume_text = extract_text(file_path)
        
        prompt = f"""
You are an expert Applicant Tracking System (ATS) auditor and recruitment AI analyst (like CompuTrabajo, Workday, and Greenhouse ATS screeners).
Your task is to analyze the candidate's Base Resume against the target Job Description (JD).

Perform 3 comprehensive evaluations:
1. ATS MATCH SCORE (%): Calculate direct keyword and skill alignment between the Resume and Job Description.
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

Job Description:
{jd}
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
