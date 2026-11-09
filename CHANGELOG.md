# Changelog

Registro cronológico de cambios por sesión. Cada sesión documenta su
alcance (qué problemas atacó, qué archivos tocó, qué decisiones se
tomaron) y un trail de commits para auditoría.

## 2026-11-09 — Sesión "Docker de punta a punta"

**Tipo:** feature (infraestructura).

### Feature — Stack 100 % Docker

Antes el backend solo se levantaba con un contenedor creado a mano
(`docker start jd-to-resume-backend`, imagen de 2,75 GB que reinstalaba
Chromium en cada arranque) y el frontend corría en el host con
`npm run dev`. No había `Dockerfile` ni `docker-compose.yml` en el repo, así
que el arranque no era reproducible.

- **`backend/Dockerfile`** — multi-stage. La etapa de build crea un venv,
  instala `requirements.txt` + `requirements-dev.txt` y descarga el
  navegador con `playwright install chromium --only-shell`; la etapa final
  copia solo el venv, los binarios del navegador y el código, e instala las
  librerías de sistema (`playwright install-deps`, `fonts-freefont-ttf`,
  `fonts-dejavu-core`). Sin compiladores, sin caché de pip, sin listas de
  `apt` en la imagen final. Corre como usuario no-root (`appuser`,
  uid 10001) y trae `HEALTHCHECK` contra el endpoint raíz.
- **`frontend/Dockerfile`** — multi-stage: `node:24-alpine` compila el
  bundle con `npm ci` + `npm run build` (que corre `tsc -b`, así que un
  error de tipos rompe el build) y `nginx:1.27-alpine` sirve el resultado.
- **`frontend/nginx.conf`** — sirve la SPA y hace de proxy inverso de
  `/api` hacia `backend:8000`. Como todo queda en el mismo origen, el
  bundle de producción usa URLs relativas (sin CORS, sin recompilar por
  entorno) y el `download_url` relativo que devuelve el backend
  (`/api/download/<archivo>.pdf`) resuelve sin cambios. `proxy_buffering
  off` + `chunked_transfer_encoding on` preservan el streaming SSE de
  `/api/generate`, y `try_files` resuelve el fallback de la SPA.
- **`backend/.dockerignore` y `frontend/.dockerignore`** — fuera del
  contexto de build quedan `.env` (y cualquier `.env.*`), `node_modules/`
  (~200 MB), `dist/`, `__pycache__/`, `.pytest_cache/`, `output/`,
  `rendercv_output/`, `*.pdf` y `*.log`. Nada de eso llega al daemon ni se
  hornea en una capa.
- **`compose.yaml`** — orchestra ambos servicios: `env_file:
  ./backend/.env` inyecta las credenciales **en tiempo de ejecución**
  (nunca en la imagen), el volumen `jd-to-resume-output` persiste los PDFs
  y las fotos fuera del contenedor, y `depends_on: condition:
  service_healthy` evita la ventana de error al arrancar. El backend
  publica el 8000 y el frontend el 5173, igual que antes.
- **`backend/requirements-dev.txt`** — `pytest` y `pytest-asyncio`
  fuera de las dependencias de runtime, para poder correr la suite dentro
  del contenedor (`docker compose exec backend pytest`).
- **`backend/.env.example`** — plantilla sin secretos; documenta las
  variables que el README ya describía.
- **`.gitignore`** — se añadió la excepción `!requirements-dev.txt`: el
  patrón global `*.txt` lo estaba ignorando y el archivo no habría
  llegado al repo.

### Optimización de tamaño de imagen

El primer build dio una imagen de backend de **2,76 GB**. Dos hallazgos
medidos con `docker history` la bajaron a **2,03 GB (-27 %)**:

- **Chromium headless shell en vez del Chromium completo.**
  `playwright install chromium` descarga *dos* navegadores: el Chromium
  completo (~403 MB) y el `chromium_headless_shell` (~273 MB). Contrary
  a lo que sugiere `chromium.executable_path`, Playwright 1.64 lanza el
  **headless shell** para `launch(headless=True)` sin `channel=`. Como
  los cuatro `launch()` del backend son headless y ninguno pasa
  `channel=`, el Chromium completo era peso muerto: `--only-shell`
  descarga solo el binario que se usa. *(El primer intento fue el
  inverso —borrar el headless shell— y rompió el render con
  `Executable doesn't exist at .../chromium_headless_shell-1248/...`;
  el error de Playwright en los logs fue lo que lo dejó claro.)*
- **Purga de fuentes y Xvfb que Chromium headless nunca carga:**
  `fonts-unifont`, `fonts-wqy-zenhei`, `fonts-ipafont-gothic`,
  `fonts-noto-color-emoji` y `xvfb` (~75 MB). Se purgan en la *misma*
  capa que los instala, así que esos bytes nunca llegan a la imagen.

La imagen del frontend quedó en **74 MB** (bundle estático + nginx).

### Bug encontrado durante el build

La primera versión del Dockerfile del frontend fijaba `NODE_ENV=production`
en la etapa de build. `npm` omite las `devDependencies` cuando esa
variable está puesta, así que `tsc` no existía y el build fallaba con
`sh: tsc: not found`. La variable se quitó del stage de build (el bundle
se compila con las devDependencies instaladas).

### Verificación

