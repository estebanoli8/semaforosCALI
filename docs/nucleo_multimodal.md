# Núcleo multimodal v0.6 — implementación y límites

Fecha: 2026-11-08. Código en `semaforos/`. Es una etapa de integración privada: todavía no sustituye el portal existente ni es el instalador completo.

## Qué implementa

- PostgreSQL exclusivo: conversaciones, ZIP fuente, evidencias, literalidad del chat, cola, intentos, ejecuciones, transcripciones, cajas, lectura por luz, etiquetas y métricas. Migración numerada con SHA-256; no se modifica una migración ya aplicada.
- Importación privada por CLI de ZIP locales. Conserva archivos y nombres originales; deduplica contenido idéntico aunque cambien compresión o fecha. Las exportaciones ampliadas todavía requieren consolidación de conversación/reportes: no se publica un conteo definitivo desde este núcleo.
- Una inferencia pesada a la vez, bloqueo de sesión PostgreSQL, adquisición atómica, lease renovable, reintentos limitados y conservación del historial. Cada inferencia corre en un proceso separado que libera RAM al terminar.
- Audio con faster-whisper en CPU/int8. Transcripción literal y segmentos separados de correcciones humanas. Posteriormente Qwen extrae afirmaciones con cita y fuente verificables.
- Imágenes: YOLO11n detecta semáforos y genera copia anotada. Otra etapa usa Qwen3-VL 2B local en Ollama para leer luces por recorte. Booleanos rojo/amarillo/verde admiten null. Las cajas demasiado pequeñas quedan indeterminadas sin llamar al VLM. El rendimiento/calidad de esta combinación está pendiente de evaluación real.
- Videos: reutiliza el muestreo ya probado, extrae audio y cuadros con referencias al video, y encola audio/foto mediante los mismos adaptadores. Máximo inicial 600 s configurable; nunca recorta un video largo silenciosamente.
- MLOps: configuración, versión del código, huellas de entrada, identidad real del modelo, prompts, tiempos y consumo del proceso. Salidas e intentos anteriores permanecen. Un ID de experimento nuevo permite comparar otra ejecución; repetir una solicitud idéntica dentro del mismo experimento no crea otro trabajo.
- API privada para consultar trabajos/ejecuciones, pedir reprocesamiento y guardar etiquetas. WER, detecciones a IoU 0.5 y cobertura/acierto de luces calculados sobre etiquetas aportadas. Sin etiquetas no se inventan métricas de calidad.

La carga web reanudable y el seguimiento privado están descritos en [carga_web.md](carga_web.md). La importación se ejecuta en el trabajador, fuera de la petición HTTP y antes de la siguiente inferencia.

## Modelos y configuración

`config/modelos.json` sí se carga en este núcleo; es independiente de `config/experimento.example.json` (propuesta antigua). Cambiar parámetros crea una configuración identificable. Los trabajos ya en cola mantienen su configuración original.

| Etapa | Inicial | Parámetros principales |
|---|---|---|
| Audio | Systran/faster-whisper-small | revisión, idioma, int8, hilos, beam, VAD |
| Detección | yolo11n.pt local | SHA esperado, resolución, confianza, IoU, máximo de cajas |
| Luces | qwen3-vl:2b en Ollama | digest esperado, tamaño mínimo, contexto, tokens, hilos |
| Texto | qwen3:4b-instruct existente | digest esperado, contexto, tokens, hilos |

Las revisiones/digests pueden fijarse después de instalar y verificar. Cuando no se fijan, se registra la identidad resuelta en cada ejecución, pero no se promete repetir exactamente una descarga futura de un tag mutable. Para comparaciones reproducibles, fijar revisiones y pesos antes de lanzar el conjunto etiquetado. No hay caché automática entre experimentos distintos.

Qwen3-VL es candidato inicial para luces, no un clasificador validado para los cruces de Cali. El detector general por sí solo no decide si una luz está encendida. La clasificación visual no certifica una avería. El texto del ciudadano conserva su condición de declaración.

