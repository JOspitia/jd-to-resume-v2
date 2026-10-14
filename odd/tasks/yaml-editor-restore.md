# YAML Editor — restore + multi-domain integration

> Re-implementación del feature `edit-before-generate-yaml` que estaba
> WIP y se perdió durante el reset de ToolApp.tsx / main.py en el commit
> c68c28b del feature multi-domain.
>
> Branch: `feat/yaml-editor` (sale de `feat/multi-domain-tailoring` HEAD = b3b61bb).
>
> Decisiones de scope (acordadas con el usuario):
>   * Branch dedicado — PR separado del multi-domain.
>   * Domain-aware: el YAML editor respeta `domain_game` seleccionado.
>     `render-from-yaml` y `analyze-yaml` también reciben `domain_game`
>     para que el audit use el vocabulario del dominio.

## Estado actual

**9/11 tasks done, 2 blocked.** 10 commits sobre `feat/multi-domain-tailoring` HEAD. Branch **pusheada** a `origin/feat/yaml-editor`. PR sugerido: `feat/yaml-editor` → `main` (después de mergear `feat/multi-domain-tailoring`).

| # | Task | Specs | Estado | Commit |
|---|---|---|---|---|
| T1 | DRY refactor de audit prompt (`_run_audit_against_text`) | S9 | ✅ done | `b80680e` |
| T2 | `yaml_helpers` module + roundtrip tests | S8, S9 | ✅ done | `02351f7` (23 tests en `test_yaml_helpers.py`) |
| T3 | `edit_before_generate` flag + SSE `yaml_ready` event | S2, S5, S7 | ✅ done | `8c20c9d` |
| T4 | Endpoint `POST /api/render-from-yaml` | S6 | ✅ done | `40dffd8` |
| T5 | Endpoint `POST /api/analyze-yaml` (domain-aware) | S8, S10 | ✅ done | `a2782ea` |
| T6 | Frontend state + checkbox + SSE handler | S1, S2, S4 | ✅ done | `265e6ef` (tsc clean) |
| T7 | Editor panel con 3 botones + handlers | S3, S4 | ✅ done | `1fad68f` (tsc clean) |
| T8 | Audit-after-render cuando `autoValidateATS` está activo | S9 FE (WIP T9) | ✅ done | `7567c24` (tsc clean) |
| T9 | Endpoint tests con mocks (`test_yaml_endpoints.py`, 14 tests) | S6, S8, S9 FE | 🟦 **blocked** | Test file commiteado en `a218594`. Pytest falla en la colección porque los stubs `sys.modules` a nivel de módulo rompen `stop_global_capturing`. Fix: mover los stubs a `conftest.py`. |
| T10 | README con sección "Editor YAML (v2.7+)" | (doc) | ✅ done | `29ec8dd` |
| T11 | Smoke end-to-end + tag `v2.7.0` | S1, S2, S6 | 🟦 **blocked** | Necesita API key de LLM en `backend/.env` + vos corriendo el stack localmente + generando un PDF con el editor activo por cada dominio. El sandbox no puede levantar FastAPI ni hacer LLM calls. |

## Verificación

```
$ git log --oneline feat/multi-domain-tailoring..feat/yaml-editor
a218594 chore(yaml): add T9 endpoint test file + L6 verification note
29ec8dd docs(yaml): add YAML Editor section + update Endpoints table for v2.7
7567c24 feat(yaml): audit-after-render when autoValidateATS is on
1fad68f feat(yaml): editor panel with 3 action buttons + handlers
265e6ef feat(yaml): frontend state + checkbox + SSE handler for yaml_ready
a2782ea feat(yaml): add /api/analyze-yaml endpoint (domain-aware)
40dffd8 feat(yaml): add /api/render-from-yaml endpoint
8c20c9d feat(yaml): add edit_before_generate flag + SSE yaml_ready event
02351f7 refactor(yaml): extract yaml_helpers module + add roundtrip tests
b80680e refactor(audit): unify audit path in _run_audit_against_text

$ cd backend && pytest tests/ -q
............................ 48 passed in 0.05s

$ cd frontend && ./node_modules/.bin/tsc --noEmit --project tsconfig.json
(no output = 0 errors)
```

`domain_game` propaga end-to-end (heredado del feature multi-domain):
- `generate_resume()` lee `domain_game` del Form → emite `yaml_ready` con los `section_labels_es/en` del juego seleccionado.
- `render_from_yaml()` lee `domain_game` del Form → usa los `section_labels` del juego para los headers del PDF renderizado.
- `analyze_yaml()` lee `domain_game` del Form → compone el prompt de audit con la `SKILL_TAXONOMY` y seeds del juego (no 'add Docker' en CVs de Psi/HR).

