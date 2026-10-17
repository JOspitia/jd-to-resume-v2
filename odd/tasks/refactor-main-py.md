# Refactor `main.py` — Arquitectura Hexagonal (Ports & Adapters)

> `backend/main.py` creció a **2.510 líneas** después de los fixes de seguridad (PR-Sec). El módulo mezcla HTTP routing, file persistence, prompt building, LLM orchestration, LinkedIn scraping, PDF rendering, YAML validation, IA repair y middlewares. La decisión de arquitectura es **hexagonal (Ports & Adapters)** porque:
>
> 1. Hay **múltiples adapters LLM** (OpenAI-compatible + Gemini cascade + DeepSeek) que cambian vía env var → vale la pena un port explícito.
> 2. Hay **2 adapters de PDF render** (RenderCV + Playwright HTML fallback) → port explícito.
> 3. Hay **3 estrategias de LinkedIn** (ProxyCurl API + Playwright auth + public scrape) → port explícito.
> 4. El **dominio** (qué es un CV, qué es un tailoring, qué es un score ATS) es estable y merece aislamiento.
>
> Documento define **6 commits chicos, verificables independientemente**. Cada commit preserva el comportamiento visible.

## Estado actual (snapshot del monolito)

| Bloque | Líneas en `main.py` hoy | Capa hexagonal destino |
|---|---|---|
| `extract_text` + `_extract_header_from_pdf_text` + 5 regex constants | 420-578 (158) | `adapters/parser/pymupdf_adapter.py` |
| `GeminiResumeOutput` (pydantic) | 580-592 | `domain/entities.py` |
| `call_llm_api` + 3 cascades | 594-700 (106) | `adapters/llm/` (3 archivos) + `application/services/llm_orchestrator.py` |
| `extract_linkedin_profile_data` | 704-1041 (337) | `adapters/linkedin/` (3 archivos) + `application/services/linkedin_service.py` |
| `_build_language_override` | 1043-1111 (68) | `application/services/translation_service.py` |
| `_build_audit_prompt` + `_run_audit_against_text` | 1113-1168 (55) | `application/use_cases/analyze_ats.py` + `domain/audit_prompts.py` (módulo) |
| `generation_pipeline` | 1170-1635 (465) | `application/use_cases/generate_resume.py` |
| `_run_internal_audit` | 1637-1665 (28) | `application/use_cases/analyze_ats.py` (privado al use case) |
| `generate_resume` | 1668-1737 (69) | `routes/generate_router.py` (thin HTTP layer) |
| `analyze_ats` | 1740-1779 (39) | `routes/audit_router.py` |
| `render_from_yaml` | 1782-1889 (107) | `routes/yaml_editor_router.py` |
| `analyze_yaml` | 1892-1973 (81) | `routes/audit_router.py` |
| `_YAML_SCHEMA_DESCRIPTION` + helpers YAML (`_parse_yaml_safe`, `_validate_yaml_schema`, `_content_tokens`, `_content_drift`, `_strip_yaml_fences`) | 1976-2088 (~112) | `domain/yaml_pipeline.py` (puro) |
| `_ask_llm_to_repair_yaml_async` | 2142-2187 (45) | `application/use_cases/repair_yaml.py` |
| `repair_yaml` | 2190-2353 (163) | `routes/yaml_editor_router.py` |
| `download_resume` | 2369-2392 (23) | `routes/assets_router.py` |
| `clear_cache` | 2394-2414 (20) | `routes/assets_router.py` |
| `_persist_uploaded_photo` | 100-122 (22) | `adapters/storage/filesystem_storage.py` |
| `HTML_TEMPLATE` (string Jinja) | 131-320 (190) | `adapters/renderer/templates/classic.html.j2` |
| `_ats_link_label`, `_check_profile_urls_not_fragmented`, `_photo_to_data_uri`, `_render_html_template` | 322-418 (~95) | `adapters/renderer/playwright_html_adapter.py` |
| `read_root` | 125-126 | `main.py` (health check trivial) |

## Arquitectura hexagonal propuesta

