# Historial

## 2026-11-16 — Informe detallado con enlace a la conversación

- Las filas de la web y el PDF muestran cruce, fecha abreviada y enlace a las evidencias de la conversación.
- El PDF se genera detrás del proxy HTTPS de Easypanel cuando el origen del navegador coincide con el dominio de la petición. Los enlaces firmados muestran solo los archivos del corte.
- Las fichas presentan cruce y procedencia cuando constan. El color del botón indica la evaluación guardada.

## 2026-11-16 — GPS clicable y piloto de cinco conversaciones

- El detalle abre las coordenadas reconocidas en Google Maps y aumenta el tamaño del cruce y la fecha.
- El comando de piloto elige hasta cinco conversaciones de la base y encola solo Qwen con identificadores de caso. Las llamadas posteriores conservan la selección encolada.

## 2026-11-16 — Filtro del remitente y detalle legible

- El lector reconoce los alias del equipo con variantes de tildes y espacios. El ejecutor vuelve a comprobar los remitentes de trabajos antiguos antes de enviar texto a Qwen o audio al transcriptor.
- El detalle muestra solo hallazgos únicos y su fuente. Conserva los valores por campo para evaluación.

## 2026-11-15 — Detalle anidado por ciudadano y cruce

- El detalle privado abre nombre o número del ZIP, luego ubicación y, por último, los cuatro campos con sus evidencias.
- El PDF incluye los dos primeros niveles y enlaces a los archivos. Distingue evidencia del cruce y archivos de la conversación.

## 2026-11-15 — Piloto de detalle ciudadano y Qwen compacto

- El [PR #18](https://github.com/estebanoli8/semaforosCALI/pull/18) integró los cuatro campos del detalle, el PDF enlazado, las evaluaciones humanas y la alerta de formato del TXT.
- Los cortes del operador confirmaron el arranque de los dos carriles del VPS y el cierre de las 94 tareas de 34 conversaciones importadas. Dos ZIP seguían en recepción. Quedaron registradas la cobertura por campo y la latencia de Qwen. La comparación emparejada de velocidad sigue pendiente.
- Se actualizó el procedimiento de verificación con una consulta de solo lectura, estados de carga y criterios de cobertura, calidad y comparación emparejada.

## 2026-11-15 — Acción Popular

- Sesión compartida de equipo, detalle en pestaña nueva, informe del mismo corte y evaluación por evidencia.
- Normalización de vías de Cali, asociación de adjuntos a mensajes y síntesis con duraciones declaradas.
- Perfil suave de audio y reproceso selectivo de chat y audio. Cartografía aplazada.

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
