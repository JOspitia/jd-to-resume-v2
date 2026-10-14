# Bug: "REPARAR YAML (IA)" destruye el texto y falla con `bad indentation of a sequence entry`

> Reportado por el usuario: editó el Resumen Profesional desde el formulario, el YAML quedó con `bad indentation of a sequence entry` (línea 26, col 2), al presionar REPARAR la IA devolvió un resultado degenerado y **el textarea quedó vacío — el trabajo manual se perdió**.

## Tres bugs, uno raíz

### BUG 1 — RAÍZ: `serializeFormDataToYaml` emitía YAML inválido

`frontend/src/lib/yamlFormData.ts`

```js
// ANTES — inconsistente
function fieldLine(key, value) { return `  ${key}: ${yamlString(value)}`; }
lines.push(`- ${fieldLine('category', s.category)}`);   // → "-   category: ..."  (col 4)
lines.push(`  items:`);                                  // → "  items:"          (col 2)
```

El prefijo `- ` (2 columnas) + los 2 espacios de `fieldLine` = 4 columnas, mientras el hermano `items:` iba a 2. **PyYAML es leniente y lo aceptaba; js-yaml es estricto y lo rechaza** con exactamente el error reportado. Por eso el bug solo se manifestaba en el frontend (validación con js-yaml) y el backend nunca lo veía.

Fix: contrato de indentación explícito con dos funciones:
- `fieldLine(key, value)` → sin indent (usada justo después de `- `).
- `siblingFieldLine(key, value)` → con `LIST_KEY_INDENT` (2 espacios).
- `LIST_KEY_INDENT = '  '`, `LIST_ITEM_INDENT = '    '` como constantes documentadas.

### BUG 1b — `key:` seguido de `[]` en línea separada

```js
lines.push('achievements:');
lines.push('[]');   // ← YAML inválido: "can not read an implicit mapping pair"
```

Fix: `achievements: []` en una sola línea. Aplicado a `education`, `skills`, `experience`, `projects`, `achievements`.

### BUG 1c — `yamlString` con regex heurístico