## Dependencias

Este feature depende de `feat/multi-domain-tailoring` mergeado primero (T1 de yaml-editor usa `_run_audit_against_text` que vino del refactor de multi-domain). El orden de merge recomendado: multi-domain → yaml-editor → tag `v2.7.0`.


## Specs (verbatim de `edit-before-generate-yaml.md`)

**S1** — Checkbox labelled `Editar respuesta de la IA antes de generar el CV (formato YAML)` cerca del toggle `Validar automáticamente match ATS`.

**S2** — Cuando el checkbox está ON y el usuario clickea `GENERATE TAILORED RESUME`, el backend para después de la llamada LLM y streamea el `parsed_data` como YAML al frontend en lugar de renderizar el PDF.

**S3** — Cuando el YAML está listo, render del editor panel con:
   * textarea monospace pre-poblada con el YAML (min-height 420px, resizable).
   * área de error inline para fallos de parse (sobre los action buttons).
   * botón primario `Generar CV` que POSTea el YAML a `/api/render-from-yaml` y reusa la misma UI de progreso/descarga que `/api/generate`.
   * botón secundario `Descartar y regenerar YAML` que re-invoca `/api/generate` con el flag.
   * botón `VALIDAR YAML (Sin generar CV)` que POSTea el YAML a `/api/analyze-yaml` y renderiza resultados en el panel existente de AUDITORÍA ATS — no renderiza PDF.

**S4** — En un render exitoso de `/api/render-from-yaml`, el editor YAML se cierra, `editBeforeGenerate` resetea a false, y el resto de la UI de éxito (PREVIEW, DOWNLOAD PDF, ATS audit) aparece sin cambios.

**S5** — Nueva dependencia: `pyyaml` (ya presente en venv 6.0.3 — agregar a `requirements.txt` para installs futuras).

**S6** — Nuevo endpoint `POST /api/render-from-yaml` acepta `yaml_content` (requerido), `theme`, `fit_single_page`, `page_break_section`, `jd`, `custom_instructions`, `domain_game`. Reusa path de RenderCV/Playwright. Sin llamada LLM.

**S7** — Pipeline existente no afectada cuando `edit_before_generate=false` (u omitido).

**S8** — Nuevo endpoint `POST /api/analyze-yaml` acepta `yaml_content` (requerido) y `jd` opcional, `domain_game`. Serializa el dict parseado del YAML en una representación narrativa plain-text y corre el mismo prompt de audit LLM que `/api/analyze-ats`. Sin render PDF, sin side-effects en `scoreHistory` salvo una nueva entrada labelled `YAML vN`.

**S9** — Audit prompt body definido exactamente UNA vez en `_run_audit_against_text`. `_run_internal_audit`, `POST /api/analyze-ats`, y `POST /api/analyze-yaml` delegan ahí.

**S10 (nueva integración multi-domain)** — `domain_game` se propaga end-to-end:
   * `/api/generate` lee `domain_game` y emite YAML con los section_labels del juego.
   * `/api/render-from-yaml` lee `domain_game` y reusa la taxonomía del juego si la necesita para render.
   * `/api/analyze-yaml` lee `domain_game` y compone el prompt de audit con la taxonomía/skills del juego.

## Tasks (work-unit commits)

- **T1** — *DRY refactor de audit prompt* (S9)
   Extraer `build_audit_prompt` (ya en `audit_prompts.py`) en una helper `_run_audit_against_text(resume_text, jd_text, audit_game)` que hace prompt → call_llm_api → parse JSON → return dict. Refactor `_run_internal_audit` y `POST /api/analyze-ats` para delegar. Commit: `refactor(audit): unify audit path in _run_audit_against_text`.

- **T2** — *Tests del audit DRY + YAML serialize* (S8, S9)
   Tests para `_run_audit_against_text` (mocks), `_serialize_resume_data_as_text` (narrative output), roundtrip YAML preserve. Commit: `test(yaml): audit DRY + narrative serialize + yaml roundtrip`.

- **T3** — *PyYAML dep + edit_before_generate flag* (S2, S5, S7)
   Agregar `pyyaml` a `requirements.txt`. Modificar `generation_pipeline` para aceptar `edit_before_generate: bool = False`. Cuando True, después de la llamada LLM y antes del render, emitir SSE `yaml_ready` con `yaml` y retornar. No tocar el path cuando es False. Commit: `feat(yaml): add edit_before_generate flag + SSE yaml_ready event`.

- **T4** — *Endpoint /api/render-from-yaml* (S6)
   POST endpoint que acepta `yaml_content` (required), `theme`, `fit_single_page`, `page_break_section`, `jd`, `custom_instructions`, `domain_game`. Hace yaml.safe_load → `parsed_data` → reusa `render_cv_with_rendercv` (mismo path que `/api/generate` post-LLM). Commit: `feat(yaml): add /api/render-from-yaml endpoint`.

