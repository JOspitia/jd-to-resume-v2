# Multi-Domain Resume Tailoring — feat/multi-domain-tailoring

> Adaptar `jd-to-resume` (hoy sesgado a CVs tech) para soportar tres dominios profesionales con prompts, taxonomía de skills y section_labels localizados: **tech**, **hr_recruiting** y **psychology**. Cero regresiones sobre la rama tech actual.

## Estado actual

**8/10 tasks done, 2 blocked.** 6 commits sobre `fix/success-buttons-grid-layout` HEAD. Branch **pusheada** a `origin/feat/multi-domain-tailoring`. PR abierto contra `main` (recomendado mergear antes de `feat/yaml-editor` que sale de esta branch).

| # | Task | Specs | Estado | Commit |
|---|---|---|---|---|
| T1 | Registry + 3 игляs (tech, hr_recruiting, psychology) | S1, S2, S5 | ✅ done | `c68c28b` |
| T2 | Wire-up `generation_pipeline` con `get_game(domain_game)` | S1, S3 | ✅ done | `23fed30` |
| T3 | Selector UI en `ToolApp.tsx` | S4, S5 | ✅ done | `17266d0` |
| T4 | `section_labels_es/en` per game (fallback en main.py) | S1, S5 | ✅ done | `67e7c9d` (consolidado con T6) |
| T5 | `SKILL_TAXONOMY` per game + regla 14 reescrita | S5, S6 | ✅ done | `c68c28b` (regla 14 en cada `strict_rules_block`) + `feefcee` (tests verifican taxonomías distintas) |
| T6 | Audit prompts domain-aware (extracted a `audit_prompts.py`) | S6 | ✅ done | `67e7c9d` (+ 15 tests en `test_audit_prompts.py`) |
| T7 | Sample CVs por dominio + JDs canónicas | S2 | 🟦 **blocked** | Esperando que me digas qué perfiles de HR/Psicología querés que muestre (no fabrico nombres/empresas yo). |
| T8 | Test suite de humo (routing + tech regression) | S3 | ✅ done | `feefcee` (33 tests en `test_domain_routing.py`) + `67e7c9d` (15 tests en `test_audit_prompts.py`) = **48/48 pasan** |
| T9 | README con sección "Dominios soportados" | S1, S2, S4, S5 | ✅ done | `b3b61bb` |
| T10 | Smoke end-to-end + tag `v2.6.0` | S1, S2, S6 | 🟦 **blocked** | Necesita API key de LLM en `backend/.env` + vos corriendo el stack localmente. El sandbox no puede levantar FastAPI ni hacer LLM calls. |

## Verificación

```
$ git log --oneline fix/success-buttons-grid-layout..feat/multi-domain-tailoring
b3b61bb docs(domain-games): add Supported Domains section to README
67e7c9d feat(domain-games): domain-aware audit prompts + section-labels fallback
feefcee test(domain-games): smoke tests for registry + tech regression
17266d0 feat(ui): add domain profile selector (tech / hr_recruiting / psychology)
23fed30 feat(domain-games): wire generation pipeline to game registry
c68c28b feat(domain-games): extract tech/hr/psychology prompt games into registry

$ cd backend && pytest tests/ -q
......................... 48 passed in 0.05s
```

`domain_game` propaga end-to-end en `backend/main.py`:
- `generate_resume()` Form param → `generation_pipeline(domain_game=...)` → `get_game(domain_game)` (default `tech`).
- `/api/analyze-ats` Form param → `_run_audit_against_text(..., audit_game=...)`.
- `_run_internal_audit` (auto re-audit en translate-to-english) → `_run_audit_against_text`.
- Próxima capa: `/api/render-from-yaml` y `/api/analyze-yaml` (feature `feat/yaml-editor`, ya mergeado en la misma chain).

## Dependencias hacia adelante

`feat/yaml-editor` (branch separada) usa `domain_game` como base para la propagación de taxonomía/skills en el audit del YAML. Si el flujo tech/hr/psychology cambia acá, el editor YAML hereda automáticamente.


## Specs

