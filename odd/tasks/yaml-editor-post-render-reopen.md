# Feature: Post-render YAML re-edit

> Después de generar el CV, permitir volver a abrir el editor YAML con el contenido que produjo el PDF actual, editarlo, y regenerar. Cierra el ciclo iterativo: edit → render → re-open → edit again.

Doc base: `yaml-editor-restore.md` (T1–T11) + `yaml-repair.md`. Branch de trabajo: `feat/yaml-editor`.

## Specs

**S1** — Al completar un render exitoso (`handleRenderFromYaml` recibe `download_url`), copiar el `yamlContent` actual a un nuevo state `lastGeneratedYaml` antes de cerrar el panel. Esto preserva el YAML final (incluyendo ediciones manuales del usuario) en memoria, separado del `yamlContent` que se limpia al cerrar el panel.

**S2** — En la success card (la que muestra PREVIEW / DOWNLOAD PDF / AUDITAR / Translate to English), agregar un CTA prominente **"✏️ Editar YAML directamente"** entre la descripción "Resume Generated!" y la grilla de acciones secundarias. Solo se muestra cuando `lastGeneratedYaml` está poblado. Color emerald-600 sólido (CTA claro), `px-8 py-4` para que ocupe el lugar de acción principal, no secundario.

**S3** — Al clickear el botón, se llama `handleReopenYamlEditor`, que copia `lastGeneratedYaml` → `yamlContent`, pone `yamlReady=true`, limpia errores. Sin LLM call (memoria pura).

**S4** — El panel YAML existente (con todos sus 4 botones — Generar CV / Descartar y regenerar / VALIDAR YAML / REPARAR YAML-IA) reaparece. El usuario puede editar y volver a hacer `Generar CV` → el ciclo se repite.

**S5** — El header del panel YAML usa el botón "✕ Cerrar" pero ahora dispara `handleCloseYamlEditor`, que limpia `yamlContent`, `yamlReady`, `yamlError`, `yamlRepairNotice` y resetea `editBeforeGenerate`. La consistencia con `handleReopenYamlEditor` es importante: ambos operan sobre los mismos state flags.

**S6** — El botón "NUEVO / LIMPIAR" (que llama `handleResetProcess`) sigue siendo el ÚNICO camino para borrar `lastGeneratedYaml`. La razón es intencional: si reseteás todo, perdés también el snapshot del YAML — querés arrancar de cero.

## Tasks (work-unit commits)

- **T1** · *State + persistence en handleRenderFromYaml success path* · specs: S1, S3, S5
   - Nueva variable de estado: `lastGeneratedYaml: string | null`.
   - En el branch de éxito de `handleRenderFromYaml`: snapshot `yamlContent` → `lastGeneratedYaml`. Después clear `yamlContent = null`.
   - Cambiar `setYamlContent('')` a `setYamlContent(null)` para alinear con el type signature.
   - Commit: `feat(yaml-editor): snapshot rendered YAML so users can re-edit after generation`.

- **T2** · *handleReopenYamlEditor + handleCloseYamlEditor handlers* · specs: S3, S5
   - `handleReopenYamlEditor`: popula `yamlContent` desde `lastGeneratedYaml`, abre el panel. Edge case: si no hay snapshot, muestra error en `yamlError`.
   - `handleCloseYamlEditor`: limpia todos los flags relevantes. Reemplaza la lógica inline del botón "✕ Cerrar".
   - Commit: `feat(yaml-editor): reopen/close handlers for post-render iteration`.

- **T3** · *CTA prominente "Editar YAML directamente" arriba de la grilla* · specs: S2
   - Posición: entre el `<p>Your tailored, ATS - friendly PDF...</p>` y el `<div className="grid grid-cols-1 md:grid-cols-2 gap-4 w-full">`.
   - Render condicional `{ lastGeneratedYaml && <button ... /> }`.
   - Icono Code2 (ya importado de lucide-react).
   - Color emerald-600 sólido (`bg-emerald-600 text-white`), no emerald-50 (que era secundario y se perdía visualmente).
   - Sin `disabled` porque el padre `{ status === 'success' && ... }` ya limita cuándo se renderiza.
   - Commit: `feat(yaml-editor): prominent Editar YAML button on success card`.

## Log

- **L1** (input): "una vez ya generado el cv ya no puedo modificar le yml debería de abajo una vez ya generado la opción de modificar directamente el yml así como la opción de regenerar cv con mejoras seleccionadas, sería que tambien pueda modificar el yml y regenerarlo". En una segunda iteración: "una vez ya aparece Resume Generated! donde podría abrir el yml para editarlo? podría ser ahí la opción editar yml y que se pueda editar".
- **L2** (decisión): botón único ("Editar YAML directamente") en la success card. NO un toggle inline permanente — interfiere con el flujo de auditoría. La opción de regenerar con mejoras seleccionadas (`handleRegenerateWithFeedback`) sigue funcionando como atajo paralelo; este feature NO la duplica ni la reemplaza.
- **L2.1** (refinamiento de UX): la primera versión del botón era emerald-50 suave (`bg-emerald-50`) y vivía en la grilla de acciones. Se perdía visualmente entre PREVIEW / DOWNLOAD / AUDITAR / Translate. El usuario reportó "no veo cómo abrir el YAML después de generar". Subido a CTA prominente (emerald-600 sólido) entre la descripción y la grilla, lo que lo hace la acción principal post-generación. Color emerald-50 eliminado del archivo; el botón de la grilla eliminado; solo queda el de arriba.
- **L3** (decisión): snapshot en memoria (`lastGeneratedYaml`), no persistente. Si el usuario recarga la página se pierde. Persistirlo a localStorage sería útil para futuro pero está fuera de scope — la iteración inmediata no lo necesita.
- **L4** (issue TS encontrado durante implementación): `disabled={status === 'generating'}` fallaba con "comparison appears unintentional" porque el padre del botón está dentro de `status === 'success' && (...)`. Quitado el `disabled` — innecesario dado el render condicional del padre. Mismo patrón que los otros botones de la success card.
- **L5** (issue encontrado): `FileCode2` no estaba en los imports de lucide-react. Reemplazado por `Code2` (ya importado).
- **L6** (issue encontrado): consistencia con el botón "✕ Cerrar" — la versión inline anterior (`setYamlReady(false); setEditBeforeGenerate(false); setYamlError('')`) no limpiaba `yamlContent` ni `yamlRepairNotice`. Actualizado para usar `handleCloseYamlEditor` que limpia todo.