```
backend/
├── main.py                          ~60  FastAPI() + middleware + router include
├── routes/                           HTTP layer (FastAPI routers, thin)
│   ├── __init__.py
│   ├── generate_router.py            ~50  generate_resume (FastAPI endpoint)
│   ├── audit_router.py               ~90  analyze_ats + analyze_yaml
│   ├── yaml_editor_router.py         ~280 render_from_yaml + repair_yaml
│   └── assets_router.py              ~50  download_resume + clear_cache
│
├── application/                      Use cases + services (orquestación)
│   ├── __init__.py
│   ├── use_cases/
│   │   ├── __init__.py
│   │   ├── generate_resume.py        ~480 generation_pipeline + GenerateResumeUseCase class
│   │   ├── analyze_ats.py            ~90  AnalyzeATSUseCase + _run_internal_audit
│   │   └── repair_yaml.py            ~50  RepairYAMLUseCase (wraps domain + LLMRepair service)
│   └── services/
│       ├── __init__.py
│       ├── llm_orchestrator.py       ~100 LLMOrchestrator (cascade de N providers via port)
│       ├── linkedin_service.py       ~370 extract_linkedin_profile_data (3 estrategias via port)
│       └── translation_service.py    ~80  _build_language_override
│
├── domain/                           Pure domain (NO imports de infrastructure)
│   ├── __init__.py
│   ├── entities.py                   ~120 Resume + JobDescription + AuditResult + DomainGame Protocol
│   ├── yaml_pipeline.py              ~140 _parse_yaml_safe + _validate_yaml_schema + _content_drift + helpers
│   └── audit_prompts.py              ~110 build_audit_prompt + AUDIT_SEEDS (move from backend/audit_prompts.py)
│
├── ports/                            Interfaces (Protocol, structural subtyping)
│   ├── __init__.py
│   ├── llm_provider.py               ~40  Protocol LLMProvider.complete(prompt) -> str
│   ├── pdf_renderer.py               ~60  Protocol PDFRenderer.render(parsed_data, output_path, ...) -> None
│   ├── resume_parser.py              ~40  Protocol ResumeParser.extract_text(file_path) + extract_header(text)
│   ├── linkedin_scraper.py           ~30  Protocol LinkedInScraper.scrape(url) -> str
│   └── resume_storage.py             ~40  Protocol ResumeStorage.save_pdf + clear_cache + read_pdf
│
├── adapters/                         Concrete implementations of ports
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── openai_compatible.py      ~80  OpenAICompatibleAdapter (DeepSeek, Groq, OpenRouter, ...)
│   │   ├── gemini.py                 ~70  GeminiAdapter (cascade 2.0-flash → 1.5-flash → 1.5-pro)
│   │   ├── deepseek_direct.py        ~60  DeepSeekDirectAdapter (legacy fallback)
│   │   └── factory.py                ~30  build_llm_provider() selecciona según LLM_PROVIDER env
│   ├── renderer/
│   │   ├── __init__.py
│   │   ├── rendercv_adapter.py       ~10  wrapper sobre render_service.render_cv_with_rendercv
│   │   ├── playwright_html_adapter.py ~100 _render_html_template (lee templates/classic.html.j2)
│   │   └── factory.py                ~30  build_pdf_renderer() selecciona según theme
│   ├── parser/
│   │   ├── __init__.py
│   │   └── pymupdf_adapter.py        ~160 extract_text + _extract_header_from_pdf_text + 5 regex
│   ├── linkedin/
│   │   ├── __init__.py
│   │   ├── proxycurl_adapter.py      ~50  ProxyCurlLinkedInAdapter (cuando LINKEDIN_API_URL seteada)
│   │   ├── playwright_adapter.py     ~280 PlaywrightLinkedInAdapter (login + scroll + scrape)
│   │   ├── public_scraper_adapter.py ~50  PublicLinkedInAdapter (urllib + og:description)
│   │   └── factory.py                ~30  build_linkedin_scraper() selecciona según env vars
│   └── storage/
│       ├── __init__.py
│       └── filesystem_storage.py     ~70  save_pdf + read_pdf + clear_cache + persist_photo
│
├── schemas/                          Pydantic (HTTP boundary only, NO domain)
│   ├── __init__.py
│   └── api_models.py                 ~15  GeminiResumeOutput (move from main.py)
│
├── templates/                        Jinja2 templates
│   └── classic.html.j2               ~190 HTML_TEMPLATE (extract from main.py as file)
│
├── domain_games/                     (ya existe ✓ — quda como adapters/game_registry.py)
├── yaml_helpers.py                   (ya existe ✓ — quda como parte de domain/yaml_pipeline.py)
├── photo_helpers.py                  (ya existe ✓ — quda como parte de adapters/storage/filesystem_storage.py)
├── language.py                       (ya existe ✓ — usado por translation_service)
├── render_service.py                 (ya existe ✓ — absorbido por adapters/renderer/rendercv_adapter.py)
└── audit_prompts.py                  (MOVED a domain/audit_prompts.py — actualizar import paths)
```

