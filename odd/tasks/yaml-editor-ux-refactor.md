# Frontend UX Refactor — visual layout + component extraction

> El `ToolApp.tsx` actual (post-extracción) tiene los hooks y componentes bien, pero el layout visual sigue siendo el mismo: todo apilado vertical, hero de 7xl, secciones sin jerarquía, AdvancedOptions "técnicamente" colapsable pero no se ve diferente. El usuario pidió reorganizar la UX, no solo extraer archivos.

Branch: `feat/ux-refactor`.

## Specs (resumidas)

**S1** — **Hero compacto**: el header "Perfect Your Resume. Beat the ATS." de 7xl pasa a header de 2xl-3xl en la parte superior. No ocupa 200px con copy de marketing.

**S2** — **Secciones numeradas con labels visuales**: cada bloque (PERFIL, TU CV, LA VACANTE, OPCIONES AVANZADAS, GENERAR) tiene un número + label en una `rm-tag` (neo-brutalist) y un `<h2>` semántico. El usuario sabe dónde está y qué falta.

**S3** — **Componente `Section` reutilizable** que envuelve cada bloque con el mismo estilo: `rm-box`, número + label en header, contenido children, y un slot `action` opcional (para botones como "Reset", "Limpiar" etc. que viven a la derecha del label).

**S4** — **AdvancedOptions verdaderamente colapsado por default**: el header de la sección tiene un toggle visible `▼ Opciones Avanzadas` / `▶ Opciones Avanzadas`. El cuerpo se oculta/expande con framer-motion. El 80% de los usuarios nunca lo abre. La preferencia se persiste en localStorage (key `jd-to-resume.advanced-options`) — primera vez abre, después recuerda.

**S5** — **Links en una fila**: GitHub | LinkedIn | Portfolio en línea horizontal con `flex-row gap-3`, no 3 filas separadas que duplican el espacio.

**S6** — **JD + Target Role juntos**: el target role es un input compacto arriba del JD textarea (no una sección separada). El JD ocupa el ancho completo con placeholder claro.

**S7** — **ActionBar sticky bottom**: el botón "Generar CV" está siempre visible abajo, `sticky bottom-0`, full-width, grande. z-index alto. El contenido del ToolApp tiene `pb-44` (padding-bottom) para que el contenido no quede tapado.

**S8** — **Sin acciones duplicadas en ActionBar**: el ActionBar SOLO tiene el botón Generate. Las acciones secundarias (Translate, Audit, Reset) viven en la success card (ResultsPanel) o como iconos discretos en el header. El usuario no necesita un menú de 4 botones en la barra inferior — eso compite visualmente con el CTA principal.

**S9** — **CvUploader con drop zone visual**: el área de upload es un cuadrado grande con borde dashed, icono central, texto "Arrastrá tu CV o hacé clic". Feedback visual al hover y al dragover.

**S10** — **ProfileSelector más visual**: iconos más grandes (24-32px en vez de 20px), descripción debajo del label, borde destacado cuando está seleccionado. Es el diferenciador del producto.

**S11** — **Cero cambios en el contrato HTTP**: mismas URLs, mismos FormData fields, mismo SSE parsing. Los hooks y componentes ya tienen la lógica; solo cambia el visual.

**S12** — **Responsive**: mobile-first. En `sm:` los inputs van full-width, en `md:` el grid de 2 columnas aparece, en `lg:` todo el contenido cabe con buen spacing.

## Tasks (work-unit commits)

| # | Task | Archivos | Specs |
|---|---|---|---|
| T1 | `Section` component (reutilizable) | `components/Section.tsx` | S2, S3 |
| T2 | `ToolApp.tsx` reescrito con layout nuevo (header compacto, secciones numeradas, sticky bottom) | `ToolApp.tsx` | S1, S2, S3, S7, S8 |
| T3 | `AdvancedOptions` con Collapsible visible y persistente | `components/AdvancedOptions.tsx` | S4 |
| T4 | `CvUploader` con drop zone visual | `components/CvUploader.tsx` | S9 |
| T5 | `JobContext` con links en una fila y target role arriba del JD | `components/JobContext.tsx` | S5, S6 |
| T6 | `ProfileSelector` con iconos grandes y borde destacado | `components/ProfileSelector.tsx` | S10 |
| T7 | `ActionBar` minimal (solo Generate, sticky bottom) | `components/ActionBar.tsx` | S7, S8 |
| T8 | `ResultsPanel` absorbe acciones secundarias (translate, audit, reset) | `components/ResultsPanel.tsx` | S8 |
| T9 | Verificación `tsc --noEmit` + responsive check | — | S12 |

