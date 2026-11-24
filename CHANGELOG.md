# Changelog

Registro cronológico de cambios por sesión. Cada sesión documenta su
alcance (qué problemas atacó, qué archivos tocó, qué decisiones se
tomaron) y un trail de commits para auditoría.

## 2026-11-24 — Sesión "Los bullets traducidos no empiezan con 'I'"

**Tipo:** fix.

### Fix — La traducción arrastraba el sujeto ("I increased…")

**El síntoma.** El usuario revisó el PDF traducido y notó que **todos** los
bullets de experiencia empezaban con "I": "I increased automated test
coverage…", "I reduced bugs detected in production…", "I validated medical
flows…". Seis bullets, seis "I".

**¿Es lo correcto?** No. La convención del CV en inglés es el **verbo en
pasado sin sujeto**: "Reduced response times by 45%…". De hecho, el propio
prompt de adaptación del repo ya lo hace así. El problema es de la
traducción, no de la convención.

**La causa.** El español obliga a conjugar el verbo ("Incrementé",
"Reduje"), y un verbo conjugado necesita sujeto. La traducción literal
arrastra el "I" porque no es opcional en la lengua de origen. El prompt no
decía nada del asunto, así que el modelo hizo lo natural: traducir la
oración completa.

**El arreglo, en dos capas:**

1. **El prompt** (`backend/domain/translate_prompts.py`) gana una sección
   "THE FIRST PERSON" que explica la diferencia entre las dos lenguas y da
   los pares de ejemplo (Incrementé la cobertura → Increased test
   coverage).

2. **El backend normaliza** (`strip_subjects` /
   `strip_leading_subject` en `backend/domain/translation_facts.py`). Si el
   modelo aun así deja un "I" al principio, se quita **solo** cuando lo
   sigue un verbo en pasado — regular ("increased", "reduced",
   "configured") o irregular ("led", "built", "wrote") — y el verbo queda
   con mayúscula inicial.

   Lo que **no** se toca, a propósito:
   - "In 2019 I led the team" → el sujeto no va al principio.
   - "I am the first point of contact" → no es un verbo en pasado.
   - "I have 4 years of experience" → tampoco es pasado.
   - El resumen y cualquier otro texto que no es un bullet de experiencia.

**Verificación.** 6 tests nuevos (`TestLeadingSubject`), 432 en verde.
Prueba real sobre el CV del usuario: **0 bullets con sujeto "I"** y **0
campos en español**, con un PDF de dos páginas limpio.

---

## 2026-11-24 — Sesión "Traducción fiel del CV al inglés"

**Tipo:** feature.

### Fix — La traducción dejaba casi todo en español (guard de idioma)

**El síntoma.** El usuarioPegó el PDF que le salió y señaló lo que faltaba:
los bullets de experiencia, los cargos, las categorías de habilidades, los
títulos de grado y los logros seguían **en español**. Solo se habían
traducido los títulos de sección y el resumen (que en su PDF de origen ya
venía en inglés).

**La causa: el prompt estaba desbalanceado.** Las reglas de "no toques
nada" eran muchas y enfáticas ("no agregues", "no borres", "no
reordenes", "no reescribas") y la de "traducí" era una más. El modelo
optimizó por no infringir las prohibiciones, y "no toques nada" se leyó
como **"copiá el input"**. Lo que el modelo produjo fue, literalmente,
lo que el prompt le pedía en los pocos lugares donde el prompt estaba
escrito en detalle.

**Dos arreglos:**