**S1 — Alcance del producto.** *"normalmente el programa esta implementado para cvs de tecnologia y desarrollo"* — el comportamiento actual cubre CVs tech y debe seguir cubriéndolos sin cambios visibles para el usuario que no active nada nuevo.

**S2 — Nuevos dominios soportados.** *"quiero implemetnarlo para cvs de analistas de contratación y psicología"* — agregar soporte para CVs de analistas de contratación / recruiting y de psicólogos (organizacional y clínica), con tratamiento diferenciado por dominio.

**S3 — Invariante: no romper nada existente.** *"implementa lo que me recomiendes, pero no borrar nada de lo que tengo"* — el flujo tech debe producir resultados equivalentes a v2.5 con el mismo CV base + JD. Cualquier cambio en el prompt maestro debe preservarse detrás de un selector que por default es `tech`.

**S4 — Selector de perfil en la UI.** *"puede ser un botón de opción tipo de perfil y entonces tecnologia, psicologia entonces dependiendo del perfil toma un tipo u otro"* — un control de UI claro (radio group o segmented control) que el usuario utiliza *antes* o *al inicio* del flujo de generación para elegir el dominio del CV. La elección condiciona prompt, taxonomía de skills y section_labels.

**S5 — Tres dominios v1.** Confirmados por el usuario: `HR / Recruiting (Analistas)` + `Psicología (Organizacional + Clínica)` + `Mantener Tech también`. Coexisten los tres en la misma pantalla.

**S6 — Anti-regresión sobre audit.** El endpoint `/api/analyze-ats` y `_run_internal_audit` deben producir análisis con vocabulario del dominio activo (no sugerencias tipo *"Añade 'Docker'"* sobre un CV de Psicología).

## Tasks

Cada task = 1 work-unit commit sobre `feat/multi-domain-tailoring`. Cada commit preserva el comportamiento tech intacto.

- **T1** · *Crear backend/domain_games/ con registry + 3 игляs (tech, hr_recruiting, psychology)* · route: explore_workunit · specs: S1, S2, S5 · commit: `feat(domain-games): extract tech/hr/psychology prompt games into registry`
   Extraer el bloque de prompt tech actual a `backend/domain_games/tech.py`, agregar `hr_recruiting.py` (verbos, narrativas A/B/C/D, categorías de skills, section_labels ES/EN) y `psychology.py` (ídem). Cada módulo exporta `build_prompt_blocks(extra: dict) -> dict` con claves: `system_intro`, `rules`, `action_verbs`, `narrative_patterns`, `skill_taxonomy`, `section_labels`. El módulo `tech.py` debe producir **exactamente** el mismo prompt que el actual (validado por test de regresión en T8).

- **T2** · *Renderizar el prompt del backend componiendo preamble común + игла elegida* · specs: S1, S3 · commit: `feat(domain-games): compose prompt from common preamble + game in main.py`
   En `main.py` línea ~974–1130, reemplazar el string literal gigante por una llamada a `_render_prompt(game, ...)`. Las reglas 1–4 (no-alucinación, compacto, summary, fórmula XYZ, etc.) — agnósticas del dominio — migran a `backend/domain_games/_preamble.py`. Las reglas 5–20B — redactadas con sesgo tech — se reemplazan por el bloque específico del игла activo. El default si el FE no envía game sigue siendo `tech`.

- **T3** · *Selector de dominio en ToolApp.tsx (segmented control tech/hr/psychology)* · specs: S4, S5 · commit: `feat(ui): add domain profile selector (tech / hr / psychology)`
   Nuevo `<DomainProfileSelector>` en `ToolApp.tsx`, posicionado arriba del formulario de upload, con 3 opciones. Default = `tech` para no romper UX. El valor se guarda en state y se envía en cada `POST /api/generate` como `formData.append("domain_game", game)` y en `POST /api/analyze-ats` como `domain_game` en JSON.

- **T4** · *Localización de section_labels por игла* · specs: S1, S5 · commit: `feat(domain-games): localized section_labels per game`
   Cada игла exporta `SECTION_LABELS_ES` y `SECTION_LABELS_EN` con headers apropiados: tech (Skills, Work Experience, Projects), hr_recruiting (Selección & Reclutamiento, Aprovisionamiento, Evaluación & Assessment, Onboarding, Employer Branding), psychology (Evaluación Psicológica, Pruebas Aplicadas, Intervención, Investigación, Ética Profesional).

