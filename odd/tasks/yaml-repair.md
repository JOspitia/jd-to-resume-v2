# Feature: AI-assisted YAML repair

> Botón "🤖 REPARAR YAML (IA)" en el panel del editor YAML. Cuando la edición manual rompe
> la sintaxis o el schema del YAML, el backend lo valida localmente y, si no pasa, manda al
> LLM para que lo arregle sin perder datos factuales.

Branch de trabajo: `feat/yaml-editor` (sale de `feat/multi-domain-tailoring` HEAD).
Doc base que extiende: `yaml-editor-restore.md` (el feature original).

## Specs

**S1** — Botón nuevo en el panel del editor YAML, ubicado entre "VALIDAR YAML" y el cierre del bloque de botones. Etiqueta `🤖 REPARAR YAML (IA)`. Color de UI: púrpura suave (`bg-purple-100`), diferenciable del resto.

**S2** — Al clickear el botón, `POST /api/repair-yaml` recibe `yaml_content` (el contenido actual del textarea) y opcionalmente `domain_game` (para que la IA use el vocabulario del dominio si necesita rebuildear lists).

**S3** — Validación local de dos pasadas (cheap, sin LLM):
   1. `yaml.safe_load` → captura errores de indentación, quoting, `:` faltantes, scalar donde se esperaba mapping.
   2. `GeminiResumeOutput` (Pydantic) → captura desajustes de schema (e.g. `experience` es `string` en lugar de lista, falta `points` en una entrada, etc.).
   Si las dos pasan → devolver el YAML sin tocar con `{ok: true, repairs: ["YAML válido — sin cambios."], schema_errors: []}`. **No LLM call.**

**S4** — Si alguna validación falla, el backend manda al LLM un prompt estricto:
   - Recibe el YAML roto + lista de errores reportados.
   - El LLM responde SOLO el YAML reparado (no prosa, no ``` fences — fences se strippean por `_strip_yaml_fences`).
   - Se vuelve a validar el output del LLM.
   - Si pasa → devolver YAML reparado con `repairs` describiendo el cambio.
   - Si NO pasa → devolver el YAML parcial con `ok: false`, `schema_errors: [...]` poblado para que el usuario termine manual.

**S5** — Defaults respetados: la validación local aplica los mismos defaults que `render_from_yaml` antes de invocar Pydantic, para no rechazar YAMLs que omitan campos opcionales (email, portfolio, etc.). Solo errores estructurales pasan a la fase LLM.

**S6** — Frontend actualiza el textarea con la respuesta (`yaml` del JSON), muestra banner púrpura con `repairs`/`schema_errors`, y limpia `yamlError` al inicio. Si la red falla, el banner de error se muestra como `yamlError` (lo mismo que ya existía para errores de parse).

**S7** — NO modifica factual content (nombres, fechas, escuelas, herramientas, métricas). Esto está reforzado en el prompt del LLM y es la SLA más importante de esta feature: si la IA inventa datos, falla el feature.

## Tasks (work-unit commits)

- **T1** · *Backend: endpoint /api/repair-yaml + helpers locales* · specs: S3, S4, S5
   - Endpoint POST que toma `yaml_content`, `domain_game` opcional.
   - Helpers `_parse_yaml_safe`, `_validate_yaml_schema`, `_strip_yaml_fences`, `_YAML_SCHEMA_DESCRIPTION`, `_ask_llm_to_repair_yaml_async`.
   - Two-pass: local first, LLM only when needed.
   - Commit: `feat(yaml): add /api/repair-yaml endpoint with two-pass validation`.

- **T2** · *Frontend: handleRepairYaml + botón púrpura* · specs: S1, S6
   - States nuevos: `yamlRepairing`, `yamlRepairNotice` (top-level del componente, no en callback).
   - Handler: POST al endpoint, reemplaza contenido del textarea, muestra banner con cambios aplicados.
   - Botón entre "VALIDAR YAML" y el cierre del bloque; deshabilitado mientras `yamlRepairing=true`.
   - Banner inline púrpura debajo de los botones para `yamlRepairNotice`.
   - Commit: `feat(yaml): add REPARAR YAML (IA) button + handleRepairYaml`.

- **T3** · *Fix TypeScript en handlers existentes* (drive-by, mismo PR o commit aparte)
   - `handleValidateATS` ahora toma `(overrideFile?: File | null)` y los `onClick` directos rompen TS. Los handlers `onClick` de los dos botones ATS manuales se envuelven en `() => handleValidateATS()`. Pre-existente en el archivo, no introducido por este feature.

## Log

- **L1** (input): "debería de validar que si haya quedado bien estructurado y solicitar a la ia realizar correcciones en caso de que se haya dañado el formato".
- **L2** (decisión): botón explícito, no auto-repair silencioso. La reparación cambia el contenido del textarea sin avisar al usuario (es lo que el feature implica), pero el flag UI lo hace consciente.
- **L3** (decisión): validación en 2 pasadas (syntax + schema). Solo escalate a LLM si las 2 locales fallan. Cero LLM-call cuando el YAML está OK.
- **L4** (decisión): los defaults del renderer se aplican ANTES de validar schema, para no generar LLM-calls innecesarios por campos opcionales faltantes.
- **L5** (verificación): tested localmente:
   - YAML válido con campos mínimos → `ok=true, repairs=["YAML válido — sin cambios."]`.
   - YAML con syntax error (`- company: acme\n  - role: dev` mal indented) → caught en `yaml.safe_load`, mensaje de indentación.
   - YAML con schema mismatch (`experience: "developer at acme"` string en vez de list) → caught en `GeminiResumeOutput`, `Input should be a valid list`.
   - Top-level no-mapping (`- one\n- two`) → caught, mensaje claro.
   - `_strip_yaml_fences` elimina fences ```yaml ... ``` si la IA los emite igual.
- **L6** (issue encontrado durante implementación): `yaml.safe_load` no estaba en scope porque el archivo importa `yaml as _pyyaml` (para no chocar con `yaml_helpers`). Fixed el renombre en `_parse_yaml_safe`.
- **L7** (issue encontrado durante implementación): `_validate_yaml_schema` original llamaba `GeminiResumeOutput(**parsed)` sin defaults → 10 campos requeridos fallaban incluso con YAML válido. Fixed populando defaults primero.