## Capas y sus responsabilidades

### Domain (`backend/domain/`)

Cero dependencias externas (solo `typing`, `pyyaml`, `pydantic.BaseModel` para value objects). **Regla de oro**: este paquete no puede importar de `adapters/`, `application/`, ni `ports/`. Si lo hace, se rompió la arquitectura.

```python
# domain/entities.py
@dataclass
class Resume:
    """A parsed CV. Output of ResumeParser, input to PDFRenderer."""
    name: str
    contact: ContactInfo
    summary: str
    experience: list[Experience]
    education: list[Education]
    skills: list[Skill]
    projects: list[Project]
    achievements: list[str]
    section_labels: dict[str, str] = field(default_factory=dict)
    raw_yaml: str | None = None  # if loaded from YAML, the source

@dataclass
class JobDescription:
    text: str
    target_role: str | None = None
    custom_instructions: str | None = None

@dataclass
class AuditResult:
    ats_score: int
    match_level: str
    matched_keywords: list[str]
    missing_keywords: list[str]
    ai_detection_score: int
    ai_tone_verdict: str
    ai_humanize_tips: list[str]
    ats_formatting_score: int
    actionable_tips: list[str]

@dataclass
class TailoredResume:
    """Output of GenerateResumeUseCase."""
    pdf_path: str
    yaml_text: str
    parsed_data: dict  # the canonical dict shape

class DomainGame(Protocol):
    """Already implemented in backend/domain_games/__init__.py"""
    name: str
    label_es: str
    label_en: str
    skill_taxonomy_es: list[str]
    skill_taxonomy_en: list[str]
    section_labels_es: dict[str, str]
    section_labels_en: dict[str, str]
```

### Ports (`backend/ports/`)

```python
# ports/llm_provider.py
from typing import Protocol

class LLMProvider(Protocol):
    """Any LLM that can complete a prompt and return text."""
    def complete(self, prompt: str, *, model: str | None = None) -> str: ...
    @property
    def name(self) -> str: ...

# ports/pdf_renderer.py
class PDFRenderer(Protocol):
    """Render a parsed Resume dict to a PDF file."""
    def render(
        self,
        parsed_data: dict,
        output_path: str,
        *,
        theme: str = "sb2nov",
        fit_single_page: bool = False,
        page_break_section: str | None = None,
        photo_path: str | None = None,
    ) -> None: ...
    @property
    def name(self) -> str: ...

# ports/resume_parser.py
class ResumeParser(Protocol):
    """Extract text and header fields from a PDF."""
    def extract_text(self, file_path: str) -> str: ...
    def extract_header(self, text: str) -> dict: ...

# ports/linkedin_scraper.py
class LinkedInScraper(Protocol):
    """Scrape a LinkedIn profile. Returns a Markdown/text dump."""
    def scrape(self, linkedin_url: str) -> str: ...
    @property
    def strategy_name(self) -> str: ...

# ports/resume_storage.py
class ResumeStorage(Protocol):
    """Persist and serve generated PDFs and candidate photos."""
    def save_uploaded_pdf(self, content: bytes, original_filename: str) -> str: ...
    def save_generated_pdf(self, source_path: str) -> str: ...
    def read_pdf(self, filename: str) -> bytes: ...
    def delete_pdf(self, filename: str) -> None: ...
    def clear_all(self) -> tuple[int, int]: ...  # (pdfs_deleted, photos_deleted)
```

