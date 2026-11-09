# Comparación conservadora de exportaciones

API privada: `GET /conversation-comparison?left_parse_id=UUID&right_parse_id=UUID`.
Seleccionar índices obtenidos de `/evidence/{id}/chat-parses`. El panel privado permite cargar exportaciones paginadas, seleccionar dos índices y consultar su comparación. La búsqueda automática de candidatos sigue pendiente.

Compara remitente visible, marca temporal literal y cuerpo exacto, manteniendo multiplicidad y orden. Detecta contenido comparable idéntico, contención ordenada, solapamiento o ausencia de coincidencias. No usa nombres ZIP ni sufijos (1)/(2), ni fecha de carga para afirmar cuál es más reciente. Mensajes sin remitente o marca temporal y registros de sistema no participan y se cuentan aparte.

Es una propuesta de relación textual, nunca una confirmación de identidad o una fusión. No compara adjuntos: dos exportaciones con texto idéntico podrían incluir archivos distintos. Cambios de formato o nombre del contacto pueden disminuir coincidencias y necesitan revisión. Se rechazan configuraciones de parser diferentes y comparaciones de más de 10.000 mensajes por lado para acotar memoria en el VPS.

No modifica reportes, evidencia ni conteos. Pendiente: interfaz, confirmación persistente de relaciones, reconciliación de adjuntos y agrupación automática de hechos. Siete pruebas unitarias sintéticas cubren duplicados, orden, fechas, remitentes e incertidumbre; no equivalen a evaluación con datos reales.

## Decisión e historial (2026-11-09)

`POST /export-relations` registra misma conversación, distintas o pendiente con revisor declarado, motivo, fecha y comparación original. `GET /export-relations` devuelve historial paginado; el panel muestra las 20 últimas decisiones. Se exige versión esperada para impedir sobrescrituras concurrentes. Una petición repetida conserva el mismo resultado. La relación se registra entre dos índices, sin inferir transitividad ni reconciliar adjuntos ni fusionar reportes. Correcciones crean otra versión. La identidad del revisor es declarada bajo la clave del equipo.

Migración 005; pruebas PostgreSQL para idempotencia, conflictos, historial, acceso privado y conservación de conversaciones. Prueba de navegador para selección, comparación y decisión. Estas pruebas usan datos sintéticos.
