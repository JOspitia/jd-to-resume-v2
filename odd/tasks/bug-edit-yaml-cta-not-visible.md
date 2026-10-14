# Bug: Edit YAML CTA invisible después de una generación directa

> Síntoma: el CTA "✏️ Editar YAML directamente" en la success card no aparecía después de generar un CV con el flujo NORMAL (sin marcar "Editar antes de generar"). Solo aparecía si el usuario había pasado por el modo edit-before-generate. Reportado por el usuario: "se evidencia solo estas opciones Resume Generated! … PREVIEW / DOWNLOAD / AUDITAR / Translate / NUEVO … no la de editar yml".

## Root cause

El CTA está condicionado a `lastGeneratedYaml` truthy:

```jsx
{ lastGeneratedYaml && (
  <button onClick={ handleReopenYamlEditor } ... > ✏️ Editar YAML directamente </button>
) }
```

Pero `lastGeneratedYaml` solo se populaba desde `handleRenderFromYaml` (línea 327 de ToolApp.tsx):

```js
if (yamlContent) {
  setLastGeneratedYaml(yamlContent);
}
```

`handleGenerate` (el flujo principal cuando `editBeforeGenerate=false`) **nunca** snapshotteaba el YAML, porque el backend en ese modo emite solo `download_url` y nunca le pasa el YAML al frontend. Resultado: CTA invisible tras una generación directa.

Cuando el usuario marcó "Editar antes de generar" → el backend emite `yaml_ready` → el frontend populaba `yamlContent` (visible en el editor) → el usuario editaba → hacía click en "Generar CV" → `handleRenderFromYaml` corría → snapshotteaba `lastGeneratedYaml` → CTA visible. Pero ese era solo el 50% del flujo.

## Fix

Dos cambios sincronizados:

### Backend `main.py:1367`
Emitir el YAML también en el evento SSE `Finished` (no solo en el `yaml_ready` del path edit-before-generate):

```diff
+ yaml_payload = _yaml_safe_dump_unicode(parsed_data)
  yield f"data: {json.dumps({'step': 'Finished', 'progress': 100,
      'download_url': f'/api/download/{output_filename}',
      'audit_scores': audit_scores,
-     'translation': translation_meta})}\n\n"
+     'translation': translation_meta,
+     'yaml': yaml_payload})}\n\n"
```

El serializador `_yaml_safe_dump_unicode` ya estaba importado (de `yaml_helpers`). ~2-5KB extra en la línea SSE.

### Frontend `ToolApp.tsx:684` (SSE loop en `handleGenerate`)
Capturar `data.yaml` cuando llega el `download_url`:

```diff
                  if (data.audit_scores) { ... score history ... }

+ // Snapshot the YAML that produced this PDF so the user can re-open
+ // the editor after a non-edit-before-generate pass. The backend emits
+ // `data.yaml` on the Finished event for the direct path; the
+ // edit_before_generate path returns earlier with its own yaml_ready
+ // event and snapshots there.
+ if (typeof data.yaml === 'string' && data.yaml) {
+   setLastGeneratedYaml(data.yaml);
+ }
```

## Verification

- `python main.py` importa OK.
- `tsc --noEmit` pasa sin errores.
- Flujo end-to-end (manual):
  1. Subir PDF + seleccionar profile.
  2. Click "GENERATE TAILORED RESUME" (sin marcar edit-before-generate).
  3. Backend corre LLM → renderiza PDF → emite `Finished` con `download_url` + `yaml`.
  4. Frontend captura `data.yaml` → `setLastGeneratedYaml(...)`.
  5. Success card aparece con el CTA "✏️ Editar YAML directamente" arriba, justo después de "Resume Generated!".
  6. Click → editor YAML se reabre con el contenido del PDF recién renderizado.

## Recommendation

Agregar test de regresión: assert que el SSE `Finished` event siempre incluye el campo `yaml` cuando el path es `edit_before_generate=false`. Sin ese test, el bug puede volver al refactorear `generation_pipeline`.

## Log

- **L1** (input): "se evidencia solo estas opciones Resume Generated! Your tailored… PREVIEW / DOWNLOAD PDF / AUDITAR MATCH ATS… Translate to English / NUEVO / LIMPIAR. no la de editar yml".
- **L2** (verificación): grep `lastGeneratedYaml` + lectura del código. Confirmé que el botón estaba gateado en `lastGeneratedYaml` truthy, y que el snapshot solo se hacía en `handleRenderFromYaml`, nunca en `handleGenerate`. La suposición errónea del feature anterior fue que el usuario siempre pasaría por el modo edit-before-generate — incorrecto, el modo default es el directo.
- **L3** (decisión de fix): emitir el YAML siempre en el Finished event es más limpio que exponer un endpoint `/api/get-yaml-for-pdf/{filename}` con fetch lazy. Y aprovecha que `audit_scores` y `translation` ya viajan en el mismo evento — el patrón ya está establecido. Costo en bandwidth: ~2-5KB por generación (aceptable).
- **L4** (issue evitado): al inicio pensé en leer `parsed_data` desde el backend para serializarlo a YAML en el frontend. Eso sería redundante — el backend YA tiene el `parsed_data` listo al momento del Finished event. Serializar del lado del backend es 1 línea vs pedirle al frontend que reciba el dict y lo serialice.
