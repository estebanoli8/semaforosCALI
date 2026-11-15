# Semáforos Cali

Sistema de IA multimodal para organizar y revisar evidencia ciudadana sobre fallas de semáforos en Cali. Proyecto de Esteban Oliveros Montoya para la Maestría en Inteligencia Artificial Aplicada de la Universidad Icesi.

## Estado del proyecto

| Componente | Estado |
| --- | --- |
| Operación en el VPS | Panel privado, trabajador, PostgreSQL y almacenamiento persistente operativos en Docker y Easypanel. Ollama se ejecuta en un servicio separado del mismo VPS. |
| Ingesta | Carga reanudable de ZIP de WhatsApp. En una misma selección se sube la versión con el sufijo numérico mayor para cada nombre base. |
| Procesamiento | Dos carriles, texto y multimedia. Conserva texto literal y originales, enlaza derivaciones y muestra el avance por tarea y conversación. |
| Revisión | Panel privado con transcripciones, audio reproducible, miniaturas anotadas, microreportes e indicadores preliminares. Permite corregir transcripciones y consolidar reportes con historial. |
| Métricas de modelos | Portal privado disponible en el VPS. Filtra por experimento. El corte final de `detalle-qwen-v3` y su comparación emparejada siguen pendientes. |
| Informe y publicación | PDF general fechado y evidencias protegidas. La ruta pública `/semaforos` ofrece registros preliminares anonimizados y versiones depuradas. La cartografía del panel de Acción Popular queda para una fase posterior. |
| Acción Popular | Detalle por ciudadano y conversación, PDF enlazado, evaluación humana por modelo y alerta de formato de WhatsApp. Se confirmó el arranque de la tanda en el VPS. |
| Entregables pendientes | Cartografía en fase posterior, dominio definitivo y correo por reporte en n8n. |

Una conversación puede originar varios reportes. Los relatos independientes sobre un mismo cruce conservan registros separados. La revisión coteja fecha, ubicación, descripción y evidencias con sus fuentes.

## Detalle de reporte y piloto Qwen

