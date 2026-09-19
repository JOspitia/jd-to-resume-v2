# Resume Tailor AI v2.5 — Adaptador ATS multilingüe con RenderCV + Iteración

<div align="center">

[![React](https://img.shields.io/badge/Frontend-React_19_+_Vite_+_Tailwind-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![shadcn/ui](https://img.shields.io/badge/UI-shadcn--ui_new--york_+_Radix-000?logo=shadcnui)](https://ui.shadcn.com/)
[![FastAPI](https://img.shields.io/badge/Backend-FastAPI_+_Python-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![RenderCV](https://img.shields.io/badge/PDF-RenderCV_+_Typst-0055FF?logo=python&logoColor=white)](https://github.com/sinaatalay/rendercv)
[![Multi-LLM](https://img.shields.io/badge/AI-DeepSeek_%7C_OpenAI_%7C_Gemini-FF5E00)](https://aistudio.google.com/)

**Sube tu CV base + la descripción de la vacante y la IA reescribe, reorganiza y re-empaqueta tu trayectoria real en un PDF vectorial ATS-friendly, auditable e iterativo.**

[Arquitectura](#arquitectura) · [Features](#features) · [Pipeline](#pipeline-de-generacion) · [API](#endpoints) · [Setup](#instalacion-y-configuracion) · [Variables .env](#variables-de-entorno)

</div>

---

## Qué es

`jd-to-resume` es una plataforma full-stack que **no inventa experiencia**: toma tu CV real (PDF) más la descripción de una vacante y produce un PDF nuevo, reestructurado, con palabras clave alineadas a la JD y un puntaje ATS verificable. Funciona con tres motores de LLM en cadena (proveedor primario OpenAI-compatible → fallback Gemini multi-modelo), cuatro plantillas tipográficas vectoriales y un ciclo de refinamiento preservando el último PDF generado como base.

El frontend es una SPA con shadcn/ui (estilo new-york) sobre Radix, decorada con una capa *neo-brutalist* (`rm-box` / `rm-btn` con sombra dura 4×4). Tiene dos vistas: una landing pública y la herramienta (ToolApp) donde ocurre todo el flujo.

---

## Features

### 1. Tres motores LLM en cadena
- **Primario (OpenAI-compatible).** Si defines `LLM_PROVIDER=openai_compatible|deepseek|minimax|kimi|moonshot|openrouter|groq` más `LLM_API_KEY`/`LLM_BASE_URL`, el backend lo usa primero con timeout de 45 s.
- **Fallback automático a Gemini.** Si el primario falla o expira, pasa a `genai` y prueba `gemini-2.0-flash` → `gemini-1.5-flash` → `gemini-1.5-pro`.
- **Parsing tolerante.** Si la IA envuelve la respuesta en ` ```json `, se limpia antes de `json.loads`. Si no es `dict`, intenta tomar el primer elemento de una lista. Defaults defensivos para todas las claves esperadas.

### 2. PDF vectorial: RenderCV + Typst (con fallback)
- Tres temas soportados: **`sb2nov`** (estándar Silicon Valley), **`classic`** y **`moderncv`**. Más un cuarto modo **`classic_html`** que salta RenderCV y renderiza directo con Jinja2 + Playwright.
- Cuando `theme != "classic_html"` y el theme es válido (`sb2nov|classic|moderncv`), se compila con `rendercv.renderer.typst.generate_typst` → `rendercv.renderer.pdf_png.generate_pdf`.
- Si RenderCV falla, cae automáticamente a `Jinja2` + `Playwright` con el template HTML embebido en `main.py` (modo "Classic HTML"). Nunca dejas al usuario sin PDF.
- **Anti-orfanos.** `allow_page_break: false` en entries, espaciados estrictos (`space_between_items: 0.1em`, `space_above: 0.1em`) y `orphans/widows: 3` en CSS del fallback HTML.
- **Modo 1-página.** `fit_single_page=true` reduce márgenes a `0.45 in` y `line_spacing` a `0.45em`.
- **Salto de página manual.** `page_break_section` inyecta `#pagebreak()` en el `.typst` antes de la sección indicada.

### 3. Adaptación sin alucinación
- Prompt estricto: solo usa empresas, cargos, fechas y proyectos del CV base + LinkedIn extraído. Prohibido inventar (lista explícita en el system prompt).
- **Verbos de acción + métricas cuantitativas** en cada bullet.
- **Detección de idioma del JD.** Todo el contenido (resumen, viñetas, *achievements*, etiquetas de sección) sale en el idioma detectado. Meses en español (`Ene 2019 – Ago 2023`) se normalizan a `YYYY-MM` para RenderCV.
- **Categorización de skills por dominio.** El prompt obliga categorías distintas:
  - Psicología / HR / Recruiting → *Pruebas Psicotécnicas, Metodologías de Selección, Legislación Laboral…*
  - Software / Tech → *Lenguajes, Frameworks, Bases de Datos & Cloud…*
  - Business / Finanzas → *Finanzas & Análisis, ERP/CRM, Gestión de Proyectos…*
  Nunca se fuerza un set tech sobre un perfil no-tech.
- **Localización de títulos de sección.** El LLM devuelve `section_labels` (ES/EN); el render los usa.

### 4. Enriquecimiento con LinkedIn
Tres rutas, en cascada y con cache en memoria (`_linkedin_cache: dict`):
1. **API externa** (`LINKEDIN_API_URL` + `LINKEDIN_API_KEY`, ej. ProxyCurl). GET con header Bearer.
2. **Playwright autenticado** (`LINKEDIN_EMAIL` + `LINKEDIN_PASSWORD`). Login con selectores múltiples, scroll de la página para lazy-load, extractor JS que devuelve `{name, headline, location, about, experiences, education, skills, certifications, languages}`. Si LinkedIn devuelve `checkpoint` / 2FA, aborta y cae al paso 3.
3. **Público anónimo.** `urllib` con User-Agent Chrome + extracción de `og:description`, JSON-LD estructurado y resumen por LLM.

Tras el scrape, el LLM normaliza el HTML sucio a Markdown estructurado y se inyecta al prompt como `Extracted LinkedIn Profile Data`.

### 5. Auditoría ATS & detector de tono IA
Endpoint independiente `/api/analyze-ats`: no genera PDF, **solo audita**. Devuelve:
- `ats_score` (0–100) + `match_level`.
- `matched_keywords` y `missing_keywords` vs la JD.
- `ai_detection_score` con baremo 0–20 bajo, 21–50 medio, 51–100 alto y tips de humanización.
- `ats_formatting_score` (parseabilidad) y `actionable_tips` (ej. *"Añade 'Docker' si posees conocimientos en contenedores"*).

En el frontend, si `autoValidateATS` está activo, después de generar se llama automáticamente. Los resultados alimentan el historial `scoreHistory` (ATS / AI / Format por versión).

### 6. Refinamiento iterativo
- Cada generación guarda `tailored_resume_<timestamp>.pdf` en `backend/output/`.
- La siguiente iteración envía `base_resume_filename` y el backend toma ese PDF como input (`extract_text` con PyMuPDF). **No se parte del CV original cada vez**; se preservan las mejoras acumuladas.
- El usuario puede marcar `selectedTips`, `selectedKeywords` y escribir `customPrompt` antes de re-generar. Esos viajan como `selected_tips`/`custom_instructions` y se inyectan al prompt con prioridad sobre las reglas por defecto.
- Versión se incrementa en frontend (`generationVersionRef`) para graficar la evolución (ATS sube, AI baja).

### 7. UX con progreso en vivo
- `/api/generate` devuelve `StreamingResponse(media_type="text/event-stream")`. Cada yield es `data: {"step": "...", "progress": N}\n\n`.
- Pasos reportados: `Validating Input` (10) → `Extracting Text from Resume` (20) → opcional `Extrayendo datos del perfil de LinkedIn…` (35) → `Analyzing with AI Model` (50) → `Generating Tailored Resume Content` (75) → `Formatting Professional PDF` (90) → `Finished` (100, con `download_url`).
- Timer en segundos en la UI hasta 60 s.

---

## Arquitectura

```mermaid
flowchart TD
  A[CV PDF + JD + opcional LinkedIn/GitHub] --> B[ToolApp.tsx · React 19]
  B -->|POST /api/generate| C[FastAPI · main.py]
  C --> D[PyMuPDF extract_text]
  D --> E{¿extract_linkedin_info?}
  E -->|sí| F[3 rutas LinkedIn con _linkedin_cache]
  E -->|no| G[Skip]
  F --> H[LLM call_llm_api]
  G --> H
  H --> I{¿LLM_PROVIDER?}
  I -->|deepseek / openai_compatible| J[OpenAI client 45s]
  J -->|fallo| K[Gemini cascade]
  I -->|gemini| K
  K --> L[Gemini: 2.0-flash → 1.5-flash → 1.5-pro]
  L --> M[JSON parse + defaults defensivos]
  M --> N{¿theme?}
  N -->|sb2nov|classic|moderncv| O[RenderCV + Typst]
  O -->|fallo| P[Jinja2 + Playwright HTML]
  N -->|classic_html| P
  O --> Q[backend/output/tailored_resume_*.pdf]
  P --> Q
  Q --> R[GET /api/download/<filename>]
  R --> B

  B -.auditoría.-> S[POST /api/analyze-ats]
  S --> H

  B -.reset.-> T[POST /api/clear-cache]
  T --> Q
```

---

## Pipeline de generación

Resumen de lo que pasa cuando presionas **Generar**:

1. **Upload & persistencia.** El PDF se guarda temporalmente; si el frontend envía `base_resume_filename`, el backend prefiere ese archivo en `output/` (refinamiento).
2. **Extracción de texto.** `pymupdf` (`fitz.open()` + `page.get_text()` joined).
3. **(Opcional) LinkedIn.** Si `extract_linkedin_info=true`, se ejecuta el extractor y se concatena al prompt como bloque "Extracted LinkedIn Profile Data".
4. **LLM con system prompt estricto.** Estructura JSON esperada: `name, location, phone, email, portfolio, linkedin, github, summary, education, skills, experience, projects, achievements, section_labels`.
5. **Post-procesado.**
   - Defaults para claves faltantes.
   - Limpieza de placeholders (`github.com/janedoe`, `example.com`).
   - Merge de `section_labels` ES/EN sobre defaults en inglés.
   - Normalización de fechas (`clean_date_str` en `render_service.py`) y teléfonos (`sanitize_phone`, aplica prefijos `+57`/`+1`).
6. **Render PDF.** `render_service.convert_llm_json_to_rendercv_dict()` adapta el JSON al esquema de RenderCV (`cv` + `design`), setea `allow_page_break=false`, espaciados anti-orfanos y opcionalmente endurece tipografía para 1 página. Compila Typst y genera PDF.
7. **Persistencia.** `shutil.copy` del PDF de salida a `output/tailored_resume_<unix_ts>.pdf`.
8. **Stream final.** SSE con `download_url: "/api/download/<filename>"`.

---

## Endpoints

| Método | Ruta | Descripción |
|---|---|---|
| `GET` | `/` | Health check (`{"status": "AI Resume Backend is running OK!"}`). |
| `POST` | `/api/generate` | Pipeline completo. Acepta `multipart/form-data`: `file` (PDF), `jd`, `target_role`, `github_url`, `linkedin_url`, `custom_instructions`, `base_resume_filename`, `theme` (`sb2nov` \| `classic` \| `moderncv` \| `classic_html`), `fit_single_page`, `page_break_section`, `extract_linkedin_info`. Responde **SSE** con eventos `data: {...}\n\n`. |
| `POST` | `/api/analyze-ats` | Audita sin generar. Acepta `file` (PDF) + `jd`. Devuelve JSON: `ats_score`, `match_level`, `matched_keywords`, `missing_keywords`, `ai_detection_score`, `ai_tone_verdict`, `ai_humanize_tips`, `ats_formatting_score`, `actionable_tips`. |
| `GET` | `/api/download/{filename}` | Sirve el PDF desde `backend/output/`. |
| `POST` | `/api/clear-cache` | Borra todos los PDFs de `output/`. Devuelve `{deleted_files: N}`. |

---

## Estructura del proyecto

```text
jd-to-resume/
├── backend/
│   ├── main.py                  # FastAPI: endpoints, LinkedIn extractor, pipeline SSE, HTML fallback
│   ├── render_service.py        # Adaptador LLM-JSON → RenderCV dict + Typst + PDF
│   ├── requirements.txt         # 15 deps (ver sección)
│   ├── .env                     # Config local (gitignored)
│   └── output/                  # PDFs generados por timestamp
├── frontend/
│   ├── index.html               # <title>Resume Matcher AI</title>, fuentes Google
│   ├── src/
│   │   ├── main.tsx             # Entry React 19
│   │   ├── App.tsx              # Router simple landing ↔ tool (useState)
│   │   ├── LandingPage.tsx      # Hero + marquee stack + 3 cards features
│   │   ├── ToolApp.tsx          # UI principal: upload, ATS, refinamiento, score history
│   │   ├── index.css            # shadcn vars + neo-brutalist .rm-box / .rm-btn
│   │   ├── App.css
│   │   └── lib/utils.ts         # cn() utility (estilo shadcn)
│   ├── components.json          # shadcn/ui new-york, baseColor: zinc
│   ├── vite.config.ts           # @vitejs/plugin-react + alias @/
│   ├── tailwind.config.js
│   └── package.json             # React 19.2 + Vite 8 + Tailwind 3.4
├── README.md
├── jakes-resume.pdf             # CV de ejemplo para probar
└── resume-template-by-anubhav.pdf
```

---

## Tech stack

**Backend (Python 3.10+)**
- FastAPI + Uvicorn (ASGI)
- PyMuPDF (`fitz`) para extraer texto del PDF
- google-generativeai + openai (cliente OpenAI-compatible para cualquier proveedor compatible)
- RenderCV (Python API: `build_rendercv_dictionary_and_model`, `renderer.typst.generate_typst`, `renderer.pdf_png.generate_pdf`)
- Typst (motor tipográfico)
- Jinja2 + Playwright (render HTML fallback)
- python-multipart (form-data), python-dotenv, pydantic
- *No usados actualmente pero en `requirements.txt`: `weasyprint`, `langgraph`, `langchain-core`.*

**Frontend (Node 18+ / Vite 8)**
- React 19 + TypeScript
- Vite 8 + `@vitejs/plugin-react` + alias `@/`
- Tailwind CSS 3.4 + `tailwindcss-animate`
- shadcn/ui (`new-york`) sobre Radix UI: `@radix-ui/react-label`, `@radix-ui/react-progress`, `@radix-ui/react-slot`, `@radix-ui/react-toast`
- `class-variance-authority` + `tailwind-merge` + `clsx` (patrón shadcn)
- Framer Motion (animaciones landing + transiciones)
- Lucide React (iconos: `Sparkles`, `Upload`, `ShieldCheck`, `BarChart3`, etc.)

---

## Instalación y configuración

### Prerrequisitos
- Node.js 18+
- Python 3.10+
- Clave API de al menos un proveedor LLM (gratis en [Google AI Studio](https://aistudio.google.com/app/apikey)).

### 1. Backend

```bash
cd backend
python -m venv venv
# Windows
.\venv\Scripts\activate
# Linux / macOS
source venv/bin/activate

pip install -r requirements.txt
playwright install chromium
```

Crea `backend/.env` (ver sección siguiente) y arranca:

```bash
uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Frontend

```bash
cd frontend
npm install
npm run dev
```

Abre `http://localhost:5173`. El frontend habla con `http://localhost:8000` por defecto (configurable en `ToolApp.tsx`).

---

## Variables de entorno

Crea `backend/.env` con lo que necesites. El sistema funciona con sólo Gemini; el resto es opcional.

| Variable | Requerida | Descripción |
|---|---|---|
| `GEMINI_API_KEY` | Sí (si no hay primario) | API key de Google AI Studio. |
| `LLM_PROVIDER` | No | `gemini` (default) \| `openai_compatible` \| `deepseek` \| `minimax` \| `kimi` \| `moonshot` \| `openrouter` \| `groq`. |
| `LLM_API_KEY` | Sí si LLM_PROVIDER ≠ gemini | API key del proveedor primario. |
| `OPENAI_API_KEY` | Alias alternativo | Si existe, se usa como fallback de `LLM_API_KEY`. |
| `LLM_BASE_URL` | Condicional | Base URL del proveedor (ej. `https://api.deepseek.com/v1`). |
| `OPENAI_BASE_URL` | Alias alternativo | Idem. |
| `LLM_MODEL` | No | Modelo del primario. Default `gpt-4o-mini`. |
| `OPENAI_MODEL` | Alias alternativo | Idem. |
| `LINKEDIN_API_URL` | No | Endpoint de ProxyCurl o similar para extracción LinkedIn. |
| `LINKEDIN_API_KEY` | No | Auth Bearer para esa API. |
| `PROXYCURL_API_KEY` | Alias | Idem. |
| `LINKEDIN_EMAIL` | No | Si existe, se intenta Playwright autenticado. |
| `LINKEDIN_PASSWORD` | No | Credencial para `LINKEDIN_EMAIL`. |

**Ejemplo mínimo (sólo Gemini):**
```env
GEMINI_API_KEY=tu_clave_gemini
```

**Ejemplo con DeepSeek primario + Gemini fallback:**
```env
LLM_PROVIDER=openai_compatible
LLM_API_KEY=sk-...
LLM_BASE_URL=https://api.deepseek.com/v1
LLM_MODEL=deepseek-chat
GEMINI_API_KEY=tu_clave_gemini
```

**Ejemplo con LinkedIn enrichment:**
```env
LINKEDIN_EMAIL=tu_correo
LINKEDIN_PASSWORD=tu_password
```

> ⚠️ Scraping autenticado de LinkedIn viola sus TOS. Úsalo bajo tu responsabilidad; la API externa (ProxyCurl / similar) es la ruta recomendada para producción.

---

## Cómo funciona (en una mirada)

1. Abres la app y entras a la **Landing** → botón **OPEN GENERATOR**.
2. En **ToolApp** subes tu PDF base, pegas la JD, opcionalmente añades `target_role`, URLs de GitHub/LinkedIn y marcas *Extract LinkedIn*.
3. Eliges plantilla (`sb2nov`/`classic`/`moderncv`/`classic_html`), si quieres forzar 1 página y si quieres un corte de página antes de una sección.
4. `Generate` → la UI muestra el progreso en vivo (SSE) hasta `Finished` y te da el botón **Download**.
5. Activa *Auto-Validate ATS* y verás el puntaje ATS, AI tone, formato y keywords matched/missing. Eso se suma al `scoreHistory` con versión incrementada.
6. Refina: marca tips de humanización del análisis ATS, agrega keywords faltantes, escribe una instrucción libre → `Regenerate`. El backend toma el último PDF generado como base; tus mejoras no se pierden.
7. `Reset Process` → llama `/api/clear-cache`, limpia estado y borra los PDFs en `output/`.

---

## Licencia & créditos

Inspirado en el proyecto open-source `VJsharan/jd-to-resume` (Jinja2 + Playwright), endurecido en esta v2.5 con:

- **[RenderCV](https://github.com/sinaatalay/rendercv)** de Sina Atalay — framework CV en YAML/Typst con plantillas ATS-friendly (`sb2nov`, `classic`, `moderncv`).
- **[Typst](https://github.com/typst/typst)** — compilador tipográfico moderno, PDFs vectoriales nítidos a alta velocidad.
- **[shadcn/ui](https://ui.shadcn.com/)** sobre Radix UI — base de componentes para el frontend.
- **[Framer Motion](https://www.framer.com/motion/)** — microinteracciones y transiciones de la landing.

Hecho para iterar currículums sin perder la verdad de tu experiencia.