1. **El prompt rebalanceado.** "EVERY TEXT IN YOUR ANSWER MUST BE IN
   ENGLISH" pasó a ser la instrucción principal, con una lista explícita
   de los campos que hay que traducir (cada bullet, cada cargo, cada
   categoría, cada grado, cada logro). Las reglas de "no toques" se
   reencuadran como reglas sobre el **contenido** ("no cambies el
   contenido" en vez de "no copies el texto"), y se aclara que un cargo
   ("Ingeniero TICs - QA") es una descripción, no un nombre propio.

2. **Un guard determinista** (`backend/domain/translation_facts.py`),
   con la misma filosofía que el guard de cifras de la carta: el prompt
   pide, el backend verifica.
   - Detecta las cadenas que siguen en español con **marcadores
     funcionales del español**, no con un clasificador de documento: el
     grano importa, porque lo que hay que juzgar es *esta* cadena y no
     el CV entero.
   - No marca los nombres propios (universidad, empresa, ciudad), los
     nombres de tecnologías, las fechas ni las URL.
   - Si queda algo en español: primero un **segundo borrador** con las
     cadenas problemáticas entre comillas; si el modelo insiste, una
     **pasada dirigida** que traduce solo esos pedacitos; si tampoco,
     se conserva el original (perder contenido es peor que una frase en
     español) y se reporta en el log.
   - La primera versión del detector marcaba "backend" y "sector" como
     palabras españolas: son inglesas válidas y disparaban una llamada
     extra al modelo en cada CV. Se sacaron de la lista.

Un bug del guard que los tests destaparon: si el modelo respondía a la
pasada dirigida con el CV entero en vez del mapa de rutas, el
`set_path` **reemplazaba listas por strings** y rompía el documento.
Ahora solo se escribe sobre una ruta hoja cuyo valor actual sea un
string, y una respuesta que no sea un mapa de rutas se ignora.

**De paso:** el texto extraído del PDF arrastra el marcador `in` que
RenderCV imprime antes de un grado ("in in Bachelor's Degree"). El
backend lo limpia, así que el título no sale duplicado.

**Verificación.** 30 tests nuevos (21 del detector + 9 del guard
end-to-end), 430 en verde. Prueba real sobre el CV del usuario: **0
campos en español** en el resultado — cargos, bullets, categorías,
ítems de skills, títulos de grado y logros, todo en inglés — y un PDF
de dos páginas limpio en los dos motores.

### Fix — Tres instancias de uvicorn peleando por el puerto 8000

El `netstat` mostró **tres** instancias de uvicorn escuchando en el
puerto 8000 (la original de las 10:14 seguía atendiendo con el código
viejo), y por eso los cambios no llegaban a probarse. Con la política
de Windows de reutilizar el socket, varias instancias pueden escuchar
el mismo puerto y el traffic se reparte: el servidor que responde puede
no ser el que creaste. Se mataron todas y se arrancó una sola.

### Feature — Traducir el CV maestro sin adaptarlo, antes de generar

**El pedido.** "La opción de traducir PDF sin modificar nada del mismo
¿dónde quedó? Debería poderlo hacer antes de generar el CV."

**Dónde estaba.** La traducción existía, pero como botón en la tarjeta
de resultado: el *Traducir al inglés* re-corre **todo** el pipeline de
adaptación con `force_language=en`, o sea que vuelve a reescribir el CV
contra la vacante y solo lo escribe en inglés. No era una traducción,
era una segunda adaptación. Y como el botón vive en la tarjeta de
resultado, no había forma de traducir **antes** de generar: el CV
maestro no se podía traducir nunca.

**La solución: un modo, no una opción.** El checkbox **"Traducir mi CV
al inglés (sin adaptar)"** —en OPCIONES AVANZADAS, fuera del desplegable
"Más opciones" porque no es una opción más: cambia qué hace el
pipeline— activa `translate_only=true`, que:

1. **Usa un prompt propio** (`backend/domain/translate_prompts.py`) en
   lugar del prompt de adaptación. El contrato es el opuesto:
   *traducí el contenido, no cambies nada más*.
2. **Ignora la vacante.** El formulario la reemplaza por una nota que
   lo explica y el `jd` se manda vacío.
3. **No enriquece con LinkedIn** ni aplica las instrucciones
   adicionales: no hay nada que adaptar.
4. **Salta la re-auditoría automática**, porque no hay vacante contra la
   cual auditar. El audit sigue disponible desde el frontend con
   "Auto-validar ATS".

El prompt protege lo que una traducción suele romper:

- Mismas secciones, mismo orden, mismos puestos, mismo número de
  bullets.
- Cero añadidos: ni logros, ni métricas, ni habilidades, ni
  certificaciones.
- Contactos verbatim: una URL no se traduce.
- Cifras intactas: "200 impresoras" → "200 printers"; "2K+ descargas" →
  "2K+ downloads" (no "2.000").
- Marcas de fecha traducidas ("Actualidad" → "Present"), nombres
  propios intactos, términos técnicos con su nombre estándar de la
  industria.
- **Las certificaciones no se pierden**: la sección "Certificaciones"
  del CV original va al array `achievements` de la salida. Esto se
  detectó en la prueba real — la primera traducción dejó el array
  vacío y las certificaciones desaparecieron — y se corrigió
  añadiendo la regla 13 al prompt.

La salida usa **el mismo esquema JSON** que el pipeline del CV, así que
los renderizadores no cambian: el PDF traducido sale con la plantilla y
el color de acento que elegiste, en una sola columna y con texto
seleccionable.

Si el CV ya está en inglés, el backend lo detecta y avisa que no hay
nada que traducir, en vez de devolver un re-render inútil.

**Verificación.** 15 tests nuevos (`test_translate_only.py`): el
contrato del prompt, que la vacante no llegue al modelo, que el PDF
salga descargable, que un CV en inglés se rechace y que **el flujo
normal siga intacto**. 399 tests en verde. Prueba real contra el LLM
configurado con un CV en español: las mismas secciones, los mismos
cifras (200 impresoras, 15 horas, 2K+ descargas, 4,5/5, ocho meses),
las mismas fechas, la certificación conservada, y un PDF de una sola
página en los dos motores (RenderCV `sb2nov` y Playwright HTML).

### Fix — El `--reload` de uvicorn mataba los renders a mitad de camino

**El síntoma.** "Connection closed while reading from the driver":
Playwright perdía la conexión con su driver en pleno render, y el
backend se reiniciaba justo después.

**La causa.** `uvicorn --reload` sin `--reload-exclude` vigila **todo**
el directorio del backend, incluidos `output/` y `rendercv_output/`.
RenderCV escribe ahí sus archivos temporales → el reloader lo ve →
reinicia el server → mata el driver de Playwright → el render se cae a
 mitad. No era un bug del modo de traducción: es un bug de **todo el
 flujo de CV** en desarrollo, que aparece cuando RenderCV falla y cae
 al motor de Playwright.

**El arreglo.** `watchfiles` a `requirements-dev.txt` (los
`--reload-exclude` de uvicorn son un no-op sin esa dependencia, y
uvicorn solo lo avisa por log) y la receta de arranque con los excludes
en el README.

## 2026-11-24 — Sesión "Carta de presentación: PDF, diseño y contactos"

**Tipo:** feature.

### Fix — La carta ya no puede inventar cifras (guard determinista)

**El bug.** En la prueba end-to-end, la carta decía *"En mis roles he
atendido a más de 120 clientes por día"*. El CV no menciona ningún
cliente: es un CV de soporte de TI. La cifra no estaba inventada por
casualidad — **era un ejemplo copiado del prompt**. La regla 5 del
prompt de la carta ilustraba la gramática de una frase concreta con
ejemplos que traían números de verdad ("atendí a más de 120 clientes
por día", "cerré 35 ventas mensuales"), y el modelo los reutilizó
como si fueran datos del candidato.

Eso viola la regla que el proyecto sostiene desde el principio (no
inventar), y en una carta es peor que en el CV: el CV es una lista
verificable, la carta es prosa, y una cifra plausible se cuela sola.

**Las dos correcciones, complementarias:**

1. **La causa raíz (el prompt).** Los ejemplos de la regla 5 pasaron a
   ser marcadores de posición explícitos — `"atendí a [NÚMERO DEL CV]
   clientes por día"` — con un aviso de que son formas gramaticales y
   **no** datos, y de que sus números no se copian nunca. La regla 12
   (fact check) ahora avisa que las cifras se verifican
   mecánicamente.

2. **El garante (el backend).** El prompt no basta: la prosa es
   donde un modelo se desliza. Nuevo módulo
   `backend/domain/letter_facts.py`:
   - Extrae todas las cifras de la carta y las compara, **normalizadas**,
     contra el CV y contra la vacante. Normalizar importa: el CV
     escribe "50K+ líneas" y "2.000 descargas"; la carta escribe
     "50.000" y "2.000" — son la misma cifra, no una invención. La
     notación `K`/`M`, los separadores de miles y las decimales se
     normalizan antes de comparar.
   - No se marcan: los enteros pequeños (1 a 12, que son recuentos y
     ordinales, no métricas), las URL, los correos y los teléfonos; y
     las cifras que salen de la vacante (que es un documento real). Los
     decimales **sí** se marcan siempre. Un rango de años ("2014 -
     2018") tiene la misma forma que un teléfono, así que se distingue
     antes de comparar.
   - Si hay una cifra sin respaldo: **un reintento correctivo** con el
     modelo (se le dice exactamente cuáles son y se le pasa el
     borrador), y si el reintento también falla, **se eliminan las
     oraciones** que la llevan. Si el cuerpo entero quedara vacío, la
     petición responde 502 en vez de devolver una carta con datos
     inventados.
   - El `opening` y el `closing` pueden quedar vacíos: una carta que
     arranca con el argumento después del saludo es una carta normal,
     y una cifra inventada no lo es.

**Verificación.** Prueba real contra el LLM configurado: la carta
devuelta tiene exactamente tres cifras — 200 impresoras, 2.000
descargas y 4,5 de calificación — y **las tres están en el CV**.
Cero cifras sin respaldo. 16 tests nuevos (385 en total).

### Feature — La carta también sale en PDF, con el diseño del CV y los contactos reales

La carta de presentación solo se podía copiar como texto. Pero el PDF es
lo que más se usa: es lo que uno adjunta, lo que se imprime y lo que se
sube a un portal que pide archivo. Y tiene que **verse como el CV**, no
como un texto suelto.

**El PDF de la carta**

- `backend/templates/letter.html.j2` + `backend/templates/letter_body.html.j2`
  (nuevos) — la plantilla de la carta. Reutiliza el sistema visual del
  CV: las mismas variables CSS de acento, las mismas reglas de seguridad
  ATS (el cuerpo nunca se tiñe, nada tiene relleno de color detrás del
  texto, las URLs van en su propia línea) y la misma escala tipográfica.
- `backend/adapters/renderer/cover_letter_adapter.py` (nuevo) — renderiza
  la carta con el mismo Chromium headless que usa el fallback HTML del
  CV. **No** se reutilizan los renderizadores del CV porque están
  construidos alrededor de un documento por secciones (RenderCV espera
  un esquema de currículum: educación, skills, experiencia, proyectos) y
  una carta no tiene nada de eso. Lo que sí se reutiliza son las piezas
  que hacen bueno al CV: `design_palettes.accent_css_variables` (los
  mismos colores) y `_ats_link_label` (las URLs impresas como
  `linkedin.com/in/<slug>`, que es lo que leen los rastreadores de ATS).
- Tres estilos que reflejan los tres diseños del CV: **clásica**
  (encabezado centrado, cuerpo serif), **moderna** (encabezado a la
  izquierda, cuerpo sans) y **lateral** (columna de contactos a la
  izquierda, carta a la derecha).
- `backend/routes/design_router.py` — el catálogo de estilos de carta se
  sirve desde el mismo endpoint `/api/design-options` que los temas del
  CV, para que el swatch que el usuario ve sea el hex exacto que el
  renderizador va a aplicar.

**Los contactos:LinkedIn incluido, y siempre reales**

- `backend/application/services/cover_letter_service.py` — el bloque de
  contactos se resuelve **de forma determinista**, nunca con lo que diga
  el modelo: primero lo que el usuario escribió en el formulario, y si
  no, lo que se extrajo del propio PDF (`parser.extract_header`).
  El modelo solo aporta el **nombre**; el backend reescribe la firma con
  los contactos verificados. Una carta ya no puede inventar un teléfono,
  un correo ni una URL.
- El prompt cambió en consecuencia: la regla 6 ahora pide el nombre y
  nada más, y dice explícitamente que no escriba teléfono, correo ni
  enlaces.
- El LinkedIn sale en el encabezado y en la firma, impreso como
  `linkedin.com/in/<slug>` y clicable en el PDF.

**El resto**

- `backend/adapters/storage/filesystem_storage.py` y
  `backend/ports/resume_storage.py` — la carta se guarda como
  `cover_letter_<ts>.pdf` y se sirve por la misma ruta `/api/download`
  que los CV; el regex de allowlist pasa a
  `^(tailored_resume|cover_letter)_\d+\.pdf$` (el camino relativo sigue
  bloqueado).
- `backend/routes/cover_letter_router.py` — acepta `letter_style`,
  `accent`, `linkedin_url`, `github_url` y `portfolio_url`, y devuelve
  `pdf_url` + `pdf_filename` + `contact`. Un estilo o un color
  desconocidos caen al valor por defecto en vez de romper la petición.
- El render del PDF corre en un thread (`asyncio.to_thread`): la API
  sincrónica de Playwright no puede arrancar dentro de un event loop, y
  el endpoint es asíncrono. Si el PDF falla, la carta de texto se
  devuelve igual.
- Frontend: `CoverLetterOptions` suma el selector de diseño y los
  swatches de color (mismo catálogo que el CV), `CoverLetterPanel`
  suma **Descargar PDF** (descarga real: el servidor responde con
  `Content-Disposition: attachment`) y **Ver PDF** (apertura en el
  visor del navegador, como el botón Preview del CV), y el hook
  manda los links del formulario.
- `backend/tests/test_cover_letter.py` — 9 tests nuevos: el bloque de
  contactos determinista, el form por encima del CV, el PDF
  descargable con la URL intacta en la capa de texto, el fallback de
  estilo y color desconocidos, y el regex de almacenamiento.
- `backend/tests/test_input_validation.py` — el regex inline copia el
  nuevo allowlist, con los dos prefijos y sus casos inválidos.

### Verificación

- **369 tests en verde** (29,25 s), antes 360.
- Prueba real end-to-end con el LLM configurado: `sample-pdfs/jakes-resume.pdf`
  + una JD de Ejecutivo Comercial, perfil general, empresa "Tiendas
  Alcala", estilo lateral y color navy → 200, PDF de **una sola página**,
  texto seleccionable, con el LinkedIn del CV (`linkedin.com/in/jake`)
  intacto en la capa de texto y una cifra real del CV (200 impresoras).
- Los tres estilos renderizados y revisados visualmente: la URL del
  perfil sale clicable y sin partirse en el guion.
- `tsc --noEmit` del frontend sin errores.

## 2026-11-24 — Sesión "Carta de presentación"

**Tipo:** feature.

### Feature — Segundo entregable: carta de presentación

El tool solo producía un PDF. Ahora, con el **mismo CV y la misma
vacante**, también produce una carta de presentación: un entregable
aparte, no un flag sobre `/api/generate`, porque una carta es una
narrativa y un CV es un documento estructurado — el prompt, el contrato
de respuesta y el presupuesto de rate limit son distintos.

**Backend**

- `backend/domain/cover_letter_prompts.py` (nuevo) — el cuerpo del
  prompt. Reglas propias de una carta, porque falla de otra forma que
  un CV:
  - tiene que **añadir algo que el CV no dice** (el reclutador ya
    tiene el CV): escoge los dos o tres requisitos que más pesan en la
    vacante y argumenta cada uno;
  - **cero invención**, con la regla de que toda frase que nombre una
    habilidad, una herramienta, una cifra, una empresa o una fecha debe
    ser rastreable al CV base;
  - **sin frases vacías** ("persona dinámica y proactiva", "gran
    capacidad de adaptación", "excelente compromiso", "apasionado por el
    servicio");
  - cifras, no adjetivos;
  - sin metatexto (nunca menciona el ATS, el scoring ni la IA);
  - **ángulo por dominio**: la carta de *tech* abre con el problema que
    el candidato resolvió de punta a punta, la de *hr* con la escala
    del proceso, la de *psychology* con la población atendida y el rigor
    del método, y la de *general* con lo que el candidato le hace al
    cliente y cómo lo miden. El vocabulario sale de
    `game.skill_taxonomy_es`, así que la carta de un candidato de
    ventas no dice "pruebas psicotécnicas".
  - controles de **tono** (professional / persuasive / warm / concise),
    **longitud** (120-180 / 220-320 / 350-450 palabras) e **idioma**
    (auto / es / en).
- `backend/application/services/cover_letter_service.py` (nuevo) — la
  orquestación. Corre la cascada de LLM compartida y **normaliza** la
  respuesta a un contrato estable: `salutation`, `opening`, `body[]`,
  `closing`, `signature`, `plain_text` y `meta`. Tolera las cuatro
  formas que el modelo usa en la práctica: JSON desnudo, bloque con
  ```json, lista que envuelve el objeto y envelope `{"letter": {...}}`.
  `plain_text` lo arma el backend a partir de los campos estructurados,
  no el modelo, para que lo que se ve en pantalla y lo que se copia
  sean exactamente lo mismo.
- `backend/routes/cover_letter_router.py` (nuevo) — `POST
  /api/cover-letter`. Valida `domain_game`, `tone`, `length` y
  `language` (422 fuera de rango), persiste el PDF subido a un archivo
  temporal y lo borra al terminar. Usa su **propio scope de rate limit**
  (`cover-letter`), para que el presupuesto de la carta sea
  independiente del de la generación de CV.
- `backend/main.py` — el router se enchufa en el composition root con el
  mismo `LLMOrchestrator` y el mismo parser PyMuPDF que el resto.

**Frontend**

- `frontend/src/components/DeliverableSwitch.tsx` (nuevo) — el primer
  control del tool: **CV adaptado** o **Carta de presentación**. No es
  un paso numerado: decide qué produce el resto del flujo, así que va
  arriba y los pasos 1-3 (perfil, tu CV, la vacante) se comparten.
- `frontend/src/components/CoverLetterOptions.tsx` (nuevo) — empresa,
  tono, longitud e idioma. Reemplazan a "OPCIONES AVANZADAS" cuando el
  entregable es la carta: un tema o un color de acento no significan
  nada en un texto.
- `frontend/src/components/CoverLetterPanel.tsx` (nuevo) — el resultado:
  la carta en prosa, con **Copiar**, **Descargar .txt** y **Generar otra
  versión**.
- `frontend/src/hooks/useCoverLetter.ts` (nuevo) — la máquina de estados
  de la llamada, con timeout de 90 s y lectura del envelope de error
  (422/429/500/502).
- `frontend/src/types/coverLetter.ts` (nuevo) — los tipos y las etiquetas
  de los selectores.
- `frontend/src/hooks/useProfile.ts` — el estado del entregable y de las
  opciones de la carta; el reset los devuelve a sus valores por defecto.
- `frontend/src/components/ActionBar.tsx` — el CTA sigue al entregable
  ("Generar carta de presentación" / "Generar CV"), con los textos
  originales como default para no tocar el flujo del CV.
- `frontend/src/components/GenerationProgress.tsx` — barra
  **indeterminada** opcional, para operaciones de un solo disparo que no
  tienen stream de pasos (la carta): mostrar un porcentaje congelado
  sería mentir.
- `frontend/src/ToolApp.tsx` — el cableado. Cambiar de entregable
  limpia el resultado del otro, así un PDF viejo nunca queda debajo de
  una carta (ni al revés). En modo carta se ocultan la foto (solo es
  del render) y los paneles de auditoría y editor YAML, que no aplican.

### Verificación

- **360 tests en verde** (25,84 s), antes 333: los 27 nuevos cubren el
  prompt (que lleva los datos, la taxonomía del dominio, el ángulo por
  dominio, el tono, la longitud y el override de idioma), las seis
  variantes de parseo, los errores (campo faltante, cuerpo vacío,
  respuesta no-JSON) y el contrato del endpoint (422 en cada parámetro
  inválido, 200 con el cuerpo documentado, 502 cuando el modelo no
  entrega una carta legible, y el scope de rate limit propio).
- **Prueba real end-to-end** contra el servidor corriendo con el LLM
  configurado: `sample-pdfs/jakes-resume.pdf` + una JD de Ejecutivo
  Comercial con `domain_game=general` → 200, 246 palabras, en español,
  saluteando a la empresa por nombre, con la experiencia de soporte en
  TI traducida al lenguaje comercial ("resolver sus problemas técnicos
  y asegurar su satisfacción" → "asesorar y cerrar soluciones"), una
  cifra real del CV (200 impresoras) y los datos de disponibilidad
  (turnos, fines de semana, movilizarme en Medellín).
- `tsc --noEmit` del frontend sin errores.

## 2026-11-24 — Sesión "Perfil general (servicio, ventas y operaciones)"

**Tipo:** feature.

### Feature — Cuarto perfil de dominio: `general`

Faltaba un perfil para quien **no viene de tecnología, selección ni
psicología** y se postula a un cargo de atención al cliente, comercial o de
operaciones (venta en tienda, mostrador, caja, reposición, exhibición,
impulso, almacén, auxiliar de servicio). Con los tres juegos existentes,
el prompt le habría endosado al candidato categorías que lo descalifican:
un CV de ventas con "Lenguajes & Frameworks" o "Pruebas Psicotécnicas"
lee como un perfil equivocado, tanto para el reclutador como para el
matcher de keywords del ATS.

- **`backend/domain_games/general.py`** (nuevo) — el juego, con el mismo
  esqueleto de reglas que los otros tres (1–21) más tres reglas propias:
  - **Regla 4** — resumen de 3 a 4 líneas en lenguaje llano de servicio,
    sin jerga de psicología ni de software, y con una lista explícita de
    frases vacías prohibidas ("persona dinámica y proactiva", "gran
    compromiso", "excelente comunicador") salvo que los datos del
    candidato las respalden.
  - **Regla 5** — verbs de acción del dominio (Atendí, Asesoré, Cerré,
    Arqué, Repuse, Reposé, Fidelicé…) y métricas de servicio en vez de
    técnicas: personas atendidas, % de meta cumplida, candidatos
    gestionados, tiempos reducidos, ventas cerradas, accuracy de
    inventario. Las cifras que el CV base ya tiene ("más de 200
    candidatos", "más de 10 comunidades") deben sobrevivir a la reescritura
    con su número pegado al dato.
  - **Regla 7** — el vocabulario que repiten las ofertas: atención al
    cliente, servicio al cliente, asesoría comercial, ventas, cumplimiento
    de metas, manejo de caja, facturación, arqueo de caja, inventarios,
    exhibición de productos (merchandising), reposición, cierre de ventas,
    fidelización de clientes, trabajo en equipo y manejo de
    inconvenientes — **solo si son ciertas** en la experiencia.
  - **Regla 10** — taxonomía propia: *Atención al Cliente & Ventas · Caja,
    Facturación & Inventarios · Exhibición & Reposición · Cumplimiento de
    Metas & Resultados · Trabajo en Equipo & Servicio · Herramientas &
    Sistemas · Disponibilidad & Mobilidad*.
  - **Regla 22 (nueva)** — traducción comercial de experiencias no
    comerciales. El candidato no necesita haber vendido: lo que hizo se
    reformula con el vocabulario del cargo sin perder un dato. Las cuatro
    traducciones por defecto son *entrevistar/evaluar candidatos →
    identificar necesidades y perfilar personas*, *atender usuarios →
    manejo de clientes, empatía y resolución de quejas*, *seguimiento de
    indicadores → control de metas y resultados* y *coordinación
    operativa → organización, orden y cumplimiento de tiempos*.
  - **Regla 23 (nueva)** — información práctica: disponibilidad de
    horario y turnos (incluidos fines de semana), ciudad de residencia o
    disposición a desplazarse, y moto o licencia de conducción, **solo si el
    CV base las respalda**, en la categoría *Disponibilidad & Mobilidad*
    y/o en el campo `location`.
  - **Regla 24 (nueva)** — checklist final de los seis puntos que pide el
    perfil: resumen corto, keywords, cifras, traducción comercial, skills
    e información práctica.
  - Regla 1 endurecida para este dominio: la tentación de inventar es
    concreta (cifras de venta, manejo de caja, inventario, POS, turnos,
    licencia de moto) y queda prohibida de forma explícita.
- **`backend/domain_games/__init__.py`** — registro de `GeneralGame` en
  el diccionario `GAMES`.
- **`backend/routes/generate_router.py`,
  `backend/routes/audit_router.py`,
  `backend/routes/yaml_editor_router.py`** — `ALLOWED_GAMES` ahora
  incluye `"general"`. Sin esto, `/api/generate` devolvía HTTP 422.
- **`backend/domain/audit_prompts.py`** — semillas de auditoría propias
  del dominio ("Atención al cliente", "Cierre de ventas", "Manejo de
  caja" / "Merchandising", "Punto de venta (POS)", "Fidelización de
  clientes"), para que la auditoría no sugiera herramientas de otro perfil.
- **`frontend/src/hooks/useProfile.ts`** — el tipo `DomainGame` suma
  `'general'`.
- **`frontend/src/components/ProfileSelector.tsx`** — cuarto tile en el
  selector de perfiles (icono `Store`), y la grilla pasa de
  `sm:grid-cols-3` a `sm:grid-cols-2 xl:grid-cols-4` para que los cuatro
  quepan sin apretar.
- **`backend/tests/test_domain_routing.py`** — el contrato pasó de tres a
  cuatro juegos (el propio test lo pedía explícitamente), se añadió el
  caso de vocabulario propio en el parametrize de juegos no-tech, y dos
  tests nuevos: la taxonomía de servicio y la prohibición de inventar
  caja/licencia.
- **`backend/tests/test_audit_prompts.py`** — dos tests para las
  semillas y la taxonomía del perfil general.
- **`backend/tests/test_input_validation.py`** — el chequeo del registro
  ahora recorre los cuatro juegos.
- **`README.md`** — fila del perfil en la tabla de dominios, el contrato
  de API actualizado y una sección que explica las tres reglas propias.

### Verificación

- **333 tests en verde** (26,09 s), antes 321: los 12 nuevos cubren el
  registro, el contrato estructural de cada juego, el vocabulario
  propio, la taxonomía, las semillas de auditoría y el cartel de
  referencia.
- `render_domain_prompt_block()` del perfil general: 23.223 caracteres
  (dentro del rango que exige el test: 5.000–25.000).
- `get_game('general')` resuelve la instancia registrada y compone el
  prompt con los 24 numerados + el bloque de patrones A/B/C/D.

## 2026-11-09 — Sesión "Docker de punta a punta"

**Tipo:** feature (infraestructura).

### Feature — Stack 100 % Docker

Antes el backend solo se levantaba con un contenedor creado a mano
(`docker start jd-to-resume-backend`, imagen de 2,75 GB que reinstalaba
Chromium en cada arranque) y el frontend corría en el host con
`npm run dev`. No había `Dockerfile` ni `docker-compose.yml` en el repo, así
que el arranque no era reproducible.

- **`backend/Dockerfile`** — multi-stage. La etapa de build crea un venv,
  instala `requirements.txt` + `requirements-dev.txt` y descarga el
  navegador con `playwright install chromium --only-shell`; la etapa final
  copia solo el venv, los binarios del navegador y el código, e instala las
  librerías de sistema (`playwright install-deps`, `fonts-freefont-ttf`,
  `fonts-dejavu-core`). Sin compiladores, sin caché de pip, sin listas de
  `apt` en la imagen final. Corre como usuario no-root (`appuser`,
  uid 10001) y trae `HEALTHCHECK` contra el endpoint raíz.
- **`frontend/Dockerfile`** — multi-stage: `node:24-alpine` compila el
  bundle con `npm ci` + `npm run build` (que corre `tsc -b`, así que un
  error de tipos rompe el build) y `nginx:1.27-alpine` sirve el resultado.
- **`frontend/nginx.conf`** — sirve la SPA y hace de proxy inverso de
  `/api` hacia `backend:8000`. Como todo queda en el mismo origen, el
  bundle de producción usa URLs relativas (sin CORS, sin recompilar por
  entorno) y el `download_url` relativo que devuelve el backend
  (`/api/download/<archivo>.pdf`) resuelve sin cambios. `proxy_buffering
  off` + `chunked_transfer_encoding on` preservan el streaming SSE de
  `/api/generate`, y `try_files` resuelve el fallback de la SPA.
- **`backend/.dockerignore` y `frontend/.dockerignore`** — fuera del
  contexto de build quedan `.env` (y cualquier `.env.*`), `node_modules/`
  (~200 MB), `dist/`, `__pycache__/`, `.pytest_cache/`, `output/`,
  `rendercv_output/`, `*.pdf` y `*.log`. Nada de eso llega al daemon ni se
  hornea en una capa.
- **`compose.yaml`** — orchestra ambos servicios: `env_file:
  ./backend/.env` inyecta las credenciales **en tiempo de ejecución**
  (nunca en la imagen), el volumen `jd-to-resume-output` persiste los PDFs
  y las fotos fuera del contenedor, y `depends_on: condition:
  service_healthy` evita la ventana de error al arrancar. El backend
  publica el 8000 y el frontend el 5173, igual que antes.
- **`backend/requirements-dev.txt`** — `pytest` y `pytest-asyncio`
  fuera de las dependencias de runtime, para poder correr la suite dentro
  del contenedor (`docker compose exec backend pytest`).
- **`backend/.env.example`** — plantilla sin secretos; documenta las
  variables que el README ya describía.
- **`.gitignore`** — se añadió la excepción `!requirements-dev.txt`: el
  patrón global `*.txt` lo estaba ignorando y el archivo no habría
  llegado al repo.

### Optimización de tamaño de imagen

El primer build dio una imagen de backend de **2,76 GB**. Dos hallazgos
medidos con `docker history` la bajaron a **2,03 GB (-27 %)**:

- **Chromium headless shell en vez del Chromium completo.**
  `playwright install chromium` descarga *dos* navegadores: el Chromium
  completo (~403 MB) y el `chromium_headless_shell` (~273 MB). Contrary
  a lo que sugiere `chromium.executable_path`, Playwright 1.64 lanza el
  **headless shell** para `launch(headless=True)` sin `channel=`. Como
  los cuatro `launch()` del backend son headless y ninguno pasa
  `channel=`, el Chromium completo era peso muerto: `--only-shell`
  descarga solo el binario que se usa. *(El primer intento fue el
  inverso —borrar el headless shell— y rompió el render con
  `Executable doesn't exist at .../chromium_headless_shell-1248/...`;
  el error de Playwright en los logs fue lo que lo dejó claro.)*
- **Purga de fuentes y Xvfb que Chromium headless nunca carga:**
  `fonts-unifont`, `fonts-wqy-zenhei`, `fonts-ipafont-gothic`,
  `fonts-noto-color-emoji` y `xvfb` (~75 MB). Se purgan en la *misma*
  capa que los instala, así que esos bytes nunca llegan a la imagen.

La imagen del frontend quedó en **74 MB** (bundle estático + nginx).

### Bug encontrado durante el build

La primera versión del Dockerfile del frontend fijaba `NODE_ENV=production`
en la etapa de build. `npm` omite las `devDependencies` cuando esa
variable está puesta, así que `tsc` no existía y el build fallaba con
`sh: tsc: not found`. La variable se quitó del stage de build (el bundle
se compila con las devDependencies instaladas).

### Verificación

- `docker compose up --build -d` → backend y frontend **healthy**.
- Generación real a través del proxy de nginx: HTTP 200 en 4,8 s, SSE
  completo (`Validating Input` → `Finished`).
- PDF descargado por `http://localhost:5173/api/download/...` (HTTP 200,
  `application/pdf`, 33 KB).
- Colores del PDF extraídos del content stream: `#000000` (cuerpo),
  `#1B3A5C` (acento navy) y `#49617D` (tono secundario) — el RenderCV
  y el render por Chromium aplican el mismo acento.
- Ruta Chromium (`theme=classic_html`): HTTP 200 en 0,65 s, PDF de 1
  página con 1.291 caracteres de texto seleccionable.
- **321 tests en verde dentro del contenedor** (24,59 s).
- UI de producción servida por nginx: landing y generador renderizan
  igual que el dev server, y el catálogo de plantillas + paletas llega
  desde el backend por el proxy del mismo origen.

## 2026-11-06 — Sesión "Color de acento + fixes de render"

**Tipo:** feature + bug-fix.

### Feature — Color de acento

- **Nuevo módulo `backend/design_palettes.py`**: seis paletas (azul
  marino, verde azulado, verde bosque, granate, ciruela, gris pizarra)
  más `none`. Es la fuente de verdad: tabla de colores, cálculo de
  contraste WCAG y variables CSS para el template HTML de Playwright.
- **Nuevo parámetro `accent`** en `/api/generate` y
  `/api/render-from-yaml`. Inyecta un bloque `design.colors` que
  RenderCV aplica sobre el color del texto. Valor desconocido → HTTP
  422.
- **Nuevo endpoint `GET /api/design-options`**: catálogo de plantillas
  y paletas. El frontend lo consume para pintar los swatches con el hex
  exacto que va a salir en el PDF, en vez de duplicar la tabla.
- **Selector "Color de acento"** en `AdvancedOptions.tsx`, justo debajo
  de "Plantilla" (misma decisión de diseño, mismo bloque visual).
- **Reglas ATS aplicadas**: el cuerpo del texto sigue negro, el color
  nunca va como fondo detrás del texto, los títulos de sección conservan
  negrita + cuerpo mayor + línea, el layout sigue en una sola columna y
  el PDF sigue siendo vectorial con capa de texto real.

### Feature — Cambiar solo el diseño (sin que la IA reescriba)

El pipeline siempre reescribe el CV con el LLM, así que cambiar la
plantilla obligaba a regenerar y devolvía **otro texto**, no el mismo CV
con otra piel.

- **Nuevo botón "🎨 Cambiar diseño (sin tocar el texto)"** en la tarjeta
  de resultado, con su propio panel (plantilla + color).
- **Nuevo hook `useRedesign`**: re-renderiza el YAML guardado del PDF
  actual vía `/api/render-from-yaml`, que **no llama al LLM**. Actualiza
  el preview y el link de descarga, y deja el diseño elegido como
  selección global.
- **Nuevo helper `src/lib/renderFromYaml.ts`**: una sola fuente de
  verdad para el POST a `/api/render-from-yaml`, ahora compartido entre
  el editor YAML y el rediseño (antes estaba duplicado).
- **Nuevo módulo `src/lib/designOptions.ts`**: el catálogo de
  plantillas y paletas se pide una sola vez y se comparte entre el picker
  de "Opciones avanzadas" y el panel de rediseño.

Medido sobre el flujo real de la UI: el PDF de la IA y el rediseñado dan
**1906 caracteres de texto extraído idénticos byte a byte** (258
palabras), 0 imágenes y el mismo rango horizontal. Solo cambian los
colores.

### Bugs

- **BUG-04**: `RenderCVAdapter.render()` llamaba `render_cv_with_rendercv(fit=...)`,
  pero la función espera `fit_single_page`. Era un `TypeError` latente
  que mandaba cualquier render por el adaptador al fallback de
  Playwright. Además el adapter ignoraba el `accent`.
- **BUG-05**: `PlaywrightHTMLAdapter` y la plantilla `classic.html.j2`
  tenían los colores `#000` hardcodeados, así que el acento no llegaba
  al fallback HTML. Ahora el template consume variables CSS
  (`--accent-body`, `--accent-strong`, `--accent-muted`, `--accent-rule`).

### Verificación

- **321 tests en verde** (252 previos + 69 nuevos en
  `backend/tests/test_design_palettes.py`).
- Renderizando **el mismo YAML** con y sin acento, el texto extraído del
  PDF es **idéntico carácter por carácter** (1867 chars en ambos casos):
  la capa de texto que lee el ATS no cambia, solo la tinta.
- Todos los tonos pasan WCAG AA (≥4.5:1) contra blanco; los acentos
  están entre 7.8:1 y 11.6:1.
- El flujo de rediseño verificado end-to-end en el navegador (abrir
  panel → elegir color → aplicar), comprobando que el texto del PDF
  resultante es idéntico al original y que el picker global se sincroniza.

### Trail de commits

- `fix(frontend): buffer SSE chunks so the final event is never dropped`
- `fix(backend): parse date ranges correctly and never emit an inverted pair`
- `fix(build): unblock pytest, the production build and the playwright dependency`
- `feat(prompts): forbid a references section in the generated CV`
- `feat(design): add ATS-safe accent palettes for the rendered CV`
- `feat(redesign): re-render the same CV with another design, without the LLM`

---

## 2026-10-17 — Sesión "Code review + rebrand"

**Tipo:** refactor + bug-fix + feature.

### Frontend

- **Rebrand UI completo (PR1-PR6)**: design tokens (`index.css`),
  primitives `Button`/`Card`/`Badge` con variants, dark mode toggle
  (`useTheme` + `ThemeToggle` + FOUC-prevention script), Footer
  atribución a "Edited by Johan Ospitia".
- **Landing traducida a español**: hero, FEATURES array reescrito
  reflejando capacidades reales (Generación IA / Auditoría ATS /
  Personalización total). Removido pinning a Gemini: copy del tipo
  "tu IA favorita" reemplazó "nuestra IA (Gemini)" para reflejar el
  modelo BYOK multi-provider.
- **Dark mode completo**: cubre inversión de tabs seleccionadas
  (`bg-foreground text-background` en vez de `bg-black text-white`),
  migración de pill labels, e index.html (`lang="es"` + title
  sincronizado con el brand `ResumeTailor-AI`).
- **ErrorBoundary en `App.tsx`**: captura render errors con recovery
  card en español.

### Backend — Fixes del code review (Pass 1 / 2 / 3)

Audit estático sobre `backend/main.py` por pass, con foco en bugs
reales, malas prácticas y código deprecado. Total: **2 doc reviews
+ 13 commits de fixes**.

#### Bugs
- **BUG-01**: `call_llm_api` re-construia el orchestrator por llamada.
  Fix: delega al singleton `_llm_orchestrator`.
- **BUG-02**: `_persist_uploaded_photo` referenciaba globals
  definidos abajo. Fix: reordenado después de `_save_photo` /
  `_PHOTOS_DIR`.
- **BUG-03**: `_RL_HITS` acumulaba keys vacías. Fix: pop() en la rama
  429 y simetría en la rama happy-path.

#### Deprecations / legacy
- **`google.generativeai` (EOL)** → migrado al SDK oficial
  `google-genai`. Stub de tests actualizado a hermético.
- **`fitz` (deprecation namespace)** → migrado a `import pymupdf`
  como API canónica del proyecto.
- 4 imports no usados eliminados de `playwright_html_adapter`.
- Shims `_content_tokens` / `_content_drift` eliminados; el test
  correspondiente apunta al módulo fuente.

#### Arquitectura hexagonal (cierre MP-02)
- `enforce_rate_limit` + `_RL_HITS` → `application/rate_limit.py`.
  4 routers pasan de `from main import` (lazy, in-handler) a top-level
  imports.
- `_persist_uploaded_photo` → `photo_helpers.persist_uploaded_photo`
  con `photos_dir` explícito. Nuevo `application/paths.py` para
  `OUTPUT_DIR` / `PHOTOS_DIR`.
- `extract_linkedin_profile_data` →
  `application/services/linkedin_service.py`. Cierra el último
  `from main import` en servicio.

#### Otros (Pass 3)
- **NEW-01**: `print(f"[LINKEDIN EXTRACTOR] ...")` → `logger.info(...)`
  en `extract_linkedin_profile_data`.
- **NEW-02**: `from main import extract_linkedin_profile_data` (lazy
  en `generation_service.py:267`) → top-level import.

#### Hardening
- `test_main_module_imports_without_nameerror_on_helpers` recibia
  `ValueError` por no tener keys LLM en el sandbox. Inyectado
  `LLM_API_KEY=test-no-llm-call-expected` en el subprocess del test
  para que el modulo cargue limpio y el test cumpla su rol original
  (NameError scan, no LLM smoke).

### API base URL env var (deploy blocker)
Frontend con 9 call sites hardcodeando `http://localhost:8000`.
Migrado a `import.meta.env.VITE_API_BASE_URL` con helper
`apiUrl(path)` en `frontend/src/lib/api.ts`. Default a string vacío
(same-origin para deploy detrás de reverse proxy).

### Métricas finales

| Métrica | Antes | Después |
|---------|-------|---------|
| `main.py` líneas | 2510 | 297 |
| Tests passing | 222/222 | 222/222 |
| Backend deprecation warnings | 2 (gemini + fitz) | 0 |
| Circular import (`from main`) en hot paths | 6 sitios | 0 |
| `import fitz` | sí | no |
| `import google.generativeai` | sí | no |

### Pendiente (no bloqueante)

- **MP-01 (cosmetic)**: imports no-lazy restantes en `main.py`.
  Funcional pero estético — para una sesión dedicada.
- **Vitest + RTL setup**: no hay test infra en frontend.
- **`tests/test_yaml_endpoints.py`** legacy: roto desde el hex
  split pero no recolectado. Cleanup pendiente.

## 2026-10-17 — Sesión "Frontend code review"

**Tipo:** bug-fix + refactor (frontend).

### Bugs

- **BUG-01**: `/api/generate` no tenía `AbortController` ni timeout, a diferencia de `analyze-ats` y `render-from-yaml` que ya usan 60s. SSE backend hung podía dejar requests abiertas indefinidamente. Fix: AbortController con 120s ceiling + `clearTimeout` en finally.
- **BUG-02**: closure de `forceTranslateToEnglish` (state de React) podía capturar el valor viejo cuando el usuario hacía click en "Translate to English" inmediatamente antes de `handleGenerate`. Fix: usar `shouldTranslate` (variable local ya resuelta param > state) en vez del state directo.
- **BUG-03**: 4 listas en `AuditPanel.tsx` usaban `key={i}` (índice de array) en `map` callbacks. Para listas interactivas (botones de keywords con checkbox, labels de tips) el índice como key es frágil: si el backend reordena keywords en el próximo audit, los checkboxes pueden quedar marcando valores equivocados. Fix: `key={kw}` / `key={tip}` en las 4 listas. También removimos el `, i: number` parameter ya inutilizado.
- **BUG-04**: `useProfile.ts` revocaba la Object URL de la foto en 3 sitios (manual en `handlePhotoChange`, manual en `clearPhoto`, cleanup en `useEffect`). El cleanup capturaba el mismo valor que las manuales, revocando doble. Fix: borrar las manuales, dejar el `useEffect` cleanup como único punto de revocación (cubre los 3 escenarios: cambio de foto, clear, unmount).

### Malas prácticas

- **MP-02**: 5 `catch (err: any)` en `useGeneration`, `useYamlEditor`, `useAudit`. Fix: `catch (err: unknown)` + narrowing explícito con `err instanceof DOMException && err.name === 'AbortError'` para aborts y `err instanceof Error ? err.message : fallback` para mensajes. TypeScript ahora chequea los accesos.
- **MP-03**: `let interval: any` en `useGeneration` (timer de elapsedSeconds). Fix: `ReturnType<typeof setInterval> | null`.
- **MP-04**: `handleResetProcess` en `ToolApp` era función inline recreada en cada render, forzando re-render de `ResultsPanel` aunque no cambiara. Fix: envuelta en `useCallback` con deps `[profile, generation, audit, yamlEditor]`.
- **MP-05**: `resetProfile` mezcla prefs de sesión (theme, fit, page break) con flags de comportamiento (`strictEditsOnly`, `extractLinkedinInfo`). Documentamos explícitamente en el JSDoc qué sobrevive reset y por qué (preservando v2.5 UX byte-for-byte sin tocar comportamiento).

### Type safety (`any` → interface)

- **MP-01 + DUP-03**: el shape del response de `/api/analyze-ats` estaba declarado 3 veces con tipos parciales o `any` (`useAudit.ts:42`, `AuditPanel.tsx:14`, `useGeneration.ts:83-91`). Fix: extraer `AuditData` interface en `frontend/src/types/audit.ts` (8 campos opcionales) y migrar los 3 sitios. Si el backend agrega un campo nuevo, modificar solo `AuditData` y TS avisa a cada consumidor.

### Código duplicado

- **DUP-01**: bloque "degenerate-output guard" (cuenta líneas con contenido + threshold 40% con floor de 3) aparecía idéntico entre `handleRenderFromYaml` y `handleRepairYaml`, solo difería en el mensaje. Fix: extraer `validateRepairOutput(repairedYaml, originalYaml)` como top-level helper que retorna `{ ok: true } | { ok: false; message: string }`.
- **DUP-02**: 3 endpoints repetían el patrón `new AbortController + setTimeout(controller.abort, 60000) + fetch + clearTimeout`. Fix: helper `fetchWithTimeout(url, options, timeoutMs = DEFAULT_FETCH_TIMEOUT_MS = 60_000)` en `lib/api.ts` + export `SSE_FETCH_TIMEOUT_MS = 120_000` por si migramos SSE después.

### `key={i}` extras (revisión, no modificados)

- `ScoreHistory.tsx:33` y 5 sitios en `YamlFormEditor.tsx`: NO son el mismo anti-pattern que BUG-03. `ScoreHistory` es display-only. `YamlFormEditor` tiene callbacks de update posicionales (`data.map((e, idx) => idx === i ? ...`) que requieren index tracking. Cambiar a keys estables requeriría rediseñar las callbacks — fuera de scope.

### Métricas

- Tests backend: 222/222 sigue verde.
- Sin cambios en backend.
- 2 archivos nuevos: `frontend/src/types/audit.ts`, ninguno en backend.
- 0 `catch (err: any)`, 0 `any` en shapes de audit (los 3 sitios migrados).

### Pendiente (no bloqueante)

- `tests/test_yaml_endpoints.py` legacy roto: no recolectado, explota si se corre puntual. Cleanup pendiente.
- MP-01 cosmetic: imports no-lazy restantes en `main.py`.
- Vitest + RTL setup: sigue sin test infra frontend.
