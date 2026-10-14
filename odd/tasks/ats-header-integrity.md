# ATS header integrity

> URLs de perfil legibles por el crawler, y el fix que devolvió RenderCV a su rightful lugar.

Branch: `feat/yaml-editor-structured` · Commits: `99faa5c`, `7f9d854`, `e00dc73`, `dedce67`

Tres defectos encadenados. El primero enmascaró a los otros dos.

---

## 1. El ajuste compacto era inerte (raíz de todo)

```python
def convert_llm_json_to_rendercv_dict(parsed_data, theme="sb2nov"):  # ← sin el parámetro
    ...
    if fit_single_page:   # ← NameError
```

El bloque de compactación existía pero la firma nunca lo recibió, y `render_cv_with_rendercv` se lo pasaba. Resultado: `TypeError` en **cada** render.

Como esa llamada está envuelta en un `try/except` que cae al renderer HTML de Playwright, el fallo era invisible. **RenderCV nunca se usó** y el toggle "Priorizar 1 Página" no hacía nada en ningún tema.

Consecuencia observable: un CV generado con `sb2nov` salía en **Times New Roman** (la fuente del `HTML_TEMPLATE`) en vez de **New Computer Modern** (la de RenderCV). Eso fue la pista que permitió diagnosticar los defectos siguientes.

Efecto del fix, medido con 3 experiencias:

| | Páginas |
|---|---|
| Sin compactar | 2 |
| Compactado | **1** |

## 2. URLs completas como texto visible

El template HTML generaba anclas cuyo texto era solo el nombre de la red:

```html
<a href="https://linkedin.com/in/julieth-caicedo">LinkedIn</a>
```

Los crawlers ATS leen la **capa de texto** del PDF, no las anotaciones de enlace. El crawler veía la palabra "LinkedIn" y no tenía URL que seguir.

`_ats_link_label` emite ahora la misma etiqueta que RenderCV ya produce — `linkedin.com/in/<slug>` — para que ambos renderers coincidan. Normaliza scheme, `www.` y slash final.

**Bonus de seguridad**: las URLs no estaban escapadas. Un `portfolio` con `"` podía inyectar markup. Ahora `href` y etiqueta van con `escape()`.

## 3. La foto fragmentaba las URLs

Una foto desplaza la línea de contacto a la derecha. Medido sobre un PDF real:

| | Ancho de la línea |
|---|---|
| Sin foto | 481pt |
| Con foto | **436pt** |

Faltan 45pt, así que el layout envuelve — y las URLs parten en sus guiones:

```
linkedin.com/in/julieth-andrea-caicedo-
goyeneche
```

La anotación de enlace queda intacta (`https://www.linkedin.com/in/...`), pero el texto no. El ATS lee el texto.

**Solución**: los perfiles van en una línea propia de ancho completo, con `white-space: nowrap` por link.

### Segundo bug, encontrado al verificar el primero

La primera versión usó `inline-block` + `nowrap`. Los tres links sumaban **637pt** en una columna de impresión de **554pt** → overflow de 83pt. Eso produjo dos síntomas distintos:

| Síntoma reportado | Causa |
|---|---|
| Pegado a la izquierda, no centrado | Una caja inline que desborda **ignora `text-align: center`**. El desborde va a la derecha; la caja queda al inicio. |
| Renglón en blanco de más | Cada link `nowrap` se partía en su **propia línea interna** → bloque de 35pt donde una línea de texto son 12.6pt. |

Resuelto con flex:

```css
.profile-links {
  display: flex; flex-wrap: wrap; justify-content: center; gap: 0 6pt;
}
.profile-links a { white-space: nowrap; }
.profile-links a:not(:last-child)::after { content: " |"; }
```

El `nowrap` por link sigue protegiendo el slug; `flex-wrap` permite quebrar **entre** links sobre una línea compartida y centrada. El separador va por `::after` para no participar del layout y aun así aparecer en el texto extraído.

| | Antes | Después |
|---|---|---|
| Overflow | +83pt | **0pt** |
| Alineación | izquierda | centrado |
| Alto del bloque | 35pt | 2 líneas limpias |
| URLs íntegras | no | **3/3** |

## Canario

`_check_profile_urls_not_fragmented` corre tras cada render (ambos paths) y avisa por log cuando una URL no sobrevive la extracción. El fix de layout es la cura; esto detecta la regresión, porque un wrap silencioso es invisible a cualquier otro check.

## Nota de método

La primera medición dio "todo bien" en los 4 renderers. **Medía en modo screen (1280pt).** El bug solo aparece en **print** (554pt), que es lo que usa el PDF. A partir de ahí todas las verificaciones usan `emulate_media(media="print")` con viewport de 554pt.

Sin esa corrección el test verde habríahidden un bug visible para el usuario — el mismo patrón que ya habíaAppeared dos veces en este trabajo (el tokenizador que ignoraba `30%`, y el overflow).

## Log

- **L1** (input): *"Inclusión del Enlace a LinkedIn: En el encabezado aparece la palabra 'LinkedIn' sin el hipervínculo o URL completa."*
- **L2** (input): *"Fragmentación del Enlace de LinkedIn: la URL se dividió en dos líneas por espacio de margen... Un parser automatizado puede registrar el enlace roto como dos palabras separadas."*
- **L3** (investigación): 16 combinaciones sintéticas (4 temas × foto × compactado) **no reproducían** el problema. Se pidió revisar el PDF real y se encontró la causa.
- **L4** (hallazgo): el PDF reportado usa Times New Roman → lo generó el fallback HTML, no RenderCV. Rastreado hasta el `TypeError` de `fit_single_page`.
- **L5** (geometría real): línea de contacto 481pt necesarios vs 436pt disponibles con foto. Déficit de 45pt medido sobre el archivo, no estimado.
- **L6** (error de método): se diminutionó el problema con un test sintético que pasaba, y con un monkeypatch que **nunca aplicó**. El reporte "pasa igual sin el fix" era una señal inválida. Se descartó esa evidencia.
- **L7** (decisión): línea dedicada en lugar de reducir fuente o foto. Reduce la foto a 2.4cm daba solo 22.7pt de los 45pt necesarios, y(requireía achicar la fuente a 9.5pt — invasive e innecesaria cuando bastaba dar a la URL la línea completa.
- **L8** (verificación): contrastado contra el PDF real del usuario; 3/3 URLs contiguas, overflow 0, ambas líneas centradas.
