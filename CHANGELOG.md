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

## 2026-10-17 — Sesión "Frontend code review"

**Tipo:** bug-fix + refactor (frontend).

### Bugs

- **BUG-01**: `/api/generate` no tenía `AbortController` ni timeout, a diferencia de `analyze-ats` y `render-from-yaml` que ya usan 60s. SSE backend hung podía dejar requests abiertas indefinidamente. Fix: AbortController con 120s ceiling + `clearTimeout` en finally.
- **BUG-02**: closure de `forceTranslateToEnglish` (state de React) podía capturar el valor viejo cuando el usuario hacía click en "Translate to English" inmediatamente antes de `handleGenerate`. Fix: usar `shouldTranslate` (variable local ya resuelta param > state) en vez del state directo.
- **BUG-03**: 4 listas en `AuditPanel.tsx` usaban `key={i}` (índice de array) en `map` callbacks. Para listas interactivas (botones de keywords con checkbox, labels de tips) el índice como key es frágil: si el backend reordena keywords en el próximo audit, los checkboxes pueden quedar marcando valores equivocados. Fix: `key={kw}` / `key={tip}` en las 4 listas. También removimos el `, i: number` parameter ya inutilizado.
- **BUG-04**: `useProfile.ts` revocaba la Object URL de la foto en 3 sitios (manual en `handlePhotoChange`, manual en `clearPhoto`, cleanup en `useEffect`). El cleanup capturaba el mismo valor que las manuales, revocando doble. Fix: borrar las manuales, dejar el `useEffect` cleanup como único punto de revocación (cubre los 3 escenarios: cambio de foto, clear, unmount).

### Malas prácticas

- **MP-02**: 5 `catch (err: any)` en `useGeneration`, `useYamlEditor`, `useAudit`. Fix: `catch (err: unknown)` + narrowing explícito con `err instanceof DOMException && err.name === 'AbortError'` para aborts y `err instanceof Error ? err.message : fallback` para mensajes. TypeScript ahora chequea los accesos.
- **MP-03**: `let interval: any` en `useGeneration` (timer de elapsedSeconds). Fix: `ReturnType<typeof setInterval> | null`.
- **MP-04**: `handleResetProcess` en `ToolApp` era función inline recreada en cada render, forzando re-render de `ResultsPanel` aunque no cambiara. Fix: envuelta en `useCallback` con deps `[profile, generation, audit, yamlEditor]`.
- **MP-05**: `resetProfile` mezcla prefs de sesión (theme, fit, page break) con flags de comportamiento (`strictEditsOnly`, `extractLinkedinInfo`). Documentamos explícitamente en el JSDoc qué sobrevive reset y por qué (preservando v2.5 UX byte-for-byte sin tocar comportamiento).

### Type safety (`any` → interface)

- **MP-01 + DUP-03**: el shape del response de `/api/analyze-ats` estaba declarado 3 veces con tipos parciales o `any` (`useAudit.ts:42`, `AuditPanel.tsx:14`, `useGeneration.ts:83-91`). Fix: extraer `AuditData` interface en `frontend/src/types/audit.ts` (8 campos opcionales) y migrar los 3 sitios. Si el backend agrega un campo nuevo, modificar solo `AuditData` y TS avisa a cada consumidor.

### Código duplicado

- **DUP-01**: bloque "degenerate-output guard" (cuenta líneas con contenido + threshold 40% con floor de 3) aparecía idéntico entre `handleRenderFromYaml` y `handleRepairYaml`, solo difería en el mensaje. Fix: extraer `validateRepairOutput(repairedYaml, originalYaml)` como top-level helper que retorna `{ ok: true } | { ok: false; message: string }`.
- **DUP-02**: 3 endpoints repetían el patrón `new AbortController + setTimeout(controller.abort, 60000) + fetch + clearTimeout`. Fix: helper `fetchWithTimeout(url, options, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS = 60_000)` en `lib/api.ts` + export `SSE_FETCH_TIMEOUT_MS = 120_000` por si migramos SSE después.

### `key={i}` extras (revisión, no modificados)

- `ScoreHistory.tsx:33` y 5 sitios en `YamlFormEditor.tsx`: NO son el mismo anti-pattern que BUG-03. `ScoreHistory` es display-only. `YamlFormEditor` tiene callbacks de update posicionales (`data.map((e, idx) => idx === i ? ...`) que requieren index tracking. Cambiar a keys estables requeriría rediseñar las callbacks — fuera de scope.

### Métricas

- Tests backend: 222/222 sigue verde.
- Sin cambios en backend.
- 2 archivos nuevos: `frontend/src/types/audit.ts`, ninguno en backend.
- 0 `catch (err: any)`, 0 `any` en shapes de audit (los 3 sitios migrados).

### Pendiente (no bloqueante)

- `tests/test_yaml_endpoints.py` legacy roto: no recolectado, explota si se corre puntual. Cleanup pendiente.
- MP-01 cosmetic: imports no-lazy restantes en `main.py`.
- Vitest + RTL setup: sigue sin test infra frontend.
