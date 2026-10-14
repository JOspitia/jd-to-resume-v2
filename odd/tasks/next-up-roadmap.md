# Roadmap — próximos sprints

> Documento estratégico — qué implementar después de `edit-before-generate-yaml`.
> Lee primero: `multi-domain-tailoring.md` (feature en curso) y `edit-before-generate-yaml.md` (recién cerrado).
> Este doc **no** es un work-unit. No tiene commit propio. Sirve para alinear prioridades antes de empezar el siguiente feature.

## TL;DR — el orden que recomiendo

1. Cerrar `multi-domain-tailoring` (T1–T10 ya definidos en su doc) **+ agregar 2 mejoras que migran a ese mismo branch**:
   - Simetría de `force_language` (soporte `es` además de `en`).
   - Persistencia del candidate profile (inputs completos en localStorage + import/export JSON).
2. Bootstrap de test suite mínima con golden prompts, anclada al T8 que ya está en `multi-domain-tailoring.md`.
3. Cancelar generación + retry desde último artefacto (Checkpoint = YAML editable ya implementado).
4. Audit preview en el path sin-edit (reuso del endpoint `/api/analyze-yaml` ya creado).
5. DOCX export desde el dict YAML.

NO hacer: reescritura de `main.py` fuera del multi-domain refactor, más providers LLM, multi-usuario/auth, rediseño UI, cover-letter generation.

---

## Sprint 1 — Multi-domain + base que arrastra

### Por qué primero
El prompt maestro monolítico en `main.py:974–1130` (~150 líneas con reglas 1–20B) ya cruzó el umbral de retorno decreciente. Multi-domain **obliga** la descomposición en registry: eso es lo único que permite después agregar idioma nuevo, taxonomía nueva, o dominio nuevo sin parchar el monolito. La regla `default = "tech"` + el byte-equivalence test (T8 del doc de multi-domain) son el seguro anti-regresión — no los toques.

### Tareas que migran al branch `feat/multi-domain-tailoring` (extender T1–T10)

**S1-fix. Simetría de `force_language`.**
- Hoy: `_build_language_override` solo se invoca con `target_language="en"` (en `main.py:787–850`).
- Mover la lógica a una función pura `_build_language_override(target_language, source_language)` sin asumir inglés.
- En `generation_pipeline`, eliminar la rama `if source_language == "en": raise ValueError("E_CV_ALREADY_ENGLISH")` — dejá que el LLM decida (la override ya le dice qué hacer).
- Sumar `force_language='es'` en el endpoint; cubrir el caso CV-inglés-pidiendose-español.
- Default de UI: ninguno. Solo aparece el botón "Translate" si `lastOutputLanguage !== target`.

**S1-persist. Candidate profile en localStorage + import/export.**
- Hoy: `handleResetProcess` borra el perfil y `localStorage.setItem('jd-to-resume.contact')` solo guarda GitHub/LinkedIn/Portfolio (`ToolApp.tsx:72–92`).
- Extender a: nombre, contacto completo, JD guardado del último intento, theme, fit_single_page, page_break_section, edit_before_generate, strict_edits_only, github/linkedin/portfolio, linkedin scrape flag.
- Botón nuevo en la UI: "Guardar perfil" / "Cargar perfil" / "Exportar perfil (.json)" / "Importar perfil (.json)".
- Botón "Exportar YAML" del último YAML generado → ciclo offline para iterar.

### Tests (T8 extendido)
- `tests/test_domain_routing.py` (ya en T8): 4 casos base.
- `tests/test_force_language_symmetry.py`: 2 casos (es→en, en→es) verificando que la override construya instrucciones equivalentes.
- `tests/test_audit_yaml_endpoint.py`: que `/api/analyze-yaml` produce el mismo shape que `/api/analyze-ats` y maneja YAML inválido con `{error: ...}` limpio.

---

## Sprint 2 — Quality of life

**S2-cancel. Cancelar generación + retry desde último paso.**
- `AbortController` ya está usado en `handleValidateATS` (`ToolApp.tsx:186–187`) — replicar el patrón en `handleGenerate` y `handleRenderFromYaml`.
- Botón "Cancelar" visible mientras `status === 'generating'`.
- El "retry" hoy se llama `handleRegenerateYaml` (ya existe). Lo único que falta es exponerlo como botón de reintento cuando el SSE muere por red, no por validación.
- Estado limpio: `setStatus('idle')` en el `abort()` handler.

