# Propuestas de agrupación — 2026-11-09

El panel privado ofrece **Proponer agrupaciones de esta conversación**. La regla versionada `message-grouping-v1` agrupa afirmaciones por mensaje fuente inequívoco; una transcripción vinculada explícitamente puede compartir ese mensaje. Cada propuesta se revisa antes de crear el reporte. No se impone un reporte por mensaje ni se guarda nada al elegir la propuesta.

Una única ubicación literal (ignorando mayúsculas y espacios externos) y alguna descripción del daño permiten sugerir un candidato. Varias ubicaciones, ubicación ausente, falta de daño, más de 200 afirmaciones o fuente sin mensaje dejan advertencia de contexto/separación. Una frase podría contener más de un hecho aunque la ubicación coincida: el operador sigue decidiendo. Las equivalencias semánticas entre direcciones no se adivinan.

Las fuentes ya agrupadas muestran los reportes activos relacionados. Para exportaciones diferentes, solo se consultan relaciones directas cuya última decisión humana sea `misma_conversacion`. Si remitente visible, marca temporal literal y cuerpo coinciden exactamente y el otro mensaje tiene afirmaciones textuales vinculadas a un reporte activo, se muestra un **posible reporte en otra exportación**. No confirma duplicación: pueden existir ocurrencias idénticas y adjuntos diferentes. No se aplica transitividad ni se equiparan transcripciones de audios sin comparar los archivos.

El panel permite consultar ese otro reporte sin trasladar sus fuentes. El operador aún no puede consolidar automáticamente reportes entre conversaciones. Retirar la confirmación de relación elimina la sugerencia en la siguiente consulta; las decisiones anteriores siguen conservadas.

API privada `GET /report-proposals?conversation_id=UUID&offset=0&limit=20`: hasta 50 grupos por página, 2.000 afirmaciones por respuesta; si se supera este último límite se solicita reducir la página. No carga un lote completo en memoria. No consulta modelos adicionales ni altera métricas, originales o conteos.

Pruebas sintéticas: ausencia de creación automática, señales de ambigüedad, fuentes existentes, relación confirmada/revocada, fechas distintas, acceso privado, paginación y selección de propuesta en navegador. La calidad semántica con reportes reales sigue pendiente. La agrupación automática completa y la reconciliación de adjuntos no se consideran terminadas.
