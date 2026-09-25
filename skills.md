# Perfil Profesional - Skills y Redacción

Este documento organiza tus habilidades actuales y sirve como base para agregar habilidades externas o mejoras de redacción enfocadas en optimización para filtros ATS y entrevistas.

---

## 1. Skills Actuales

### Habilidades Técnicas / Backend & Frontend
- **Python**: FastAPI, Desarrollo de APIs RESTful.
- **JavaScript / TypeScript**: React, Vite, Node.js.
- **UI & Estilos**: Tailwind CSS, HTML5, CSS3, Diseño responsivo y glassmorphic UI.
- **Herramientas & Entornos**: Git, GitHub, Uvicorn, entornos virtuales (`venv`), npm.

### Metodologías y Procesos
- Optimización de CVs para Sistemas de Seguimiento de Candidatos (ATS).
- Integración de Inteligencia Artificial / LLMs para procesamiento de texto.

---

## 2. Skills Externos (Por Incorporar / En Aprendizaje)

> *Podés agregar en esta sección habilidades adicionales que poseas o estés adquiriendo (tecnologías, frameworks, herramientas de cloud, etc.).*

- **Ejemplo**: Docker / Contenedores
- **Ejemplo**: Bases de datos (PostgreSQL, MongoDB)
- **Ejemplo**: Testing (Pytest, Jest)

---

## 3. Skills de Redacción & Optimización ATS

### Fórmulas de Redacción para Logros
- **Fórmula XYZ (Google)**: *"Logré [X], medido por [Y], haciendo [Z]"* (Ej: *"Reduje el tiempo de respuesta de la API en un 35% implementando almacenamiento en caché con Redis"*).
- **Método STAR / PAR**: *Problema/Acción/Resultado* enfocado en cuantificar métricas e impacto de negocio.

### Palabras Clave y Verbos de Acción Recomendados
- **Desarrollo & Arquitectura**: *Diseñé, Implementé, Refactoricé, Desplegué, Migré, Optimicé, Automaticé*.
- **Impacto & Resultados**: *Incrementé, Reduje, Agilicé, Maximicé, Consolidé, Lideré*.
- **Metodologías & Prácticas**: *Agile/Scrum, CI/CD, Code Reviews, TDD, Clean Code, REST APIs, Microservicios*.

### Reglas de Oro para ATS
- **Sin elementos complejos**: Evitar tablas compuestas, columnas múltiples, imágenes, cuadros de texto gráficos o caracteres especiales no estándar.
- **Tipografías Estándar**: Uso de fuentes legibles por parser (Arial, Calibri, Helvetica, Roboto, Times New Roman).
- **Encabezados Estándar**: Usar nombres exactos de sección (*Work Experience*, *Education*, *Skills*, *Projects*).
- **Formatos Limpios**: Preferir PDF generado directamente desde texto (no escaneado) o archivos DOCX.

### Reglas de la Skill `ats_optimization`
1. **Evitar Keyword Stuffing (`avoid_keyword_stuffing`)**: No repetir el mismo término o herramienta en más de 2 secciones sin variar el contexto.
2. **Normalizar Herramientas (`verify_tool_names`)**: Asegurar que cada herramienta mencionada sea reconocible y relevante para el puesto (ej: transformar nombres poco comunes como `"Gentle AI, Kimi K2"` en `"Orquestadores de agentes IA (ej. Kimi K2)"`).
3. **Consistencia Cronológica (`fix_date_consistency`)**: Usar `"Inicio: YYYY-MM"` en lugar de `"present"` para estudios o empleos que aún no han comenzado.
4. **Línea de Titular Profesional (`add_headline`)**: Insertar una línea de título debajo del nombre alineada al rol objetivo (ej. `"Nombre | Título Profesional | Stack Principal"`).
5. **Diferenciación de Certificaciones (`separate_certifications`)**: Separar claramente certificaciones completadas de las que están en curso.
6. **Cuantificación de Logros (`quantify_every_bullet`)**: Garantizar que cada viñeta de experiencia incluya métricas (%, tiempo, ahorro o volumen).
7. **Variación de Fraseo (`vary_phrasing`)**: Usar sinónimos y variaciones de contexto al nombrar skills para evitar que los algoritmos anti-IA lo marquen como texto automático.
8. **Alineación de Cargos (`match_job_title_language`)**: Reflejar el título del puesto objetivo en los cargos previos cuando aplique como alias profesional.

### Reglas de la Skill `keyword_gap_detection`
1. **Detección Automática de Brechas**: Identificar tecnologías, frameworks, protocolos o herramientas mencionadas en Experiencia o Proyectos (ej. `FastAPI`, `Playwright`, `SSE`, `Cloudflare`, `CI/CD`, `Jest`, `REST APIs / OpenAPI`) que no figuren en la sección de **Habilidades**.
2. **Enriquecimiento del Array de Skills**: Agregar automáticamente cada palabra clave exacta a la sección de Habilidades bajo su categoría correspondiente (ej: *Frameworks & Librerías*, *DevOps & Herramientas*, *Bases de Datos & Cloud*).
3. **Coincidencia Exacta para ATS**: Garantizar que las herramientas específicas utilizadas en la práctica no queden únicamente redactadas en prosa, ya que los filtros ATS realizan *exact match* sobre las listas de habilidades.