- El panel privado reúne cada conversación bajo el ciudadano, con tres columnas, estado del análisis y acceso directo a las evidencias. Genera el PDF con enlaces individuales dentro del plazo indicado.
- El diagnóstico offline del **15 de noviembre de 2026** usó **22 TXT únicos**. Antes de inferir, el agrupador pasó de **25 a 20 lotes iniciales** y de **19.207 a 4.977 caracteres de mensaje**. El tiempo de inferencia y la exactitud se medirán en el VPS con la tanda pendiente. Los conteos cubren entrada, no reintentos.
- [Despliegue, migración de cola, evaluación y demostración de alerta](docs/detalle_qwen.md). [Consulta de solo lectura para obtener un corte nuevo](docs/observabilidad.md#corte-agregado-del-piloto).

## Flujo y modelos

1. El equipo carga los ZIP desde el panel privado. El núcleo guarda los archivos en el VPS y registra su procedencia en PostgreSQL.
2. El parser lee el chat y enlaza los adjuntos identificables. Los microreportes reconocen coordenadas GPS explícitas. El texto y el audio atribuidos de forma explícita a Esteban Oli se excluyen de las entradas de los modelos.
3. Los trabajadores generan transcripciones, detecciones y extracciones. La curaduría conserva por separado la predicción original y la corrección humana.

| Componente | Función | Evaluación |
| --- | --- | --- |
| Whisper Small con faster-whisper | Transcribe notas de voz y audio de video en español. Usa CPU INT8, audio mono a 16 kHz y detección de voz. | Tasa de error de palabras (WER) con transcripciones humanas de referencia. |
| YOLO11n | Detecta semáforos y dibuja cajas en fotos y fotogramas. La lectura automática de colores quedó retirada. | Precisión y exhaustividad con cajas de referencia e IoU ≥ 0,5. |
| Qwen3 4B Instruct en Ollama | Extrae daño, desde cuándo, reincidencia tras reparación, gestión, peligro y ubicación del chat y las transcripciones. Cada afirmación se vincula a una cita comprobable. | Tiempos, fallos y tokens por segundo. La exactitud por campo requiere etiquetas humanas. |
| FFmpeg | Extrae el audio y hasta 15 fotogramas por video según la regla de muestreo aprobada. | Tiempos y fallos de preparación. |

## Resultados observados en el VPS

Corte del panel del **14 de noviembre de 2026**, hora de Cali. Se registraron **163 conversaciones**, **696 archivos originales** y **3.609 tareas finalizadas**. De ellas, **3.551 quedaron completadas** y **58 registraron error**.

| Etapa | Completadas | Fallidas |
| --- | ---: | ---: |
| Transcripción de audio | 254 | 0 |
| Detección en fotos y fotogramas | 2.712 | 0 |
| Extracción de texto | 391 | 55 |
| Preparación de video | 194 | 3 |

Las tareas son ejecuciones por etapa. Una detección completada significa que terminó el análisis de una imagen. Un reporte es un registro ciudadano consolidado con sus fuentes.

Se relanzaron las 55 extracciones fallidas. En seis reintentos completados y medidos, la generación del JSON consumió el **78 %** del tiempo observado. Son casos seleccionados por un fallo previo. El rendimiento con conversaciones nuevas y la calidad de sus extracciones se evalúan por separado.

### Piloto del 15 de noviembre de 2026

El operador preparó `detalle-qwen-v3` sobre **33 conversaciones con trabajo pendiente y 3 cargas ZIP en trámite**. Se crearon **19 lotes de texto** y se reencolaron **17 tareas**. El primer corte tras el Deploy confirmó `SC_PROCESS=all`, dos trabajadores activos, **15 tareas completadas**, **2 en ejecución** y **74 pendientes**. Había **1 ZIP importado** y **2 en recepción**. La extracción de texto tenía **1 tarea en curso y 37 pendientes** en ese corte.

El corte confirma arranque y avance paralelo. La completitud final por campo, las extracciones compactas finalizadas y la mejora de tiempo requieren un corte posterior. El antecedente del 14 de noviembre y el análisis offline de 22 TXT tienen poblaciones y unidades distintas. Para evaluar velocidad, medir sobre las mismas fuentes con ambos perfiles y registrar la calidad por campo. [Registro y método de validación](docs/detalle_qwen.md#piloto-en-el-vps).

## Uso y verificación

- **Acción Popular.** Entra una vez con la clave del equipo. **Detalle de reporte** muestra las conversaciones y el botón de PDF del mismo corte. Cada enlace de evidencia abre la conversación en una pestaña nueva, con cruce asociado, momento del mensaje, transcripción o estado del modelo y evaluación humana. **Desempeño de modelos** y **Cargue de ZIP** usan la misma sesión.
- **Reproceso.** Tras desplegar, ejecuta `python -m semaforos.reprocess` para estimar el lote. Prueba con `--conversation UUID --apply` antes de encolar todo con `--apply`. Se reutilizan las detecciones visuales y los artefactos del video. Consulta el [procedimiento de Acción Popular](docs/accion_popular.md).
- El panel privado permite subir nuevos ZIP mientras el trabajador procesa los anteriores. Se pueden cargar las conversaciones conforme se exportan de WhatsApp.
- La consulta pública genera su corte a partir de lo que ya está guardado. La tabla prioriza cruces identificados e incluye conteos por intersección y por tipo de evidencia. Los indicadores superiores cuentan reportes, fotos, videos, audios y cruces. Los enlaces abren un visor privado compartido por los tipos de evidencia, con lectura del TXT completo, fotos con cajas cuando hay detecciones y audio y video a 1×, 1,5× o 2×. Se ingresa una vez por sesión con la clave del equipo. El mapa aparece debajo de la tabla mientras no tenga puntos. La guía explica cómo se agrupan los relatos y cuándo sus ubicaciones se pueden mostrar en el mapa.
- El portal de métricas se abre desde **Desempeño de modelos** o en la ruta `/metricas`, con la clave del equipo. Muestra actividad, tiempos, fallos, salidas parciales y calidad cuando existen referencias humanas.
- Para desplegar desde `main`, usar **Easypanel → semaforos → semaforos-core → Deploy**. Planificarlo al terminar el lote, porque el reemplazo del contenedor interrumpe las tareas activas.
- [GitHub Actions](https://github.com/estebanoli8/semaforosCALI/actions) verifica el núcleo con PostgreSQL y el panel con Chromium, incluida la vista móvil. Las pruebas usan datos sintéticos. Las cifras del piloto provienen del VPS.

Las pruebas locales del comparador y los prototipos usan Python 3.11 y FFmpeg/ffprobe.

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s prototype/v0_3 -p 'test_*.py' -v
python -m unittest discover -s prototype/v0_4 -p 'test_*.py' -v
```

Para comparar ejecuciones sobre el mismo conjunto de datos y las mismas etiquetas:

```bash
python tools/compare_runs.py runs/base.json runs/candidato.json --output runs/comparacion.md
```

## Documentación

- [Arquitectura](docs/arquitectura.md), [carga web](docs/carga_web.md) y [despliegue en Easypanel](docs/despliegue_easypanel.md).
- [Curaduría y dos carriles](docs/curaduria_rendimiento.md), [audio y microreportes](docs/audio_y_microreportes.md), [consolidación y revisión](docs/reportes_revision.md) y [seguimiento de la cola](docs/observabilidad.md).
- [Mapa, PDF, pausa y validación integral](docs/mapa_e_informe.md).
- [Diseño de experimentos](docs/experimentos.md), [diccionario aprobado el 8 de noviembre](docs/diccionario.md) y [checkpoint inicial](docs/estado.md). Las decisiones posteriores sobre selección de ZIP y lectura de luces se reflejan en el estado actual de este README.
- [Historial de cambios](CHANGELOG.md).

## Regla de mantenimiento

**Cada mejora debe actualizar este README en el mismo PR.** Registrar qué cambió, cómo se usa o valida y su estado de despliegue. Para cambios de alcance, modelos, datos o configuración, enlazar la documentación técnica correspondiente. Fechar los resultados del VPS e identificar su origen y denominador.

GitHub contiene código y ejemplos sintéticos. Originales ciudadanos, contactos, pesos de modelos, salidas privadas y secretos se mantienen fuera del repositorio.