### Adapters (`backend/adapters/`)

Cada adapter implementa un port. La elección del adapter concreto se hace en una factory function que lee env vars.

```python
# adapters/llm/factory.py
def build_llm_provider() -> LLMProvider:
    """Select the LLM adapter based on env vars. Returns the FIRST adapter;
    the cascade is handled by the application layer (LLMOrchestrator), not here."""
    provider = os.getenv("LLM_PROVIDER", "gemini").lower()
    if provider in ("openai_compatible", "deepseek", "minimax", "kimi", "moonshot", "openrouter", "groq"):
        return OpenAICompatibleAdapter(...)
    if provider == "gemini":
        return GeminiAdapter(...)
    # etc.

# adapters/renderer/factory.py
def build_pdf_renderer(theme: str) -> PDFRenderer:
    """Select renderer based on theme. sb2nov|classic|moderncv → RenderCVAdapter;
    classic_html → PlaywrightHTMLAdapter. Falls back to HTML if RenderCV fails."""
    if theme == "classic_html":
        return PlaywrightHTMLAdapter()
    return RenderCVAdapter(theme)
```

### Application (`backend/application/`)

Use cases orquestan los ports. **No saben nada de FastAPI ni de HTTP**. Reciben ports por constructor (composition root en `main.py`).

```python
# application/use_cases/generate_resume.py
class GenerateResumeUseCase:
    def __init__(
        self,
        llm_orchestrator: LLMOrchestrator,
        pdf_renderer: PDFRenderer,         # factory decides sb2nov vs classic_html
        parser: ResumeParser,
        linkedin_service: LinkedInService,
        audit_uc: AnalyzeATSUseCase,       # for the auto-re-audit
        storage: ResumeStorage,
    ) -> None: ...

    async def execute(
        self,
        uploaded_pdf_path: str,
        jd: JobDescription,
        game: DomainGame,
        *,
        base_resume_filename: str | None = None,
        force_language: str | None = None,
        edit_before_generate: bool = False,
        photo_path: str | None = None,
        custom_instructions: str | None = None,
    ) -> AsyncIterator[dict]:
        """The streaming generator. Yields SSE events as it progresses."""
        ...
```

### Routes (`backend/routes/`)

Thin HTTP layer. No lógica de negocio. Recibe el use case por dependency injection (composition root en `main.py`).

```python
# routes/generate_router.py
from fastapi import APIRouter, Form, File, UploadFile, Depends

def build_generate_router(generate_uc: GenerateResumeUseCase) -> APIRouter:
    router = APIRouter(prefix="/api", tags=["generate"])

    @router.post("/generate")
    async def generate_resume(
        file: UploadFile = File(...),
        jd: str | None = Form(None),
        # ... 14 form fields ...
    ):
        # 1. Persist upload via storage adapter
        uploaded_path = await generate_uc.storage.save_uploaded_pdf(
            await file.read(), file.filename
        )
        # 2. Call use case, return StreamingResponse
        return StreamingResponse(
            generate_uc.execute(uploaded_path, jd, game, ...),
            media_type="text/event-stream",
        )

    return router
```

### Composition root (`main.py`)

