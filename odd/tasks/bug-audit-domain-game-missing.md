# Bug: `/api/analyze-ats` ignores `domain_game` — audit always tech

> Bug del feature `multi-domain-tailoring`. Síntoma: el usuario selecciona "Analistas de Contratación" en el selector de perfil y, al auditar el CV (manual o auto), el panel muestra keywords tech (Python, JavaScript, Java, React, Node.js) como faltantes. Mismatch total con el perfil HR activo.

## Root cause

`handleValidateATS` en `frontend/src/ToolApp.tsx:207` construye el `FormData` solo con `file` y `jd` — falta `domain_game`. El resto de handlers (handleGenerate, handleAuditYaml, handleRenderFromYaml, handleRepairYaml) ya propagan `domain_game` correctamente. Solo este handler quedó fuera.

El backend (`/api/analyze-ats` en `main.py:1474`) aceptaba domain_game ausente sin error: `get_game(None)` cae al `DEFAULT_GAME = "tech"` (`backend/domain_games/__init__.py:36, 54`). Resultado: la IA audita con vocabulario tech sin importar qué profile esté activo.

## Why this slipped past T8

El `test_yaml_endpoints.py:284-291` valida que `domain_game="marketing"` (no permitido) devuelva HTTP 422, pero NO cubre el caso positivo de `domain_game` válido propagándose al prompt. T8 del doc `multi-domain-tailoring` valida routing en `test_domain_routing.py`, pero el smoke manual con API keys (T11) está bloqueado por sandbox. Combinación → bug visible solo en runtime real, reportado por el usuario.

## Fix

Una sola línea en `frontend/src/ToolApp.tsx` (FormData de `handleValidateATS`):
```diff
  const formData = new FormData();
  formData.append("file", fileToAudit);
  formData.append("jd", jd);
+ // T6 of multi-domain: propagate the active profile so the backend builds
+ // the audit prompt with the right SKILL_TAXONOMY (hr_recruiting /
+ // psychology / tech). Without this, /api/analyze-ats falls back to the
+ // "tech" game and the LLM audits the HR CV against tech keywords.
+ if (domainGame) formData.append("domain_game", domainGame);
```

Cubre los 4 entrypoints que llaman a `handleValidateATS`:
1. Botón "📊 SOLO AUDITAR ATS" arriba (ToolApp.tsx:1146).
2. Botón "📊 AUDITAR MATCH ATS & DETECCIÓN IA" en la success card (ToolApp.tsx:1297).
3. Auto-validate cuando `autoValidateATS=true` después de generación (ToolApp.tsx:679).
4. Auto-audit post-render-from-YAML cuando ambos flags activos (ToolApp.tsx:347 + auditRenderedPdf fetch → handleValidateATS).

## Verification

`tsc --noEmit` pasa sin errores. La ruta sigue siendo:
- POST /api/analyze-ats con `domain_game=hr_recruiting`
- → `get_game("hr_recruiting")` → hr DomainGame con `skill_taxonomy_es = ["Selección & Reclutamiento", ...]`
- → audit prompt inyecta esa taxonomía como keywords esperadas
- → LLM devuelve missing_keywords dentro del dominio HR (no Python/JS/Java/etc).

`/api/analyze-yaml` ya estaba bien (verificado por grep: línea 393 `if (domainGame) formData.append('domain_game', domainGame)`).

## Recommendation

Agregar a `test_yaml_endpoints.py` (o un test nuevo):
- test_analyze_ats_propagates_domain_game: POST /api/analyze-ats con domain_game=hr_recruiting, mock call_llm_api, assert prompt contiene "Selección" y NO contiene "Python"/"JavaScript".

Sin un test así, el mismo bug puede volver al refactorear `handleValidateATS` o `domain_games/__init__.py`.

## Log

- **L1** (input user): "Aparece la siguiente novedad selecciono en profile analista de contratación, pero la validaciónd de ats me toma el de tecnología". Pegó el output completo del audit panel con `matched_keywords` HR (Excel, Power BI, SPSS) y `missing_keywords` tech (Python, JS, Java, React, Angular, Node.js), `ats_score=10%`.
- **L2** (verificación): grep + read del código. Confirmé que:
  - `domainGame` state existe y se setea con los botones del selector (ToolApp.tsx:21, 818, 833, 848).
  - `handleResetProcess` lo resetea a 'tech' (line 161).
  - `handleGenerate`, `handleAuditYaml`, `handleRenderFromYaml`, `handleRepairYaml` propagan `domain_game` en FormData.
  - `handleValidateATS` (el handler del audit manual y del auto-audit) NO lo propaga. Single point of failure.
- **L3** (backend sanity check): `get_game(None)` → `tech` por default. Confirmado en `domain_games/__init__.py:54`. Sin `domain_game` enviado, la auditoría siempre es tech.
- **L4** (fix aplicado): una línea en `handleValidateATS` con el comentario explicando por qué es importante.
