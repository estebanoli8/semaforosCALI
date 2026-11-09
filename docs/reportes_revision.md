# Consolidación y revisión privada — v0.8

## Alcance implementado

Las salidas textuales completadas se indexan en afirmaciones con su variable, origen, cita literal, posición, fecha del mensaje cuando existe, evidencia, transcripción y ejecuciones de modelo. La cita presentada elimina etiquetas `<attached:...>`/`<adjunto:...>`; la cita y los originales permanecen íntegros. No se usa el resumen para reemplazar la narración.

Repetir un experimento sobre la misma fuente y la misma cita/posición reutiliza la afirmación y añade otra referencia de predicción. Distintos experimentos siguen teniendo métricas y salidas propias. Cambiar el parser o la transcripción puede producir otra interpretación que debe compararse, no fusionarse a ciegas. Antes de indexar se comprueba que el fragmento procede realmente del chat/transcripción almacenado; las citas inventadas o las entradas alteradas no crean afirmaciones.

La migración `004_reports.sql` agrega afirmaciones, referencias de predicción, reportes, asociaciones y eventos versionados. No modifica las migraciones anteriores.

## Uso del panel

1. Entrar al panel privado y pulsar **Cargar conversaciones**. Elegir una conversación; todas las listas tienen paginación, también con más de 100 conversaciones.
2. Leer las afirmaciones y abrir su fuente original. Seleccionar las que describan un mismo hecho, incluso en varias páginas.
3. Elegir explícitamente una fuente principal: su mensaje define la fecha del reporte. Si el audio no tiene un vínculo inequívoco con un mensaje de WhatsApp, su fecha queda desconocida.
4. Indicar el nombre del revisor y el motivo. Crear un reporte, complementar uno abierto o reemplazar su agrupación conservando el historial.
5. Cotejar las fuentes y marcar revisado, mantener pendiente o descartar. “Revisado” no significa inspección física ni certificación del daño.

Esta versión implementa **consolidación asistida por el operador**. No cuenta automáticamente cada ZIP, mensaje, predicción o fotograma como un reporte. Una conversación con varios cruces se puede dividir en varios reportes. Una referencia complementaria se añade al existente. La propuesta automática de grupos y la reconciliación confirmada entre exportaciones ampliadas siguen pendientes; esto no cambia la regla aprobada, limita lo implementado en esta etapa.

Los reportes se guardan inmediatamente con `revision=pendiente`. El detalle expone las ocho listas aprobadas: ubicación, daño, tiempo declarado y afectaciones, separadas entre texto y audio. Una lista vacía no significa que una modalidad se haya procesado exitosamente; el estado de procesamiento se muestra aparte.

## Historial y protección contra duplicados

- Cada operación lleva un UUID de petición: reenviar la misma operación no crea otro reporte ni otra versión.
- Una agrupación idéntica de fuentes ya vigente se rechaza incluso con otra petición. Una superposición parcial es visible en la tabla; corresponde al revisor decidir si hay un complemento o un hecho distinto.
- Dos personas no pueden sobrescribirse silenciosamente: una versión desactualizada se rechaza y hay que recargar el reporte.
- Agregar o reemplazar fuentes vuelve a dejar la revisión pendiente. Las predicciones originales no se corrigen ni se usan para reentrenar.
- Cada evento guarda revisor declarado, motivo, fecha y captura de la versión, incluidos sus vínculos a fuentes. Descartar retira del conteo vigente, conserva el reporte y todas sus versiones.
- Un procesamiento posterior sobre las evidencias del reporte activa `review_outdated` y `revision_effective=pendiente` en el detalle. El estado original de la decisión permanece en el historial. Las listas muestran la última decisión registrada; al abrir se informa si está desactualizada. El portal público futuro deberá usar el estado efectivo.
- No se fusionan fuentes de conversaciones distintas sin resolver esa relación; el API devuelve un conflicto explícito. La reconciliación de exportaciones ampliadas no está resuelta todavía.

## Evidencia y procesamiento

Se incluyen las evidencias de las afirmaciones, los adjuntos explícitamente vinculados a sus mensajes y los padres/derivados de esos archivos. Así, un audio extraído mantiene su video fuente. Esto documenta la relación de origen; no asegura que todas las imágenes describan el mismo cruce. Las asociaciones semánticas que sean ambiguas necesitan revisión.

El estado de procesamiento se calcula sobre las tareas de esas evidencias. En un chat con varios reportes es conservador: puede permanecer pendiente mientras termina otra extracción del mismo archivo. No se afirma que el reporte esté completo si aún quedan tareas relacionadas. La revisión de la agrupación no sustituye el etiquetado de calidad de transcripción, cajas y luces, que continúa por `/reviews`.

## Rutas privadas

`GET /conversations`, `GET /findings?conversation_id=...`, `GET /reports`, `GET /reports/{id}`, `GET /reports/{id}/history` y `GET /evidence/{id}/download` requieren Bearer. La descarga entrega el original como adjunto y comprueba contención de ruta; no publica el volumen.

`POST /reports` crea; `POST /reports/{id}/changes` recibe `attach`, `replace` o `review`. Se exige revisor y motivo. El revisor es declarado bajo la clave del equipo: todavía no hay cuentas individuales verificadas. El historial es trazabilidad técnica sencilla, no firma digital.

Todo sigue privado. No hay envío de correo, publicación ciudadana ni documento PDF en este bloque. El código no instala ni modifica el VPS.

## Verificación

Pruebas PostgreSQL con datos sintéticos: cita respaldada por la fuente, reutilización entre experimentos, idempotencia, grupos duplicados, división de cruces, complemento, reemplazo, conflictos de versiones, descarte, conservación de fuentes, privacidad, fechas de audio y rechazo de agrupaciones entre conversaciones sin resolver. La prueba Chromium recorre selección de fuentes y creación de reporte, además de la carga reanudable y vista móvil.

La inferencia de estas pruebas es simulada. La evaluación con exportaciones reales y modelos locales sigue pendiente. Siguientes componentes: reconciliación entre versiones de conversación y agrupación propuesta, mapa, PDF general, correo/n8n y empaquetado/despliegue integral.