```python
# main.py (~60 líneas)
def create_app() -> FastAPI:
    load_dotenv()

    # 1. Build adapters
    llm_provider = build_llm_provider()
    pdf_renderer = build_pdf_renderer(theme="sb2nov")
    parser = PyMuPDFParser()
    linkedin_scraper = build_linkedin_scraper()
    storage = FilesystemStorage(OUTPUT_DIR, PHOTOS_DIR)

    # 2. Build services
    llm_orchestrator = LLMOrchestrator([llm_provider, GeminiAdapter(...), DeepSeekDirectAdapter(...)])
    linkedin_service = LinkedInService(linkedin_scraper, llm_orchestrator)
    translation_service = TranslationService()

    # 3. Build use cases
    analyze_ats_uc = AnalyzeATSUseCase(llm_orchestrator, parser, audit_prompts)
    repair_yaml_uc = RepairYAMLUseCase(llm_orchestrator, yaml_pipeline)
    generate_uc = GenerateResumeUseCase(
        llm_orchestrator, pdf_renderer, parser,
        linkedin_service, analyze_ats_uc, storage,
        translation_service,
    )

    # 4. Build FastAPI
    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=[...], ...)
    app.add_middleware(SlowAPIASGIMiddleware)
    limiter = Limiter(default_limits=["5/minute"])
    app.state.limiter = limiter
    app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

    # 5. Mount routers
    app.include_router(build_generate_router(generate_uc))
    app.include_router(build_audit_router(analyze_ats_uc))
    app.include_router(build_yaml_editor_router(repair_yaml_uc, pdf_renderer))
    app.include_router(build_assets_router(storage))

    return app

app = create_app()
```

## Grafos de dependencias

```
ports/                  ← stdlib only (typing.Protocol)
    ↑
domain/                 ← stdlib + pyyaml (puro)
    ↑
adapters/               ← domain (for entities) + ports (for interfaces) + external libs (fitz, google.generativeai, openai, playwright, jinja2)
    ↑
application/            ← domain + ports (never imports adapters directly)
    ↑
routes/                 ← application (use cases) + adapters (only via composition root in main.py)
    ↑
main.py                 ← composes everything
```

**Regla**: `application/` y `routes/` **nunca importan de `adapters/` directamente**. Reciben ports por inyección. Si una ruta hace `from adapters.llm.gemini import GeminiAdapter`, se rompió la hexagonal.

## Plan de migración de tests

| Archivo | Qué testea hoy | Acción |
|---|---|---|
| `test_yaml_helpers.py` (364) | `serialize_resume_data_as_text`, `yaml_safe_dump_unicode` | Mover a `tests/test_domain_yaml_pipeline.py`. Mismos tests, distinto path. |
| `test_domain_routing.py` (276) | Registry de games | **Sin cambio.** El módulo no se mueve (queda en `domain_games/`). |
| `test_audit_prompts.py` (148) | `build_audit_prompt` | Mover a `tests/test_domain_audit_prompts.py`. Path update. |
| `test_content_drift.py` (92) | `_content_drift` | Mover a `tests/test_domain_yaml_pipeline.py` (mismo archivo que yaml_helpers tests). |
| `test_security_fixes.py` (220) | `main._DOWNLOAD_FILENAME_RE`, CORS, rate limit | Reescribir para apuntar a `routes.assets._DOWNLOAD_FILENAME_RE` y a la nueva composición `create_app()`. |
| `test_input_validation.py` (140) | `render_service.convert_llm_json_to_rendercv_dict`, `domain_games.get_game` | `convert_llm_json_to_rendercv_dict` se mueve a `adapters/renderer/rendercv_adapter.py`. Update path. |
| `test_yaml_endpoints.py` (252, **roto pre-existente**) | Endpoints con mocks | **Bloqueado.** Ignorado. Refactor hexagonal lo arreglará naturalmente (los endpoints reciben use cases por DI, no globals). |

**Tests nuevos a crear durante el refactor**:
- `tests/test_llm_orchestrator.py` — cascade con mocks de providers, fallback chain, timeout handling.
- `tests/test_pdf_renderers.py` — RenderCVAdapter vs PlaywrightHTMLAdapter con `parsed_data` mínimo.
- `tests/test_resume_parser.py` — `extract_text` y `extract_header` con PDFs reales.
- `tests/test_filesystem_storage.py` — save/read/delete con tempdir.
- `tests/test_use_case_generate_resume.py` — use case con todos los ports mockeados, verifica el flujo SSE.

## Orden de commits

### Commit 1 — `refactor: extract domain/ + ports/`

**Qué se mueve**:
- `GeminiResumeOutput` → `schemas/api_models.py` (HTTP boundary).
- Define `Resume`, `JobDescription`, `AuditResult`, `TailoredResume` dataclasses → `domain/entities.py`.
- Define `LLMProvider`, `PDFRenderer`, `ResumeParser`, `LinkedInScraper`, `ResumeStorage` Protocols → `ports/`.