- `docker compose up --build -d` → backend y frontend **healthy**.
- Generación real a través del proxy de nginx: HTTP 200 en 4,8 s, SSE
  completo (`Validating Input` → `Finished`).
- PDF descargado por `http://localhost:5173/api/download/...` (HTTP 200,
  `application/pdf`, 33 KB).
- Colores del PDF extraídos del content stream: `#000000` (cuerpo),
  `#1B3A5C` (acento navy) y `#49617D` (tono secundario) — el RenderCV
  y el render por Chromium aplican el mismo acento.
- Ruta Chromium (`theme=classic_html`): HTTP 200 en 0,65 s, PDF de 1
  página con 1.291 caracteres de texto seleccionable.
- **321 tests en verde dentro del contenedor** (24,59 s).
- UI de producción servida por nginx: landing y generador renderizan
  igual que el dev server, y el catálogo de plantillas + paletas llega
  desde el backend por el proxy del mismo origen.

## 2026-11-06 — Sesión "Color de acento + fixes de render"

**Tipo:** feature + bug-fix.

### Feature — Color de acento

- **Nuevo módulo `backend/design_palettes.py`**: seis paletas (azul
  marino, verde azulado, verde bosque, granate, ciruela, gris pizarra)
  más `none`. Es la fuente de verdad: tabla de colores, cálculo de
  contraste WCAG y variables CSS para el template HTML de Playwright.
- **Nuevo parámetro `accent`** en `/api/generate` y
  `/api/render-from-yaml`. Inyecta un bloque `design.colors` que
  RenderCV aplica sobre el color del texto. Valor desconocido → HTTP
  422.
- **Nuevo endpoint `GET /api/design-options`**: catálogo de plantillas
  y paletas. El frontend lo consume para pintar los swatches con el hex
  exacto que va a salir en el PDF, en vez de duplicar la tabla.
- **Selector "Color de acento"** en `AdvancedOptions.tsx`, justo debajo
  de "Plantilla" (misma decisión de diseño, mismo bloque visual).
- **Reglas ATS aplicadas**: el cuerpo del texto sigue negro, el color
  nunca va como fondo detrás del texto, los títulos de sección conservan
  negrita + cuerpo mayor + línea, el layout sigue en una sola columna y
  el PDF sigue siendo vectorial con capa de texto real.

### Feature — Cambiar solo el diseño (sin que la IA reescriba)

El pipeline siempre reescribe el CV con el LLM, así que cambiar la
plantilla obligaba a regenerar y devolvía **otro texto**, no el mismo CV
con otra piel.

- **Nuevo botón "🎨 Cambiar diseño (sin tocar el texto)"** en la tarjeta
  de resultado, con su propio panel (plantilla + color).
- **Nuevo hook `useRedesign`**: re-renderiza el YAML guardado del PDF
  actual vía `/api/render-from-yaml`, que **no llama al LLM**. Actualiza
  el preview y el link de descarga, y deja el diseño elegido como
  selección global.
- **Nuevo helper `src/lib/renderFromYaml.ts`**: una sola fuente de
  verdad para el POST a `/api/render-from-yaml`, ahora compartido entre
  el editor YAML y el rediseño (antes estaba duplicado).
- **Nuevo módulo `src/lib/designOptions.ts`**: el catálogo de
  plantillas y paletas se pide una sola vez y se comparte entre el picker
  de "Opciones avanzadas" y el panel de rediseño.

Medido sobre el flujo real de la UI: el PDF de la IA y el rediseñado dan
**1906 caracteres de texto extraído idénticos byte a byte** (258
palabras), 0 imágenes y el mismo rango horizontal. Solo cambian los
colores.

### Bugs

- **BUG-04**: `RenderCVAdapter.render()` llamaba `render_cv_with_rendercv(fit=...)`,
  pero la función espera `fit_single_page`. Era un `TypeError` latente
  que mandaba cualquier render por el adaptador al fallback de
  Playwright. Además el adapter ignoraba el `accent`.
- **BUG-05**: `PlaywrightHTMLAdapter` y la plantilla `classic.html.j2`
  tenían los colores `#000` hardcodeados, así que el acento no llegaba
  al fallback HTML. Ahora el template consume variables CSS
  (`--accent-body`, `--accent-strong`, `--accent-muted`, `--accent-rule`).

### Verificación

- **321 tests en verde** (252 previos + 69 nuevos en
  `backend/tests/test_design_palettes.py`).
- Renderizando **el mismo YAML** con y sin acento, el texto extraído del
  PDF es **idéntico carácter por carácter** (1867 chars en ambos casos):
  la capa de texto que lee el ATS no cambia, solo la tinta.
- Todos los tonos pasan WCAG AA (≥4.5:1) contra blanco; los acentos
  están entre 7.8:1 y 11.6:1.
- El flujo de rediseño verificado end-to-end en el navegador (abrir
  panel → elegir color → aplicar), comprobando que el texto del PDF
  resultante es idéntico al original y que el picker global se sincroniza.

### Trail de commits

- `fix(frontend): buffer SSE chunks so the final event is never dropped`
- `fix(backend): parse date ranges correctly and never emit an inverted pair`
- `fix(build): unblock pytest, the production build and the playwright dependency`
- `feat(prompts): forbid a references section in the generated CV`
- `feat(design): add ATS-safe accent palettes for the rendered CV`
- `feat(redesign): re-render the same CV with another design, without the LLM`

---

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
