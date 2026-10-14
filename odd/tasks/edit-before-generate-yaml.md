# Feature: Edit AI response before generating CV (YAML editor)

## Goal
Let users review and edit the AI-generated YAML before the backend renders the PDF, gated by a checkbox in the input area.

## Specs
- S1: Add a checkbox labelled `Editar respuesta de la IA antes de generar el CV (formato YAML)` near the existing `Validar automáticamente match ATS` toggle.
- S2: When the checkbox is ON and the user clicks `GENERATE TAILORED RESUME`, the backend must stop after the LLM call and stream the parsed data as YAML to the frontend instead of rendering a PDF.
- S3: When the YAML is ready, render an editor panel with:
  - A monospace textarea pre-populated with the YAML (min-height 420px, resizable).
  - An inline error area for YAML parse failures (displayed above the action buttons).
  - A `Generar CV` primary button that POSTs the YAML to `/api/render-from-yaml` and reuses the same progress/download UI as `/api/generate`.
  - A `Descartar y regenerar YAML` secondary button that re-invokes `/api/generate` with the flag.
  - A `VALIDAR YAML (Sin generar CV)` button that POSTs the YAML to `/api/analyze-yaml` and renders results in the existing AUDITORÍA ATS panel — no PDF render.
- S4: On a successful render from `/api/render-from-yaml`, the YAML editor must close, `editBeforeGenerate` resets to false, and the rest of the success UI (PREVIEW, DOWNLOAD PDF, ATS audit) appears unchanged.
- S5: New backend dependency: `pyyaml` (already present in venv 6.0.3 — added to `requirements.txt` for future installs).
- S6: New endpoint `POST /api/render-from-yaml` accepts `yaml_content` (required), `theme`, `fit_single_page`, `page_break_section`, `jd`, `custom_instructions`. Reuses RenderCV/Playwright path. No LLM call.
- S7: Existing pipeline unaffected when `edit_before_generate=false` (or omitted).
- S8: New endpoint `POST /api/analyze-yaml` accepts `yaml_content` (required) and optional `jd`. Serializes the parsed YAML dict into a narrative plain-text representation and runs the same audit LLM prompt as `/api/analyze-ats`. No PDF render, no score-side-effects in `scoreHistory` other than a new entry labelled `YAML vN`.
- S9: Audit prompt body is now defined exactly ONCE in `_run_audit_against_text`. `_run_internal_audit`, `POST /api/analyze-ats`, and `POST /api/analyze-yaml` all delegate to it.

## Tasks
- T1: backend: extend `generation_pipeline` with `edit_before_generate` flag and YAML emission. → done
- T2: backend: extend `POST /api/generate` to accept and forward the new flag. → done
- T3: backend: add `POST /api/render-from-yaml`. → done
- T4: backend: add `pyyaml` to `requirements.txt`. → done
- T5: frontend: add state + checkbox + SSE handling for `yaml_ready` event. → done
- T6: frontend: add `handleRenderFromYaml` and `handleRegenerateYaml`. → done
- T7: frontend: render the YAML editor panel. → done
- T8: frontend: clean up new state in `handleResetProcess`. → done
- T9: frontend: when both `editBeforeGenerate` and `autoValidateATS` are on, audit the freshly rendered PDF (fetched via download_url) instead of the original upload. → done
- T10: backend: extract audit-prompt body into `_run_audit_against_text` and add helper `_serialize_resume_data_as_text` so all three audit paths share one source of truth. → done
- T11: backend: add `POST /api/analyze-yaml`. → done
- T12: frontend: add `handleAuditYaml` handler and `VALIDAR YAML` button in the YAML editor panel. → done

## Log
- L1: Original request: enable editing the AI-generated YAML/JSON before rendering the CV, via a checkbox, with a `Generar CV` button below the editor that performs the normal render.
- L2: User chose YAML format over JSON / structured-editor option (YAML is the most user-friendly for non-technical users per their feedback).
- L3: Architectural decision — split the flow into two endpoints so the LLM is called exactly once: `/api/generate?edit_before_generate=true` emits YAML over SSE and stops; `/api/render-from-yaml` is render-only with no LLM cost. Avoids duplicating the rendering path on the frontend.
- L4: Verified `python main.py` imports cleanly under the existing venv; `/api/render-from-yaml` registered. Verified `tsc --noEmit` passes on the frontend. Verified PyYAML 6.0.3 roundtrip preserves the `parsed_data` shape end-to-end.
- L5: User asked what happens when both checkboxes (autoValidateATS + edit YAML) are enabled. Confirmed it was a silent no-op previously. Chose option 1: audit the rendered PDF after "Generar CV" by fetching the file from the SSE download_url and passing it as a File override to `handleValidateATS`. Network failures are swallowed silently so the success card stays visible.
- L6: User asked for a way to validate the YAML without generating the CV. Implemented `/api/analyze-yaml` which serializes the YAML dict into a plain-text narrative and runs the same audit LLM. The audit prompt body was already duplicated between `_run_internal_audit` and `POST /api/analyze-ats`; extracted it into `_run_audit_against_text` and made both refactored call sites delegate, so the new endpoint stays consistent automatically. Verified `_serialize_resume_data_as_text` produces a clean narrative that mirrors what `extract_text` would return from a rendered PDF.
