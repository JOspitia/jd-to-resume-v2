# Optional candidate photo

> Foto opcional del candidato en el encabezado del CV, disponible para todos los dominios.

Branch: `feat/yaml-editor-structured` · Commits: `0d0cec8`, `367ea02`, `bf7dcad`

## Specs

**S1** — Campo de foto opcional en la sección de contexto de la vacante, junto a los otros datos que aporta el candidato (cargo objetivo, LinkedIn, GitHub, portafolio).

**S2** — Disponible para **todos** los dominios, no solo RRHH y Psicología. Si un CV lleva o no foto depende del sector y del reclutador: en España y LATAM se espera en RRHH y psicología, mientras que en tech suele penalizarse. Codificar la regla en el producto sería acertar para unos reclutadores y equivocar para otros.

**S3** — Preview local con object URL, botón para quitarla, y limpieza en "Nuevo / Limpiar".

**S4** — Validación por contenido, no por extensión: un `.txt` renombrado a `.png` se rechaza. Formatos: PNG, JPG, GIF, WebP. Límite 5 MB.

**S5** — La foto llega al PDF en **los cuatro renderers** (`sb2nov`, `classic`, `moderncv`, `classic_html`).

**S6** — Una foto inválida degrada a "sin foto". Nunca hace fallar la generación completa, que dejaría al usuario sin CV.

## Implementación

### `backend/photo_helpers.py` (nuevo)

RenderCV exige una **ruta de archivo** para `cv.photo` (`ExistingPathRelativeToInput`) — rechaza data URIs, verificado. Por eso la imagen se persiste antes de entregarla al renderer.

Módulo aparte, sin imports de fastapi/fitz/rendercv, igual que `yaml_helpers`, para que siga siendo testeable sin bootear la app.

- `detect_image_extension` — sniffing por magic bytes. Cubre PNG, JPEG, GIF, WebP (WebP vía `RIFF....WEBP`).
- `save_photo` — valida y persiste con nombre derivado de SHA-256 del contenido. Resubir la misma foto reutiliza el archivo en vez de acumular copias, y dos uploads distintos nunca colisionan.
- `prune_orphaned_photos` — limpia uploads abandonados desde `/api/clear-cache`.

### Backend

`_persist_uploaded_photo` en `main.py` — nunca lanza. Loggea y devuelve `None` en vez de propagar.

`/api/generate` y `/api/render-from-yaml` aceptan `photo: Optional[UploadFile]`.

**RenderCV**: recibe la ruta. Solo se pasa si el archivo existe — una ruta obsoleta hace fallar el render entero y lo manda silenciosamente al fallback de Playwright.

**Playwright**: `_photo_to_data_uri` convierte los bytes a data URI, porque el engine HTML no tiene acceso a disco. El header pasa a ser `.header-row` flex para que la foto quede al lado del bloque de contacto, igual que `photo_position: left` de RenderCV.

**Storage**: `backend/output/photos/`. El loop de `/api/clear-cache` solo desenlaza archivos, nunca entra a subdirectorios, así que las fotos quedaban huérfanas — ahora se purgan explícitamente.

### Frontend

`PhotoField.tsx` + estado en `useProfile` (`photo`, `photoPreview`, `photoError`, `handlePhotoChange`, `clearPhoto`), siguiendo el patrón del uploader de PDF. Object URL revocado al reemplazar y al desmontar, así que elegir fotos repetidamente no filtra memoria.

El `File` viaja en cada request de generate y render-from-yaml: cambiar la foto sola reproduce el CV sin volver a subir el PDF.

## Verificación

| Caso | Resultado |
|---|---|
| Magic bytes: PNG, JPEG, GIF, WebP | PASS |
| Texto plano renombrado | Rechazado |
| Payload PHP | Rechazado |
| Payload > 5 MB | Rechazado |
| Mismos bytes subidos dos veces | PASS — una sola archivo |
| Foto embebida en los 4 temas | PASS — 1 imagen por PDF |
| Sin foto | PASS — render normal, 0 imágenes |
| Ruta obsoleta | PASS — ignorada, sin crash |

## Log

- **L1** (input): *"podrías implementar que de igual una vez ejecutado el generar el cv para evitar cualquier tipo de error se aplique el auto reparar..."* — la foto fue un pedido previo: *"poner la opción de agregar foto indiferente del perfil que sea opcional"*.
- **L2** (investigación): RenderCV 2.8 expone `cv.photo` como `ExistingPathRelativeToInput | HttpUrl`. Se probaron ruta relativa y absoluta (ambas funcionan), data URI (rechazado), y se verificó que los 3 temas built-in declaran `photo_position: left`.
- **L3** (decisión): validación por contenido en vez de confiar en la extensión del archivo. Motivo: el nombre lo elige el cliente.
- **L4** (decisión): degradar a "sin foto" en vez de fallar. Perder el CV completo por una foto mal tomada sería inaceptable para un campo opcional.
- **L5** (bug encontrado): `/api/clear-cache` no limpiaba fotos — el loop solo hace `os.remove` sobre archivos y nunca entra a subdirectorios.
- **L6** (issue durante implementación): `File` de FastAPI no estaba importado; `from html import escape` agregada para el helper de URLs.
- **L7** (verificación): 4 temas × con/sin foto = 8 configuraciones, la foto llega embebida en todas.