## API privada

Autenticación: `Authorization: Bearer <SC_API_TOKEN>`, mínimo 32 caracteres. No publicar el token ni incluirlo en GitHub. Todas las rutas de datos y acciones requieren autenticación. Solo la carcasa estática de acceso (/, /panel.js, /panel.css) es pública y no contiene datos; no es aún la proyección ciudadana.

| Ruta | Operación |
|---|---|
| GET /health | Base accesible y espacio en filesystem |
| GET /jobs?offset=0&limit=50 | Estados paginados, experimentos y errores de expansión |
| POST /jobs | evidence_id y experiment_id: solicita etapa correspondiente |
| GET /runs/{id} | Resultado, modelo y métricas de una ejecución |
| POST /reviews | run_id, field, label, reviewer, comment: conserva etiqueta y predicción por separado |

Campos de revisión: transcription (texto), boxes (lista xyxy en imagen orientada), lights (detection_id y tres booleanos/null), assertions (lista). En assertions todavía solo se almacena la etiqueta; cálculo de precisión/recall semántico pendiente. WER usa palabras Unicode en minúsculas sin puntuación. Para luces, accuracy_answered excluye abstenciones y coverage las hace explícitas; no es F1. Métricas individuales no equivalen al resultado agregado de un dataset.

## Operación de desarrollo

Variables: `SC_DATABASE_URL`, `SC_STORAGE`, `SC_MODEL_CONFIG`, `SC_MODELS_DIR`, `SC_API_TOKEN`, `OLLAMA_URL`, `SC_RESERVE_BYTES`. La base debe llamarse `semaforos_*`; el esquema es `semaforos`. Nunca apuntar a una base de otro proyecto. SC_TEST_DSN solo se usa en una base temporal llamada exactamente semaforos_test.

```bash
python -m semaforos migrate
python -m semaforos import /ruta/privada/conversacion.zip --experiment exploracion-01
python -m semaforos worker
uvicorn semaforos.api:create_app --factory --host 0.0.0.0 --port 8000
```

Estos son comandos del entorno de desarrollo; todavía no son instrucciones para cambiar el VPS del usuario. La instalación integral reunirá configuración, preparación de pesos, importación histórica y arranque.

`deploy/compose.core.yaml` y `deploy/Dockerfile.core` son candidatos de empaquetado. Solo exponen el puerto interno de API; no publican PostgreSQL ni modelos. Hace falta comprobar conexión a la red interna de Ollama/Easypanel y el presupuesto total de recursos (incluido Ollama y otros servicios). Los pesos YOLO deben existir en /models/yolo11n.pt; el VLM debe estar disponible en Ollama. El adaptador Whisper resuelve la descarga en su volumen de modelos. No se ha probado aún la construcción de esta imagen completa ni la inferencia real en VPS.

## Lo que falta

La carga web del núcleo ya usa PostgreSQL y no activa la cola SQLite del prototipo v0.4. Falta migrar resultados históricos sin enviar correos; completar parser/fechas y consolidación de mensajes, versiones y reportes; ejecutar modelos con archivos reales; panel de evaluación, mapa, PDF, correo y flujo n8n. Las afirmaciones extraídas por fragmentos son candidatos privados y no se cuentan como reportes ciudadanos finales. El particionado literal conserva caracteres pero puede separar contexto; su consolidación es una etapa pendiente.

Las pruebas automáticas de contrato y PostgreSQL usan predicciones sintéticas para verificar persistencia, recuperación y etiquetado. No acreditan calidad de Whisper, YOLO ni Qwen.

## Fuentes técnicas verificadas

- https://github.com/SYSTRAN/faster-whisper
- https://docs.ultralytics.com/modes/predict/
- https://docs.ultralytics.com/models/yolo11/
- https://ollama.com/library/qwen3-vl:2b
- https://docs.ollama.com/api/chat
- https://www.psycopg.org/psycopg3/docs/basic/usage.html
- https://www.postgresql.org/docs/current/explicit-locking.html