**S2-audit-preview. Audit preview en path sin-edit.**
- Cuando `editBeforeGenerate=false` y el LLM ya respondió (entre "Analyzing with AI Model" y "Formatting Professional PDF"), exponer un botón "📊 Ver preview ATS ahora (sin esperar el PDF)".
- Reusa literalmente `handleAuditYaml` + el LLM ya responde al final del pipeline — bastaría con emitir el JSON en el SSE intermedio igual que `yaml_ready`, y un endpoint estado-less o cache.
- **Más simple**: dejar que termine el render del PDF y al final disparar el audit auto (eso ya funciona con `autoValidateATS`). Esta feature S2 es nice-to-have, no crítica.

---

## Sprint 3 — Expansión

**S3-docx. Export DOCX desde el dict YAML.**
- 30 líneas con `python-docx`. Bajo costo, alto valor para ATS viejos.
- Endpoint `POST /api/render-from-yaml?format=docx` o nuevo `POST /api/export-yaml-docx`.
- Header: nombre + contacto. Body: secciones en orden de `section_labels`.
- **No prioritario** hasta cerrar Sprint 1.

**S3-audit-vocab. Audit aware del dominio.**
- Ya está como T6 en `multi-domain-tailoring.md`. Asegurarse de que también:
  - `scoreHistory` etiquetá cada entrada con el dominio (`Tech v2`, `HR v1`, etc.) en lugar de solo `Original` / `Refinado vN` / `EN`.
  - `matched_keywords` / `missing_keywords` filtrados por la `SKILL_TAXONOMY[game]`.

---

## NO hacer — explícito

| Idea | Por qué no |
|------|------------|
| Reescribir `main.py` aparte del multi-domain refactor | Multi-domain T1–T2 ya arrastran el 60% del refactor. Hacerlo por separado es yak-shave. |
| Agregar más providers LLM / multi-usuario / auth | Es un tool local single-user. Cada hora ahí es hora robada al producto. |
| Rediseñar la UI / cambiar la librería de componentes | El rough-edgy aesthetic es firma de la herramienta. No pulir. |
| Cover-letter generation | Tentador pero agrega superficie por una feature que ~30% usaría. |
| LinkedIn job URL scraping | Nicho, bajo ROI. |
| Deploy público / seguridad hardening | No es el momento. Producto local. |
| Reescribir `extract_text` / `render_service` | Funciona; no tocar hasta que un test falle. |

---

## Pregunta bloqueante — RESUELTA

**`psychology` queda como UN game que cubre organizacional + clínica**; `hr_recruiting` queda como game aparte. Confirma los 3 games totales del T1 de `multi-domain-tailoring.md`:
- `backend/domain_games/tech.py`
- `backend/domain_games/hr_recruiting.py`
- `backend/domain_games/psychology.py`

**Implicancia**: el `SKILL_TAXONOMY` de `psychology.py` va a ser heterogéneo (mezcla assessment organizacional con intervención clínica). Categorías sugeridas para que no se rompa el flujo:
- *Evaluación Psicológica* (16PF, DISC, Wartegg, MMPI, WAIS, Rorschach)
- *Pruebas Aplicadas* (assessment centers, role-play, entrevistas por competencias)
- *Intervención Clínica* (TCC, cognitivo-conductual, psicofármacos básicos, DSM-5)
- *Investigación* (métodos cuantitativos/cualitativos, SPSS, R, análisis de datos)
- *Ética Profesional* (consentimiento informado, secreto profesional, supervisión clínica)

Los `section_labels` también valen los dos sub-ámbitos. Si más adelante duele, se bifurca en `psych_org.py` + `psych_clinic.py` sin romper la API (mismo registry, distinta key).

---

## Log

- **L1** (input usuario): "de lo que tenemos actualmente ademas de lo que voy a implementar [multi-domain-tailoring.md] que me recomendarías implementar o mejorar?"
- **L2** (decisión): multi-domain es la jugada correcta; agregar simetría de force_language y persistencia del profile en el mismo branch.
- **L3** (decisión): cancelación + retry desde checkpoint (YAML ya sirve como checkpoint) entra en Sprint 2, no bloquea multi-domain.
- **L4** (decisión): audit preview sin esperar el PDF es nice-to-have, no crítico.
- **L5** (resuelta): `psychology` queda como un solo game (organizacional + clínica juntos), `hr_recruiting` separado. Confirma T1 de multi-domain con 3 games totales (`tech`, `hr_recruiting`, `psychology`).