```js
// ANTES — no cubría comillas, backslashes, ni whitespace interno
if (/[:{}\[\],&*#?|<>=!%@`]/.test(s) || s !== s.trim()) return JSON.stringify(s);
```

El summary del usuario terminaba en espacio (`...equipos de trabajo. `) → disparaba `s !== s.trim()` → `JSON.stringify` envolvía en comillas dobles. Al re-parsear en modo bloque literal esas comillas quedaban como texto.

Fix:
```js
const YAML_UNSAFE = /[:#{}[\],&*?|<>=!%@`"'\n\r\t\\]|^[\s-]|[\s]$/;
```
Cubre comillas simples y dobles, backslash, whitespace al inicio y al final.

### BUG 1d — `yamlMultiline` usaba `|` (literal) en vez de `>-` (folded)

Un summary es un párrafo continuo. `|` preserva hard breaks que se renderizan mal en el PDF. Además la indentación era inhomogénea.

Fix: `>-` con todas las líneas indentadas 2 espacios (incluida la primera), y `.trim()` del input.

### BUG 2 — PÉRDIDA DE DATOS (el más grave)

`frontend/src/hooks/useYamlEditor.ts:350`

```js
setYamlContent(data.yaml);   // incondicional — si el LLM devuelve basura, se pierde todo
```

No había backup. Si la reparación fallaba o devolvía un documento casi vacío, el texto del usuario desaparecía sin recuperación posible.

Fix:
1. `yamlBackup` state — snapshot **antes** de llamar al LLM.
2. El textarea **nunca** se toca en camino de error (`return` antes de `setYamlContent`).
3. Guard degenerado: si la respuesta tiene menos de `max(3, 40% de las líneas originales)`, se rechaza — evita aceptar un `name:` suelto que borraría el CV.
4. Botón **"↩ Deshacer reparación"** (`handleRestoreYamlBackup`) siempre disponible mientras haya backup.

### BUG 3 — Sin formateo (todo en una línea)

El LLM frequently responde JSON, que es YAML válido, así que pasaba todas las validaciones pero llegaba al textarea como una sola línea ilegible.

Fix (backend `main.py`): tras validar, re-serializar siempre con `_yaml_safe_dump_unicode(...)` para normalizar a estilo bloque.

## Verificación

Roundtrip con el texto exacto del usuario, compilado con `tsc` y parseado con **ambos** parsers:

| Check | js-yaml (strict) | PyYAML (backend) |
|---|---|---|
| `name` / `email` | PASS | PASS |
| summary preservado | PASS | PASS |
| skill con `:` + espacio (`Sistemas ATS: Greenhouse`) | PASS | PASS |
| skill con `#` (`Excel # avanzado`) | PASS | PASS |
| bullet con `:` (`Lideré: procesos de selección`) | PASS | PASS |
| bullet con `%` (`Reduje 40% el tiempo`) | PASS | PASS |
| listas anidadas (education/skills/experience/projects) | PASS | PASS |
| `achievements: []` | PASS | PASS |

`tsc --noEmit` limpio. Backend importa OK.

## Fix 2 — Auto-repair en `Generar CV` con las mismas protecciones

El auto-repair **ya existía** en `handleRenderFromYaml` (líneas 98-156): si `validateYaml` fallaba, llamaba a `/api/repair-yaml` antes de renderizar. Lo que faltaba eran las protecciones que agregamos al botón manual — por eso el auto-reparar podía perder texto igual de fácil.

Cambios aplicados:

1. **Backup antes del LLM** — `setYamlBackup(preRepairYaml)`.
2. **Guard degenerado** — misma regla que el botón manual: rechazar si la respuesta tiene < `max(3, 40% de las líneas originales)`.
3. **Mensajes honestos** — todos los caminos de error ahora dicen explícitamente *"Tu texto NO se perdió"* y ofrecen *"Deshacer reparación"*.
4. **Banner visible durante el auto-repair** (`YamlEditorPanel.tsx`) — spinner + texto *"Detectamos un error de formato en tu YAML. La IA lo está reparando automáticamente antes de generar el CV — no perdiste nada."* Para que el usuario entienda la demora en vez de pensar que la app se colgó.
5. **Contexto del error** — el mensaje de fallo ahora incluye tanto el error original (`validation.line`) como el de la reparación fallida (`reparValidation.line`), para que el usuario vea exactamente qué cambió y qué no se pudo arreglar.

Flujo resultante:

```text
Generar CV
  ├─ validateYaml OK → render directo
  └─ validateYaml falla
       ├─ setYamlBackup(texto)              ← snapshot seguro
       ├─ banner "la IA lo está reparando"
       ├─ POST /api/repair-yaml
       ├─ respuesta inválida  → error + NO se toca el textarea + backup intacto
       ├─ respuesta degenerada → error + NO se toca el textarea + backup intacto
       └─ respuesta OK        → setYamlContent(reparado) → render
```

## Nota sobre el prompt de reparación

También se agregó al prompt del LLM la instrucción explícita de block scalars (`>-` / `|-`) para texto multilínea, con el ejemplo de tu caso exacto. Es defensa en profundidad: el serializer ya no genera el problema, pero si el usuario edita el YAML crudo a mano y parte una línea, el LLM ahora sabe convertirla a block scalar.

## Log

- **L1** (input): *"aparece un error en la opción REPARAR YAML (IA)... al yo modificarlo desde el formulario quedaría así 'Psicóloga Organizacional con más de 2 años...' ... me parece el error 'Error de sintaxis YAML (línea 26, columna 2) bad indentation of a sequence entry' ... al hacerlo me aparece el siguiente error y me borrar el yaml 'Cambios aplicados: Local validation rejected the YAML...' ... tampoco lo formatea es decir sale todo en 1 linea"*.
- **L2** (hipótesis inicial, INCORRECTA): sospeché que el summary multilínea era la causa. Lo reproduje con PyYAML y **parseó bien** — un plain scalar con continuación indentada es YAML válido. Descarté la hipótesis.
- **L3** (hipótesis correcta): el mensaje de error del usuario citaba "línea 26" y el `bad indentation`, que es un error de js-yaml. El frontend valida con js-yaml (strict), el backend con PyYAML (lenient). Busqué la causa del desalineamiento entre ambos y la encontré en `fieldLine` + el prefijo `- `.
- **L4** (reproducción): compilé `yamlFormData.ts` con tsc y lo ejecuté contra js-yaml. Reproduje el error exacto: `bad indentation of a sequence entry (8:3)`. Confirmado.
- **L5** (fix iterativo): 3 rondas. (a) Separé `fieldLine` / `siblingFieldLine`. (b) Descubrí el segundo bug `key:` + `[]` en línea separada al testear. (c) Verifiqué con el texto real del usuario.
- **L6** (seguridad de datos): el bug de pérdida de datos era independiente del bug de sintaxis y más grave. Agregué backup + guard de salida degenerada + botón de restore antes de tocar nada del serializer, para que ninguna iteración de formatting pudiera destruir texto again.
- **L7** (limpieza): temporales de test eliminados. `git status` sin basura.
- **L8** (input): *"podrías poner que de igual una vez ejecutado el generar el cv para evitar cualquier tipo de error se aplique el auto reparar en caso de que hayan ingresado mal algo y no le hayan seleccionado reparar manualmente"*.
- **L9** (hallazgo): el auto-reparar **ya existía** en `handleRenderFromYaml` desde antes (líneas 98-156), disparado por `validateYaml`. El texto del panel ya lo prometía ("el botón Generar CV llama automáticamente a la IA"). Lo que faltaba eran las protecciones, no el mecanismo.
- **L10** (fix): paridad de seguridad entre el botón manual y el automático. Backup, guard degenerado, mensajes honestos y banner visible. Ver Fix 2.
