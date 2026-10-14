# Frontend UX Refactor — adaptive layout + component extraction

> El `ToolApp.tsx` actual tiene 1790 líneas con 30+ useState y 11 handlers. Se perdió lo intuitivo. Refactor a adaptive layout (main flow + contextual panels) sin tocar el backend.

Branch: `feat/ux-refactor` (sale de `feat/yaml-editor` HEAD = `46d8d3e`).

## Specs (resumidas)

**S1** — Adaptive layout, no stepper ni tabs ni solo-collapsible. El usuario ve el main flow siempre; los panels contextuales (YAML editor, audit) aparecen sobre el contenido cuando son relevantes.

**S2** — Advanced options colapsables por default. El 80% de los usuarios no tocan theme/page-break/auto-audit/edit-YAML; deben estar ocultos hasta que se necesiten.

**S3** — Bottom action bar fijo con el botón Generate siempre accesible, sin importar el scroll.

**S4** — Results area aparece debajo del main flow cuando hay output. No reemplaza nada; el usuario puede seguir editando inputs y volver a generar.

**S5** — YAML editor como panel full-width que se desliza sobre el contenido (AnimatePresence + fixed/overlay). No es una página nueva; el usuario puede cerrar con X y volver al main flow sin perder contexto.

**S6** — Cero cambios en el contrato HTTP: mismas URLs, mismos FormData fields, mismo SSE parsing, mismos callbacks de los hooks.

**S7** — ProfileSelector es el elemento más prominente (es el diferenciador del producto). No escondido en un "Advanced".

## Tasks (work-unit commits)

| # | Task | Archivos | Specs |
|---|---|---|---|
| T1 | `useProfile` hook | `hooks/useProfile.ts` | S1, S6 |
| T2 | `useGeneration` hook | `hooks/useGeneration.ts` | S1, S4, S6 |
| T3 | `useYamlEditor` hook | `hooks/useYamlEditor.ts` | S5, S6 |
| T4 | `useAudit` hook | `hooks/useAudit.ts` | S6 |
| T5 | `ProfileSelector` | `components/ProfileSelector.tsx` | S7 |
| T6 | `CvUploader` | `components/CvUploader.tsx` | S1, S6 |
| T7 | `JobContext` | `components/JobContext.tsx` | S1, S6 |
| T8 | `AdvancedOptions` (Collapsible) | `components/AdvancedOptions.tsx` | S2, S6 |
| T9 | `ActionBar` (sticky bottom) | `components/ActionBar.tsx` | S3, S6 |
| T10 | `GenerationProgress` | `components/GenerationProgress.tsx` | S4, S6 |
| T11 | `ResultsPanel` | `components/ResultsPanel.tsx` | S4, S6 |
| T12 | `YamlEditorPanel` | `components/YamlEditorPanel.tsx` | S5, S6 |
| T13 | `AuditPanel` | `components/AuditPanel.tsx` | S4, S6 |
| T14 | `ScoreHistory` | `components/ScoreHistory.tsx` | S4, S6 |
| T15 | `ToolApp.tsx` reescrito (~150 líneas) | `ToolApp.tsx` | S1-S7 |
| T16 | Verificación `tsc --noEmit` + smoke | — | S1-S7 |

## Lo que NO se toca

- `backend/` (main.py, audit_prompts.py, yaml_helpers.py, domain_games/, audit endpoints).
- Las llamadas HTTP: `/api/generate`, `/api/render-from-yaml`, `/api/analyze-ats`, `/api/analyze-yaml`, `/api/repair-yaml`, `/api/clear-cache`.
- El SSE parsing del backend.
- El contrato de `domain_game`, `edit_before_generate`, `autoValidateATS`, `lastGeneratedYaml`.
- La lib/ de shadcn/ui primitives.

## Estructura final

```
frontend/src/
├── ToolApp.tsx                    # ~150 líneas: orquesta hooks, compone layout
├── components/
│   ├── ProfileSelector.tsx
│   ├── CvUploader.tsx
│   ├── JobContext.tsx
│   ├── AdvancedOptions.tsx
│   ├── ActionBar.tsx
│   ├── GenerationProgress.tsx
│   ├── ResultsPanel.tsx
│   ├── YamlEditorPanel.tsx
│   ├── AuditPanel.tsx
│   └── ScoreHistory.tsx
├── hooks/
│   ├── useProfile.ts
│   ├── useGeneration.ts
│   ├── useYamlEditor.ts
│   └── useAudit.ts
└── lib/
    └── api.ts
```

## Log

- **L1** (input user): "necesito mejorar el ux desing del front al agregar tantas cosas perdio lo intuitivo, podrías en base a skills de diseño de react implementar de la mejor forma reorganizando todos los componentes para mejorar el ux desing, claro sin modificar las api del back que consumen para evitar cualquier tipo de daño".
- **L2** (decisión): adaptive layout (main flow + contextual panels). No stepper (suma fricción para usuarios expertos), no tabs (rompe el flujo lineal), no solo-collapsible (sigue siendo el status quo).
- **L3** (decisión): extraer custom hooks primero (T1-T4) para tener la lógica testeable, después componentes (T5-T14) que consumen los hooks, finalmente `ToolApp.tsx` reescrito (T15). Esto permite que cada commit sea compilable y testeable.
- **L4** (no skill): las disponibles (`serviklapp-react`, `serviklapp-ux`) son del proyecto Serviklapp. El proyecto ya tiene shadcn/ui new-york + Radix, suficiente.
- **L5** (validación de scope): `ToolApp.tsx` actual 1790 líneas, 30+ useState, 11 handlers. Cero cambios en backend confirmados.