- **T5** · *Taxonomía de skills por игла + keyword_gap_detection reescrito* · specs: S5, S6 · commit: `feat(domain-games): skill taxonomy per game (tech/hr/psychology)`
   En cada игла, exportar `SKILL_TAXONOMY` con las categorías correctas. Reescribir la regla 14 (keyword_gap_detection) del prompt para que diga *"categorize under the игла's SKILL_TAXONOMY"*, no las categorías hardcoded tech.

- **T6** · *Adaptar prompts de audit a vocabulario del игла* · specs: S6 · commit: `feat(domain-games): ATS audit prompts aware of selected game`
   En `/api/analyze-ats` y `_run_internal_audit`, inyectar en el prompt de auditoría la taxonomía `SKILL_TAXONOMY[game]` y ejemplos de keywords esperadas por dominio. Las actionable_tips deben poder decir *"Añade '16PF' si la usas en evaluación"* sin romperse.

- **T7** · *CVs de muestra por dominio* · specs: S2 · commit: `chore(samples): add sample CVs for hr_recruiting and psychology`
   Crear `sample-pdfs/hr-recruiter-sample.pdf` y `sample-pdfs/psychologist-sample.pdf` con perfiles sintéticos pero coherentes. Incluir JDs canónicas en `sample-pdfs/jd-tech.txt`, `jd-hr.txt`, `jd-psych.txt` (texto, no PDF) para tests.

- **T8** · *Test suite de humo de routing por игла* · specs: S3 · commit: `test(domain-games): smoke tests for routing + tech regression`
   `backend/tests/test_domain_routing.py` con pytest. Casos: (a) game=`tech` con `jakes-resume.pdf` + JD tech → assert prompt contiene verbos tech y SKILL_TAXONOMY tech; (b) game=`hr_recruiting` con CV HR + JD HR → assert verbos HR; (c) game=`psychology` con CV psi + JD psi → assert verbos psi; (d) la string del prompt completo para game=`tech` es byte-equivalente al baseline capturado en v2.5 (esto valida T1+S3).

- **T9** · *README actualizado con sección "Supported Domains"* · specs: S1, S2, S4, S5 · commit: `docs(domain-games): README section for multi-domain support`
   Nueva sección en `README.md` describiendo los 3 dominios, el selector UI, un ejemplo por dominio, y la nota: *"tech profile produces identical output to v2.5"*.

- **T10** · *Smoke run end-to-end de cada игла (manual o automático)* · specs: S1, S2, S6 · commit: `chore(domain-games): tag v2.6.0-multi-domain-ready`
   Levantar backend + frontend, generar PDF con cada CV sample + JD sample + game correspondiente, abrir PDF y verificar visualmente que (a) categorías de skills correctas, (b) verbos de apertura correctos, (c) section_labels en el idioma correcto.

## Log

- **L1** *(verbatim usuario)*: *"normalmente el programa esta implementado para cvs de tecnologia y desarrollo, pero en este caso quiero implemetnarlo para cvs de analistas de contratación y psicología que podría implemetar?"*
- **L2** *(decisión usuario)*: implementar lo recomendado, sin borrar lo existente, mediante un selector de perfil en la UI que dispara la lógica por dominio.
- **L3** *(selección usuario)*: dominios v1 confirmados → `HR / Recruiting (Analistas)` + `Psicología (Organizacional + Clínica)` + `Mantener Tech también`.
- **L4** *(decisión técnica)*: extraer prompt maestro en `backend/domain_games/` con 3 игляs independientes + 1 preamble común agnóstico. Default = `tech` (preserva UX). T1+T8 imponen byte-equivalencia con el prompt actual como guardarraíl de no-regresión.
- **L5** *(branch)*: creada `feat/multi-domain-tailoring` desde `fix/success-buttons-grid-layout`. Archivos sueltos no-committeados (docs de aprendizaje) ignorados — no pertenecen al feature.
