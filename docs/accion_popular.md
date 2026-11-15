# Acción Popular · revisión y reproceso

El panel privado reúne Reporte, Desempeño de modelos, Detalle de reporte y Cargue de ZIP. La clave abre una sesión HTTPS de cuatro horas compartida en el mismo navegador. Los enlaces de evidencia abren otra pestaña. Los enlaces de descarga temporales del PDF se generan solo si el equipo marca esa opción.

## Interpretación y revisión

- La tabla y el PDF del panel priorizan intersecciones reconocidas y presentan la misma Situación presentada del detalle. Se conservan filas independientes por reportante, conversación, fecha y cruce. El conteo por cruce incluye cada fila. El mapa privado y la geocodificación quedan para una fase posterior.
- El intérprete reconoce variantes de nomenclatura caleña y conserva la fuente literal. Un cruce parcial o una secuencia numérica ambigua queda pendiente de confirmar. Los metadatos de adjuntos muestran el cruce y su fuente, cuando hay un vínculo claro con el mensaje, otras líneas del mismo remitente o el audio del video. La hora se presenta en America/Bogota.
- El detalle muestra la nota de voz original y su transcripción. Bajo cada video aparece la transcripción de su pista, y bajo el chat TXT, la extracción disponible. El análisis de cada fuente indica si está pendiente, en proceso, incompleto o fallido. Las imágenes muestran la miniatura original o anotada y los fotogramas conservan el archivo derivado previo.
- La evaluación queda registrada por ejecución. En fotogramas, Observados cuenta los semáforos visibles según la persona y Detectados las cajas que esa persona revisó. En las salidas de texto y audio, Detectó ubicación registra sí o no. Sin guardar significa pendiente de evaluación. Estas etiquetas se conservan en PostgreSQL y no alteran las métricas existentes de cajas o WER.

## Easypanel

1. Despliega `semaforos-core` al commit actualizado desde `main`. Abre el panel por HTTPS y verifica que la sesión se conserve al entrar a otra sección. Confirma que el trabajador está activo (`SC_PROCESS=all` en instalación de un servicio o worker separado en la variante dividida).
2. Desde la terminal del contenedor, en `/app`, ejecuta la estimación. Esta consulta por cuáles archivos se podría encolar y no modifica la cola.

   ```bash
   /usr/local/bin/python -m semaforos.reprocess
   ```

3. Selecciona una conversación con chat, voz y video. Usa su UUID del registro de conversación, no el código visible del reporte. Ejecuta el piloto y espera sus resultados.

   ```bash
   /usr/local/bin/python -m semaforos.reprocess --conversation UUID_DE_CONVERSACION --apply
   ```

4. En Reporte y Detalle, coteja literalidad, números de las vías, adjuntos, fecha y contexto. Compara un audio limpio y uno ruidoso con sus originales. Los derivados de voz se guardan aparte con el perfil `voice-v2` (mono, 16 kHz y atenuación suave de ruido). El reconocimiento sigue usando Whisper Small y los mismos recursos configurados. Qwen mantiene la verificación por citas.
5. Cuando el piloto corresponda a los originales, encola el lote. Sigue en Cargue de ZIP el avance por tarea y en Desempeño de modelos filtra por `accion-popular-v2`.

   ```bash
   /usr/local/bin/python -m semaforos.reprocess --apply
   ```

Con la misma versión de código y configuración, repetir el comando reutiliza las solicitudes ya encoladas. Las cifras que imprime son fuentes candidatas. El reproceso encola chat y pistas de audio existentes, que a su vez generan extracciones de texto. Conserva ZIP, videos, fotos, fotogramas, detecciones y ejecuciones anteriores. Un video que nunca produjo pista de audio queda señalado en el detalle y requiere tratar por separado su preparación.
