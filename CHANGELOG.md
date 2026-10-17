# Changelog

Registro cronológico de cambios por sesión. Cada sesión documenta su
alcance (qué problemas atacó, qué archivos tocó, qué decisiones se
tomaron) y un trail de commits para auditoría.

## 2026-10-17 — Sesión "Code review + rebrand"

**Tipo:** refactor + bug-fix + feature.

### Frontend

- **Rebrand UI completo (PR1-PR6)**: design tokens (`index.css`),
  primitives `Button`/`Card`/`Badge` con variants, dark mode toggle
  (`useTheme` + `ThemeToggle` + FOUC-prevention script), Footer
  atribución a "Edited by Johan Ospitia".
- **Landing traducida a español**: hero, FEATURES array reescrito
  reflejando capacidades reales (Generación IA / Auditoría ATS /
  Personalización total). Removido pinning a Gemini: copy del tipo
  "tu IA favorita" reemplazó "nuestra IA (Gemini)" para reflejar el
  modelo BYOK multi-provider.
- **Dark mode completo**: cubre inversión de tabs seleccionadas
  (`bg-foreground text-background` en vez de `bg-black text-white`),
  migración de pill labels, e index.html (`lang="es"` + title
  sincronizado con el brand `ResumeTailor-AI`).
- **ErrorBoundary en `App.tsx`**: captura render errors con recovery
  card en español.

### Backend — Fixes del code review (Pass 1 / 2 / 3)

Audit estático sobre `backend/main.py` por pass, con foco en bugs
reales, malas prácticas y código deprecado. Total: **2 doc reviews
+ 13 commits de fixes**.

#### Bugs
- **BUG-01**: `call_llm_api` re-construia el orchestrator por llamada.
  Fix: delega al singleton `_llm_orchestrator`.
- **BUG-02**: `_persist_uploaded_photo` referenciaba globals
  definidos abajo. Fix: reordenado después de `_save_photo` /
  `_PHOTOS_DIR`.
- **BUG-03**: `_RL_HITS` acumulaba keys vacías. Fix: pop() en la rama
  429 y simetría en la rama happy-path.

#### Deprecations / legacy
- **`google.generativeai` (EOL)** → migrado al SDK oficial
  `google-genai`. Stub de tests actualizado a hermético.
- **`fitz` (deprecation namespace)** → migrado a `import pymupdf`
  como API canónica del proyecto.
- 4 imports no usados eliminados de `playwright_html_adapter`.
- Shims `_content_tokens` / `_content_drift` eliminados; el test
  correspondiente apunta al módulo fuente.

#### Arquitectura hexagonal (cierre MP-02)
- `enforce_rate_limit` + `_RL_HITS` → `application/rate_limit.py`.
  4 routers pasan de `from main import` (lazy, in-handler) a top-level
  imports.
- `_persist_uploaded_photo` → `photo_helpers.persist_uploaded_photo`
  con `photos_dir` explícito. Nuevo `application/paths.py` para
  `OUTPUT_DIR` / `PHOTOS_DIR`.
- `extract_linkedin_profile_data` →
  `application/services/linkedin_service.py`. Cierra el último
  `from main import` en servicio.

#### Otros (Pass 3)
- **NEW-01**: `print(f"[LINKEDIN EXTRACTOR] ...")` → `logger.info(...)`
  en `extract_linkedin_profile_data`.
- **NEW-02**: `from main import extract_linkedin_profile_data` (lazy
  en `generation_service.py:267`) → top-level import.

#### Hardening
- `test_main_module_imports_without_nameerror_on_helpers` recibia
  `ValueError` por no tener keys LLM en el sandbox. Inyectado
  `LLM_API_KEY=test-no-llm-call-expected` en el subprocess del test
  para que el modulo cargue limpio y el test cumpla su rol original
  (NameError scan, no LLM smoke).

### API base URL env var (deploy blocker)
Frontend con 9 call sites hardcodeando `http://localhost:8000`.
Migrado a `import.meta.env.VITE_API_BASE_URL` con helper
`apiUrl(path)` en `frontend/src/lib/api.ts`. Default a string vacío
(same-origin para deploy detrás de reverse proxy).

### Métricas finales

| Métrica | Antes | Después |
|---------|-------|---------|
| `main.py` líneas | 2510 | 297 |
| Tests passing | 222/222 | 222/222 |
| Backend deprecation warnings | 2 (gemini + fitz) | 0 |
| Circular import (`from main`) en hot paths | 6 sitios | 0 |
| `import fitz` | sí | no |
| `import google.generativeai` | sí | no |

### Pendiente (no bloqueante)

- **MP-01 (cosmetic)**: imports no-lazy restantes en `main.py`.
  Funcional pero estético — para una sesión dedicada.
- **Vitest + RTL setup**: no hay test infra en frontend.
- **`tests/test_yaml_endpoints.py`** legacy: roto desde el hex
  split pero no recolectado. Cleanup pendiente.