**Criterio de aceptación**:
- `cd backend && pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` → 90 pasan
- `python -c "from domain.entities import Resume; from ports.llm_provider import LLMProvider"` funciona
- Cero dependencias externas en `domain/` (verificar con `pip install pip-check` o inspección manual)
- `git diff --stat` muestra ~200 líneas nuevas en `domain/entities.py` + `ports/*.py`, main.py intacto

**Por qué primero**: las entidades y protocols son los cimientos del resto. No rompen nada del comportamiento actual porque main.py sigue siendo el composition root.

### Commit 2 — `refactor: extract adapters/parser/pymupdf_adapter.py`

**Qué se mueve**:
- `extract_text` + `_extract_header_from_pdf_text` + 5 regex constants → `adapters/parser/pymupdf_adapter.py` con una clase `PyMuPDFParser()` que implementa `ResumeParser`.
- `main.py` lo importa y reemplaza las llamadas internas por el adapter.

**Criterio de aceptación**:
- `pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` → 90 pasan
- `from adapters.parser.pymupdf_adapter import PyMuPDFParser; PyMuPDFParser().extract_text("file.pdf")` funciona
- Nuevo `tests/test_resume_parser.py` con 5 tests (PDF vacío, con /Link annotations, header detection email/tel/github).
- `git diff --stat` muestra ~160 líneas removidas de main.py, ~160 en adapters/parser/

**Por qué segundo**: el parser es independiente (no depende de LLM, LinkedIn, render). Testeable con PDFs reales sin mocks.

### Commit 3 — `refactor: extract adapters/llm/ + application/services/llm_orchestrator.py`

**Qué se mueve**:
- `call_llm_api` + cascades → 3 archivos en `adapters/llm/`:
  - `openai_compatible.py` (OpenAI + DeepSeek via OpenAI client)
  - `gemini.py` (cascade 2.0-flash → 1.5-flash → 1.5-pro)
  - `deepseek_direct.py` (DeepSeek legacy)
  - `factory.py` (`build_llm_provider()` lee env vars)
- `application/services/llm_orchestrator.py` orquesta los providers en orden de prioridad con fallback (era la lógica de cascada en `call_llm_api`).
- `main.py` usa `LLMOrchestrator` en lugar de `call_llm_api`.

**Criterio de aceptación**:
- `pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` → 90 pasan
- `from application.services.llm_orchestrator import LLMOrchestrator; o = LLMOrchestrator([GeminiAdapter()])` funciona
- Smoke manual con `LLM_PROVIDER=gemini` y `LLM_PROVIDER=openai_compatible` configurados → 200 con download_url
- Nuevo `tests/test_llm_orchestrator.py` con mocks de los providers, verifica el orden de cascada y el fallback.
- `git diff --stat` muestra ~120 líneas removidas de main.py, ~250 en adapters/llm/ + application/services/

**Por qué tercero**: la cascada LLM ya estaba aislada. Agregar el port y la factory es mecánico.

### Commit 4 — `refactor: extract adapters/linkedin/ + application/services/linkedin_service.py`

**Qué se mueve**:
- `extract_linkedin_profile_data` (3 estrategias) → 3 adapters en `adapters/linkedin/`:
  - `proxycurl_adapter.py` (cuando `LINKEDIN_API_URL` seteada)
  - `playwright_adapter.py` (login + scroll + scrape, ~280 líneas)
  - `public_scraper_adapter.py` (urllib + og:description)
  - `factory.py` (`build_linkedin_scraper()` decide cuál instanciar según env vars)
- `application/services/linkedin_service.py` orquesta el fallback entre las 3 estrategias (con cache `_linkedin_cache`).

**Criterio de aceptación**:
- `pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` → 90 pasan
- Sin tests nuevos (LinkedIn scraping es difícil de testear sin red real; se mantiene la cobertura actual).
- Smoke manual: `LINKEDIN_API_URL` configurada → estrategia 1; sin auth → fallback a public_scraper.
- `git diff --stat` muestra ~340 líneas removidas de main.py, ~350 en adapters/linkedin/