## Lo que NO se toca

- `backend/` (ningún archivo).
- Las llamadas HTTP (URLs, FormData fields, SSE branches).
- Los hooks (useProfile, useGeneration, useYamlEditor, useAudit) — su lógica está bien.
- La lib/ de shadcn/ui primitives.

## Estructura final (post-este-commit)

```
frontend/src/
├── ToolApp.tsx                    # ~120 líneas: layout orquestador
├── components/
│   ├── Section.tsx                # NUEVO: wrapper reutilizable con número + label
│   ├── ProfileSelector.tsx        # visual mejorado
│   ├── CvUploader.tsx            # drop zone visual
│   ├── JobContext.tsx            # links en fila, target role arriba del JD
│   ├── AdvancedOptions.tsx        # Collapsible visible y persistente
│   ├── ActionBar.tsx             # minimal, sticky bottom
│   ├── GenerationProgress.tsx    # sin cambios funcionales
│   ├── ResultsPanel.tsx          # absorbe acciones secundarias
│   ├── YamlEditorPanel.tsx       # sin cambios funcionales
│   ├── AuditPanel.tsx            # sin cambios funcionales
│   └── ScoreHistory.tsx           # sin cambios funcionales
├── hooks/
│   ├── useProfile.ts
│   ├── useGeneration.ts
│   ├── useYamlEditor.ts
│   └── useAudit.ts
```

## Mejores prácticas React aplicadas

- **Component composition**: `Section` como wrapper reutilizable, los componentes específicos se componen dentro.
- **Custom hooks**: la lógica de negocio vive en los hooks; los componentes son presentational.
- **Semantic HTML**: `<section>`, `<header>`, `<h2>`, `<label>` con `htmlFor`.
- **Accessibility**: `aria-label`, `aria-expanded`, `aria-controls` en el Collapsible, focus management.
- **Responsive**: mobile-first con breakpoints `sm:`, `md:`, `lg:`.
- **No prop drilling**: los hooks viven en ToolApp, los componentes reciben props específicas (no pasan objetos completos).
- **Stable keys**: listas con keys únicos (file name, section number, etc.).
- **No magic numbers**: spacing con clases de Tailwind consistentes (`gap-3`, `space-y-4`, etc.).

## Log

- **L1** (input user): "necesito mejorar el ux desing del front al agregar tantas cosas perdio lo intuitivo, podrías en base a skills de diseño de react implementar de la mejor forma reorganizando todos los componentes para mejorar el ux desing, claro sin modificar las api del back que consumen para evitar cualquier tipo de daño".
- **L2** (decisión): adaptive layout (main flow + contextual panels). El subagente implementó extracción de hooks+componentes pero NO cambió el layout visual — los elementos siguen en las mismas posiciones.
- **L3** (feedback user): "no reubicaste ningun elemento de todos los que hay" — el subagente solo hizo refactor estructural. Falta el rediseño visual real.
- **L4** (decisión): layout con secciones numeradas, header compacto, AdvancedOptions verdaderamente colapsado, ActionBar sticky minimal, CvUploader con drop zone, JobContext con links en fila, ProfileSelector más visual.
- **L5** (no skill): las disponibles (`serviklapp-react`, `serviklapp-ux`) son del proyecto Serviklapp. Aplico principios generales de React/UX directamente.
- **L6** (validación de scope): ya tenemos hooks + componentes extraídos (commit anterior). Ahora solo cambia el JSX/className dentro de cada componente y el orden en ToolApp. Sin cambios de lógica.
