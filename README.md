# Semáforos Cali

Sistema de IA multimodal para organizar y revisar evidencia ciudadana sobre fallas de semáforos en Cali. Proyecto de Esteban Oliveros Montoya para la Maestría en Inteligencia Artificial Aplicada de la Universidad Icesi.

## Estado del proyecto

| Componente | Estado |
| --- | --- |
| Operación en el VPS | Panel privado, trabajador, PostgreSQL y almacenamiento persistente operativos en Docker y Easypanel. Ollama se ejecuta en un servicio separado del mismo VPS. |
| Ingesta | Carga reanudable de ZIP de WhatsApp. En una misma selección se sube la versión con el sufijo numérico mayor para cada nombre base. |
| Procesamiento | Dos carriles, texto y multimedia. Conserva texto literal y originales, enlaza derivaciones y muestra el avance por tarea y conversación. |
| Revisión | Panel privado con transcripciones, audio reproducible, miniaturas anotadas, microreportes e indicadores preliminares. Permite corregir transcripciones y consolidar reportes con historial. |
| Métricas de modelos | Portal privado integrado en `main` por el [PR #11](https://github.com/estebanoli8/semaforosCALI/pull/11). El despliegue de esta versión en el VPS está pendiente de confirmación. |
| Mapa e informe | Portal privado con ubicación revisada y PDF general fechado. La ruta pública `/semaforos` incluye automáticamente los resultados disponibles de conversaciones procesadas como registros preliminares anonimizados. También muestra las versiones depuradas que el equipo haya editado. Despliegue y prueba en el VPS pendientes de confirmación. |
| Entregables pendientes | Cargar la cartografía oficial en el VPS, conectar el dominio definitivo y activar correo por reporte mediante n8n. |

Una conversación puede originar varios reportes. Los relatos independientes sobre un mismo cruce conservan registros separados. La revisión coteja fecha, ubicación, descripción y evidencias con sus fuentes.

## Flujo y modelos

1. El equipo carga los ZIP desde el panel privado. El núcleo guarda los archivos en el VPS y registra su procedencia en PostgreSQL.
2. El parser lee el chat y enlaza los adjuntos identificables. Los microreportes reconocen coordenadas GPS explícitas. El texto y el audio atribuidos de forma explícita a Esteban Oli se excluyen de las entradas de los modelos.
3. Los trabajadores generan transcripciones, detecciones y extracciones. La curaduría conserva por separado la predicción original y la corrección humana.

| Componente | Función | Evaluación |
| --- | --- | --- |
| Whisper Small con faster-whisper | Transcribe notas de voz y audio de video en español. Usa CPU INT8, audio mono a 16 kHz y detección de voz. | Tasa de error de palabras (WER) con transcripciones humanas de referencia. |
| YOLO11n | Detecta semáforos y dibuja cajas en fotos y fotogramas. La lectura automática de colores quedó retirada. | Precisión y exhaustividad con cajas de referencia e IoU ≥ 0,5. |
| Qwen3 4B Instruct en Ollama | Extrae ubicación, daño, duración declarada y afectaciones desde el chat y las transcripciones. Cada afirmación se vincula a una cita comprobable. | Tiempos, fallos y tokens por segundo. La exactitud por campo requiere etiquetas humanas. |
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

## Uso y verificación

- El panel privado permite subir nuevos ZIP mientras el trabajador procesa los anteriores. Se pueden cargar las conversaciones conforme se exportan de WhatsApp.
- La consulta pública genera su corte a partir de lo que ya está guardado. Muestra cruces y menciones reconocibles, estado de procesamiento y conteos de registros preliminares. La guía explica cómo se agrupan los relatos y cuándo sus ubicaciones se pueden mostrar en el mapa.
- El portal de métricas se abre desde **Métricas de modelos** o en la ruta `/metricas`, con la clave del equipo. Muestra actividad, tiempos, fallos, salidas parciales y calidad cuando existen referencias humanas.
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
