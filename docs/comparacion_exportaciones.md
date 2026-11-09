# Comparación conservadora de exportaciones

API privada: `GET /conversation-comparison?left_parse_id=UUID&right_parse_id=UUID`.
Seleccionar índices obtenidos de `/evidence/{id}/chat-parses`. Es una comparación explícita entre dos índices, todavía sin selector visual ni búsqueda automática de candidatos.

Compara remitente visible, marca temporal literal y cuerpo exacto, manteniendo multiplicidad y orden. Detecta contenido comparable idéntico, contención ordenada, solapamiento o ausencia de coincidencias. No usa nombres ZIP ni sufijos (1)/(2), ni fecha de carga para afirmar cuál es más reciente. Mensajes sin remitente o marca temporal y registros de sistema no participan y se cuentan aparte.

Es una propuesta de relación textual, nunca una confirmación de identidad o una fusión. No compara adjuntos: dos exportaciones con texto idéntico podrían incluir archivos distintos. Cambios de formato o nombre del contacto pueden disminuir coincidencias y necesitan revisión. Se rechazan configuraciones de parser diferentes y comparaciones de más de 10.000 mensajes por lado para acotar memoria en el VPS.

No modifica reportes, evidencia ni conteos. Pendiente: interfaz, confirmación persistente de relaciones, reconciliación de adjuntos y agrupación automática de hechos. Siete pruebas unitarias sintéticas cubren duplicados, orden, fechas, remitentes e incertidumbre; no equivalen a evaluación con datos reales.
