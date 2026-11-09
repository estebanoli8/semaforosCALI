# Historial

## 2026-11-08 — v0.8 consolidación asistida

- Afirmaciones verificadas contra texto fuente, reutilizadas entre ejecuciones compatibles con referencias a cada predicción.
- Reportes privados con ocho variables, fuente principal, revisión y capturas versionadas.
- Panel para agrupar, complementar, reemplazar, revisar y descartar, con peticiones idempotentes y control de concurrencia.
- Pruebas de PostgreSQL y recorrido del panel en Chromium con datos sintéticos. No acredita evaluación real ni despliegue.

## 2026-11-08 — v0.7 mensajes fuente

- Parser iOS/Android, fechas UTC con supuestos explícitos, cuerpo y cabecera literal.
- Índice PostgreSQL versionado, adjuntos vinculados por nombre explícito único, fuentes del modelo con ID y fecha del mensaje.
- API privada paginada para explorar mensajes y lecturas previas; pruebas sintéticas y PostgreSQL.
- Corregido runner de prueba web a Ubuntu 24.04 compatible con Playwright fijado.
- No implica consolidación final de reportes, evaluación de modelos reales ni despliegue VPS.

## Base de desarrollo — 2026-11-08

- Incorporado prototipo v0.3 existente con sus pruebas.
- Registrados diccionario y seis decisiones aprobadas.
- Documentadas arquitectura modular, experimentación y operación.
- Añadido comparador de métricas JSON y pruebas de regresión del comparador.
- Configuración de experimentos propuesta; todavía no conectada al worker.
- Pipeline de pruebas en GitHub; sin despliegue automático ni datos ciudadanos.

## 2026-11-08 — v0.4 carga continua

- Más de 100 conversaciones y llegadas diarias variables como requisito.
- Carga por bloques, verificación SHA-256, reanudación y validación asíncrona.
- Protección de espacio disponible y cancelación explícita de cargas incompletas.
- 11 pruebas locales (incluyen 125 cargas sintéticas); no desplegado en VPS.

## 2026-11-08 — núcleo privado v0.5

- PostgreSQL, cola con lease y una inferencia pesada a la vez.
- Adaptadores Whisper, YOLO, Qwen-VL y Qwen textual; resultados con procedencia.
- Etiquetas humanas y métricas por ejecución; conservación de predicciones.
- API privada y empaquetado candidato; no desplegado ni evaluado con modelos reales.

## 2026-11-08 — núcleo privado v0.6

- Carga web por bloques integrada con PostgreSQL; ninguna cola SQLite nueva.
- Migración 002 independiente, configuración de cada carga congelada y recuperación de importaciones interrumpidas.
- Panel privado con espacio libre, paginación, cancelación, reintentos y consulta de salidas; clave solo en memoria de pestaña.
- Importación y modelos comparten bloqueo de trabajador; CLI respeta ese bloqueo.
- Pruebas de carga HTTP → ZIP → tareas → predicción sintética, duplicados, reserva de disco y recuperación.
- Inferencia real, publicación ciudadana y despliegue en VPS siguen pendientes.