**Por qué cuarto**: LinkedIn es el bloque más grande de main.py. Separarlo reduce significativamente el tamaño y permite mockear LinkedIn en tests futuros sin tocar `main.py`.

### Commit 5 — `refactor: extract adapters/renderer/ + templates/classic.html.j2`

**Qué se mueve**:
- `HTML_TEMPLATE` (string 190 líneas) → `adapters/renderer/templates/classic.html.j2` (archivo Jinja2).
- `_ats_link_label`, `_check_profile_urls_not_fragmented`, `_photo_to_data_uri`, `_render_html_template` → `adapters/renderer/playwright_html_adapter.py` con clase `PlaywrightHTMLAdapter()` que implementa `PDFRenderer`.
- `render_cv_with_rendercv` (en `render_service.py`) → wrapper en `adapters/renderer/rendercv_adapter.py` con clase `RenderCVAdapter(theme)`.
- `adapters/renderer/factory.py` (`build_pdf_renderer(theme)` decide cuál).

**Criterio de aceptación**:
- `pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` → 90 pasan
- Smoke: `theme=sb2nov` → RenderCVAdapter; `theme=classic_html` → PlaywrightHTMLAdapter; PDF renderiza idéntico al baseline (diff binario).
- Nuevo `tests/test_pdf_renderers.py` con mocks de `pdfkit`/Typst/Chromium.
- `git diff --stat` muestra ~260 líneas removidas de main.py, ~280 en adapters/renderer/

**Por qué quinto**: el render ya estaba parcialmente aislado en `render_service.py`. Completar la separación nos deja con un adapter limpio testeable.

### Commit 6 — `refactor: extract routes/ + application/use_cases/ + composition root`

**Qué se mueve**:
- `generation_pipeline` + `_run_internal_audit` + `generate_resume` → `application/use_cases/generate_resume.py` (clase `GenerateResumeUseCase`) + `routes/generate_router.py` (thin).
- `analyze_ats` + `analyze_yaml` → `application/use_cases/analyze_ats.py` + `routes/audit_router.py`.
- `render_from_yaml` + `repair_yaml` + helpers YAML → `application/use_cases/repair_yaml.py` + `routes/yaml_editor_router.py`.
- `download_resume` + `clear_cache` + `OUTPUT_DIR`/`PHOTOS_DIR`/`_DOWNLOAD_FILENAME_RE` → `adapters/storage/filesystem_storage.py` + `routes/assets_router.py`.
- `_persist_uploaded_photo` → `adapters/storage/filesystem_storage.py`.
- `_build_language_override` → `application/services/translation_service.py`.
- `main.py` final: ~60 líneas, solo `create_app()` composition root.
- `audit_prompts.py` se mueve a `domain/audit_prompts.py`. Actualizar 2 imports en tests.

**Criterio de aceptación**:
- `pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` → 90 pasan (con los tests actualizados apuntando a los nuevos paths).
- `wc -l backend/main.py` ≤ 100.
- Smoke completo con servers arriba (todos los endpoints responden 200/4xx según contrato).
- Frontend carga en `http://localhost:5173`, llama al backend, recibe SSE, descarga PDF.
- `git diff --stat` muestra ~2.000 líneas removidas de main.py, ~1.500 distribuidas en routes/application.

**Por qué último y más grande**: este commit consolida todo. Riesgo medio: si un import falla, el server no arranca. Mitigación: los tests de `test_security_fixes.py` cubren los routers críticos. Smoke manual end-to-end con el frontend abierto.

## Tests de humo manuales para cada commit