### Estándar Internacional de Fechas ("Present" vs "Actualidad")
- **CVs en Inglés**: Usar `"Present"` para roles o estudios activos (ej. `"2023-02 - Present"`). Es el estándar universal en parsers internacionales (Workday, Taleo, Greenhouse).
- **CVs en Español**: Usar `"Actualidad"` para roles activos (ej. `"2023-01 - Actualidad"`). Es el término preferido y con mejor parsing en ATS de LATAM/España. Evitar *"Presente"*, *"En curso"* (reservado solo para estudios sin concluir) u *"Hoy"*.
- **Cargos/Estudios Futuros**: Utilizar `"Inicio: YYYY-MM"`.

### Reglas de la Skill `anti_ai_detector_burstiness` (Humanización & Reducción de Detección de IA)
1. **Rotación Estructural Mandatoria**: Prohibido usar la misma plantilla gramatical en viñetas consecutivas (ej. `"Desarrollé [X] usando [Y] logrando [Z]"`).
2. **Alternancia de 4 Patrones Narrativos**:
   - **Patrón A (Resultado Primero)**: *"Incrementé la velocidad de respuesta en 40% al refactorizar..."*
   - **Patrón B (Reto/Contexto Primero)**: *"Ante cuellos de botella en el procesamiento masivo, diseñé..."*
   - **Patrón C (Acción/Arquitectura Primero)**: *"Lideré el despliegue de la arquitectura sobre AWS..."*
   - **Patrón D (Herramienta/Solución Primero)**: *"Mediante FastAPI y PostgreSQL, automaticé los flujos..."*
### Reglas de la Skill `split_achievements_vs_inprogress`
1. **Separación Estricta de Logros**: Mantener en la sección de **Logros / Achievements** únicamente aquellos títulos o certificaciones completadas y verificables (ej. `"Diplomado Big Data y BI"`, `"Curso Ágiles Design Thinking y Scrum"`).
2. **Reubicación de Formación en Curso**: Mover certificaciones o cursos en progreso (ej. `"AZ-900 en curso"`, `"AWS Cloud Practitioner (en proceso)"`) hacia la sección de **Educación** o a una categoría dedicada en Habilidades denominada *"Formación Complementaria (En Curso)"*.

### Reglas de la Skill `vary_bullet_syntax`
1. **Rotación Gramatical en Proyectos**: Evitar repetir la estructura `"Verbo + Objeto + Mediante/Con + Tecnología... Implementé el stack con X logrando Y en Z%"` en más de 2 proyectos consecutivos.
2. **Patrones de Apertura Alternativos**:
   - **Enfoque en el Problema**: *"Los equipos de bodega carecían de visibilidad en tiempo real del inventario; construí una plataforma con Laravel y React..."*
   - **Enfoque en la Métrica**: *"Reduje en un 40% los costos de infraestructura al desacoplar el procesamiento de métricas..."*
3. **Ritmo y Longitud Variable**: Alternar una oración corta con una larga entre viñetas consecutivas.

### Reglas de la Skill `natural_language_markers`
1. **Marcadores de Lenguaje Natural**: Introducir imperfecciones humanas controladas y transiciones naturales para evitar patrones robóticos.
2. **Variación de Verbos de Apertura**: Prohibido iniciar 4 viñetas consecutivas con el mismo verbo (ej. *"Desarrollé"*). Variar con: *"Construí"*, *"Diseñé e implementé"*, *"Lideré el desarrollo de"*, *"Refactoricé"*, *"Migré"*.
3. **Transiciones Variadas**: Reemplazar muletillas repetitivas como *"Implementé el stack con"* por giros narrativos auténticos.

### Reglas de la Skill `certification_evidence_link`
1. **Enlaces de Verificación de Credenciales**: Incluir URLs o badges verificables (Credly, LinkedIn Learning, badges universitarios) cuando estén disponibles para reforzar la autenticidad ante revisores humanos y sistemas ATS con validación externa.

### Reglas de la Skill `anti_repetition_project_footprint`
1. **Prohibición de Muletillas Repetidas en Proyectos**: Prohibido usar la misma muletilla de transición (ej. `"Implementé el stack con..."`, `"Construí una..."`) en múltiples proyectos. Esta repetición literal es la huella digital #1 detectada por los verificadores de texto generado por IA.
2. **Narrativa 100% Única por Proyecto**:
   - *Proyecto 1 (Enfoque Arquitectura/Innovación)*: `"Arquitecturé una plataforma basada en la orquestación de LLMs..."`
   - *Proyecto 2 (Enfoque Problema/Negocio)*: `"Para resolver la falta de seguimiento de inventario en tiempo real, diseñé..."`
   - *Proyecto 3 (Enfoque Integración Técnica)*: `"Mediante la integración de Playwright y FastAPI, automaticé..."`
   - *Proyecto 4 (Enfoque Métrica/Rendimiento)*: `"Reduje los tiempos de procesamiento en 45% al implementar..."`

---

## 4. Notas / Próximos Pasos

- [ ] Revisar y actualizar la lista de **Skills Actuales**.
- [ ] Completar los **Skills Externos** con tecnologías o conocimientos adicionales.
- [ ] Aplicar la guía de redacción a cada experiencia laboral.