- **T5** — *Endpoint /api/analyze-yaml* (S8, S10)
   POST endpoint que acepta `yaml_content`, `jd`, `domain_game`. Serializa via `_serialize_resume_data_as_text`, llama `_run_audit_against_text` con el game, devuelve el dict de audit. Commit: `feat(yaml): add /api/analyze-yaml endpoint (domain-aware)`.

- **T6** — *Frontend state + checkbox + SSE handling* (S1, S2, S4, partial)
   Agregar `editBeforeGenerate` state en ToolApp.tsx. Checkbox cerca del toggle ATS. SSE handling del evento `yaml_ready` que viene de `/api/generate`. Incluir `edit_before_generate` en FormData. Reset del flag en `handleResetProcess`. tsc clean. Commit: `feat(yaml): frontend state + checkbox + SSE handler`.

- **T7** — *Frontend editor panel + 3 botones* (S3, S4)
   Render del editor panel con textarea monospace (min-h 420px resizable), área de error inline, 3 botones: `Generar CV`, `Descartar y regenerar YAML`, `VALIDAR YAML`. Handlers: `handleRenderFromYaml`, `handleRegenerateYaml`, `handleAuditYaml`. Cierre del editor en éxito de render, reset de flag. Commit: `feat(yaml): editor panel with 3 action buttons`.

- **T8** — *Audit-after-render cuando ambos flags activos* (S9 FE, partial T9 del spec)
   Si `editBeforeGenerate=true && autoValidateATS=true`, después de un render-from-yaml exitoso, fetch el PDF de `download_url` y llamar `handleValidateATS` con el File construido del blob. Network failure se swallow silencioso. tsc clean. Commit: `feat(yaml): auto-audit rendered PDF when both flags on`.

- **T9** — *Tests de endpoints nuevos + audit-after-render* (S6, S8, S9 FE)
   Tests para `/api/render-from-yaml` (valid YAML, invalid YAML, missing yaml_content), `/api/analyze-yaml` (con game=tech/hr/psychology, sin jd, con jd). Commit: `test(yaml): endpoint smoke tests for render-from-yaml and analyze-yaml`.

- **T10** — *README actualizado con sección YAML Editor* 
   Nueva sección en README describiendo el flujo del editor YAML, los 3 botones, y la integración con multi-domain. Commit: `docs(yaml): README section for YAML editor`.

- **T11** — *Smoke run end-to-end + tag v2.7.0*
   (Bloqueado por keys de LLM — el sandbox no puede levantar FastAPI ni hacer LLM calls. Documentado en todo.)

## Log

- **L1** (input): "restaurar toda esa funcionalidad [WIP-yaml] en base a lo que implementaste".
- **L2** (input): "...poder editar el text yml generado por la ia antes de generar el cv si se quiere ahcer alguna modificación o algo para evitar preguntar a la ia directamente se peuden hacer manuales".
- **L3** (decisión): branch `feat/yaml-editor` desde `feat/multi-domain-tailoring` HEAD.
- **L4** (decisión): YAML editor domain-aware; `domain_game` se propaga en los 3 endpoints.
- **L5** (recuperación de la pérdida): el WIP-yaml original (T1-T12 del doc viejo) se perdió cuando hice `git checkout HEAD -- frontend/src/ToolApp.tsx` durante T3 de multi-domain. Re-implementación desde el spec original.
- **L6** (validación independiente, esta session): verificación contra código actual en `feat/yaml-editor`. Back-end: `backend/main.py` registra los 3 endpoints nuevos (`/api/render-from-yaml`, `/api/analyze-yaml`, `/api/generate` con flag `edit_before_generate`) y `_run_audit_against_text` los unifica. `backend/yaml_helpers.py` extraído (157 líneas) con serializer y load/dump. Front-end: 24 referencias a los símbolos del feature en `ToolApp.tsx` — `editBeforeGenerate`, `yamlContent` tipado `string | null`, `yamlReady`, `yamlError`, `handleRenderFromYaml`, `handleAuditYaml`, `handleRegenerateYaml`, `auditRenderedPdf`, checkbox, panel con 3 botones. Tests: `backend/tests/test_yaml_helpers.py` (422 líneas) cubre roundtrip y serialize. Pendientes de este doc: T9 (smoke tests de los 2 endpoints con mocks) y T11 (smoke end-to-end con API keys, bloqueado por el sandbox). Los 9 commits en `git log --oneline -n 12` mapean 1-a-1 contra T2–T10 del doc.