| Commit | Smoke test | Comando |
|---|---|---|
| 1 — domain/ports | (no UI change) | `python -c "from domain.entities import Resume; from ports.llm_provider import LLMProvider"` |
| 2 — parser adapter | `extract_text` igual | `uvicorn main:app` → `curl -X POST http://localhost:8000/api/generate` con un PDF → SSE emite "Extracting Text from Resume" |
| 3 — LLM orchestrator | Cascade funciona | Cambiar `LLM_PROVIDER` entre `gemini` y `openai_compatible` → SSE termina con `download_url` |
| 4 — LinkedIn adapters | (sin LLM key) | `curl http://localhost:8000/api/generate -F file=@cv.pdf -F jd=... -F extract_linkedin_info=true -F linkedin_url=https://linkedin.com/in/...` → log muestra "LinkedIn extraction strategy: public" |
| 5 — renderers | PDF idéntico | Generar un PDF con `theme=sb2nov` y `theme=classic_html` → diff binario muestra bytes equivalentes |
| 6 — routes/application | Endpoints | Iterar todos los endpoints, validar respuesta |

## NO hacer (explícito)

| Idea | Por qué no |
|---|---|
| Implementar dependency injection container (`dependency-injector`, `fastapi-di`) | Overkill. `main.py:create_app()` es el composition root, 30 líneas. |
| Mover `domain_games/` adentro de `domain/` | El roadmap original lo dejó como módulo top-level (T1 de multi-domain). El registry es domain-level (lo trato como `DomainGame` Protocol). Cambio de path requiere actualizar 2 archivos de tests. No vale en este PR. |
| Convertir todos los adapters a async | `extract_text` es sync (PyMuPDF es sync). Los use cases usan `asyncio.to_thread` donde corresponde. |
| Crear `tests/conftest.py` que arregle `test_yaml_endpoints.py` | El refactor lo arreglará naturalmente (los endpoints reciben use cases por DI). Lo agrego en el commit 6 con tests nuevos. |
| Hacer todos los use cases clases | Algunos pueden ser funciones puras (ej. `RepairYAMLUseCase` es tan simple que una función basta). Mezclar es legítimo. |
| Agregar tests E2E con TestClient + httpx | El alcance ya es grande. Mejor agregar en un PR-Tests aparte. |

## Riesgos identificados

| Riesgo | Probabilidad | Mitigación |
|---|---|---|
| Circular import entre capas | Baja (grafo acíclico por diseño) | El orden topológico evita ciclos. Si pasa, mover el import adentro de la función (lazy import). |
| Cambio de comportamiento del LLM orchestrator | Baja | Mismas 3 cascadas, mismas timeouts. Tests con mocks cubren el orden. |
| `test_yaml_endpoints.py` arreglado por DI pero no testeado | Media | En commit 6, agregar 3 tests nuevos con TestClient que usan composition root real (no monkeypatch de sys.modules). |
| Output PDF ligeramente diferente | Muy baja | Diff binario antes/después de commit 5. |
| Frontend rompe por paths distintos | Muy baja | Las firmas HTTP no cambian. Solo cambia la implementación server-side. |

## Log

- **L1** (input usuario): *"antes de continuar veo que el archivo main tiene 2500 lineas no es poo tampoco sigue conceptos solid se podría cambiar?"*
- **L2** (decisión usuario): plan detallado antes de tocar código.
- **L3** (decisión usuario, arquitectura): hexagonal (Ports & Adapters), no layered.
- **L4** (justificación hexagonal): 3 adapters LLM + 2 adapters PDF + 3 adapters LinkedIn + 1 storage = **9 implementaciones intercambiables** detrás de 5 ports. Vale la pena la abstracción.
- **L5** (orden de commits justificado): domain + ports primero (sin deps), después adapters hoja por hoja (parser, llm, linkedin, renderer), al final composition root en main.py que inyecta todo. Cada commit es verificable independientemente.
- **L6** (pre-existente bloqueante): `test_yaml_endpoints.py` roto desde yaml-editor-restore T9. La DI del commit 6 lo arregla naturalmente. Si pasa, sumo los tests en este PR; si no, queda como follow-up.
- **L7** (validación post-implementación): después de cada commit correr `pytest tests/ -q --ignore=tests/test_yaml_endpoints.py` y esperar 90 passing. Si falla, NO mergeear el commit; arreglar antes. Smoke manual con el server arriba en commit 6.
- **L8** (regla arquitectónica a enforce): `application/` y `routes/` **nunca importan de `adapters/` directamente**. Reciben ports por inyección. Verificar con `grep -r "from adapters" application/ routes/` antes de cada commit.