# Semáforos Cali — diccionario y decisiones aprobadas

Fecha: 8 de noviembre de 2026, Colombia. Versión: 1.0 aprobada.
Estado: APROBADO por Esteban el 8 de noviembre de 2026. Las seis decisiones, variables e indicadores quedan vigentes. No acredita implementación ni despliegue.
Referencia: Checkpoint_Semaforos_Cali_2026-11-06.md y conversación posterior sobre una entrega integral instalable.

## 1. Propósito de esta revisión

Cerrar las reglas que cambian qué cuenta el sistema, qué conserva, qué muestra y cuándo notifica. La propuesta combina las definiciones previas con recomendaciones explícitas para los vacíos. Las elecciones de bibliotecas, índices SQL, límites concretos del servidor y empaquetado las resolverá el desarrollo, después de inspeccionar compatibilidad y recursos.

Se conserva el alcance: carga privada al VPS, originales y literalidad, modelos preentrenados, análisis de texto/audio/fotos y audio/fotogramas de video, n8n, Docker, revisión humana, evaluación MLOps, tabla/mapa/indicadores, PDF general y correo por nuevo reporte. Conjunto exploratorio: 36 conversaciones. No reentrenamiento, chatbot, Drive ni publicación en X en esta entrega.

## 2. Seis decisiones aprobadas

| N.º | Decisión | Regla aprobada |
|---|---|---|
| 1 | Cuándo nace otro reporte | Una nueva observación explícita de un cruce en otro momento genera otro reporte. Mensajes, fotos y audios complementarios del mismo hecho enriquecen el existente. Otro cruce genera otro reporte. La fecha del mensaje por sí sola no demuestra que haya una nueva observación. Si la relación es ambigua, queda por revisar. |
| 2 | ZIP repetidos y exportaciones ampliadas | Conservar las versiones y relacionarlas con la conversación cuando haya evidencia suficiente. Omitir contenido idéntico; reutilizar resultados compatibles de archivos ya procesados y analizar las adiciones con contexto. Los sufijos (1)/(2) o las fechas del ZIP no deciden solos cuál es la versión más reciente. No borrar históricos ni sumar otra vez reportes repetidos. |
| 3 | Publicación y PDF de pendientes | Mostrar automáticamente los datos publicables y resultados disponibles con la etiqueta “revisión humana pendiente”; mantener visibles los estados de procesamiento parcial. Incluir pendientes en el PDF general, identificados. Contactos, chats completos y originales permanecen privados. El acceso del juez a originales se concede mediante enlace autenticado. Un registro descartado queda en el historial privado y sale de los conteos públicos. |
| 4 | Momento y alcance del correo | Un correo por reporte nuevo cuando sus etapas aplicables terminen, o cuando quede parcial por errores definitivos después de reintentos limitados. Solo variables y enlaces. La migración de las 36 conversaciones no dispara correos históricos. Las correcciones y reintentos no originan otro correo automático. |
| 5 | Lectura visual incierta | Por cada semáforo: luces roja, amarilla y verde con valores sí/no/no determinable. “Ninguna luz visible” solo cuando la imagen permite evaluar las tres. Mantener separados “no se detectó semáforo” y “luces no determinables”. Ninguna de estas predicciones certifica una avería. |
| 6 | Segundo final incompleto en video | Mantener el muestreo por intervalos de un segundo alineados al inicio; contar el último intervalo aunque esté incompleto. Primero, último cuadro de cada uno de los primeros diez intervalos; después, primer cuadro de los últimos cinco intervalos no cubiertos. Máximo 15, sin repetir intervalos. Ejemplos: 8,4 s → hasta 9; 12 s → 12; 14,4 s → hasta 15; 20 s → 15. |

La decisión 3 hace explícito el alcance público del guardado inmediato previamente acordado. La decisión 6 cierra el detalle decimal que quedó señalado en el checkpoint. La decisión 4 distingue registros históricos migrados de nuevos reportes recibidos después del cambio de versión.

## 3. Reglas comunes del diccionario

- Los identificadores internos son UUID; el panel puede mostrar códigos cortos como R-000123. Un teléfono o @WhatsApp es un contacto privado, no un ID público.
- Un valor desconocido se guarda como NULL. Cero, falso, lista vacía y dato desconocido no son equivalentes.
- Fechas del sistema: instantes con zona horaria, guardados en UTC y mostrados en America/Bogota. Las fechas del chat conservan su literal y el valor local interpretado; si se asume zona Colombia, se registra como supuesto de importación.
- Los originales no se reemplazan por resúmenes ni correcciones. Las citas se vinculan a su mensaje; los marcadores de adjuntos se excluyen únicamente de la cita presentada.
- Un reporte puede tener varios mensajes y evidencias. Una evidencia puede apoyar varios reportes; esa asociación debe ser explícita. Un fotograma no genera un reporte adicional por sí mismo.
- Datos extraídos del chat, transcritos del audio, interpretados por modelos y corregidos por personas conservan procedencia diferenciada.
- Los campos públicos son una proyección de los datos privados. Si una cita necesita ocultar datos personales, se guarda una copia pública depurada y se conserva íntegra la cita fuente privada.
- Los estados y relaciones propuestos abajo no constituyen todavía una migración SQL ejecutada.

## 4. Ciudadanos, conversaciones y cargas

### Ciudadano/contacto — acceso privado

| Variable | Tipo | Regla |
|---|---|---|
| id_ciudadano | UUID | Identificador interno independiente del teléfono. |
| nombre_visible | Texto, admite NULL | Como aparece en la fuente. Un nombre igual no basta para fusionar personas. |
| contacto_original | Texto, admite NULL | Número o @WhatsApp original. |
| contacto_normalizado | Texto, admite NULL | Solo cuando se pueda normalizar sin inventar un número o identidad. |
| tipo_contacto | Categoría | telefono, arroba, otro, desconocido. |

Los contactos distintos no equivalen necesariamente a personas físicas distintas. Una misma persona puede usar dos números. El indicador lo explicitará.

### Conversación

| Variable | Tipo | Regla |
|---|---|---|
| id_conversacion | UUID | Se mantiene entre exportaciones confirmadas de la misma conversación. |
| nombre_original | Texto | Nombre de conversación/carpeta recibido. |
| id_ciudadano_principal | UUID, admite NULL | No asignar un único ciudadano a toda una conversación grupal. |
| resumen_conversacion | Texto, admite NULL | Resumen breve interpretado; enlazado a la ejecución que lo produjo. |
| ejecucion_resumen_id | UUID, admite NULL | Procedencia del resumen y su versión. |

### Carga / versión de ZIP

| Variable | Tipo | Regla |
|---|---|---|
| id_carga | UUID | Identifica cada carga recibida, incluso si resulta duplicada. |
| id_conversacion | UUID, admite NULL mientras se resuelve | Conversación vinculada. |
| nombre_zip_original | Texto | Conserva nombre y sufijo del archivo. |
| nombre_carpeta_original | Texto | Mantenerlo bajo un ID interno para evitar colisiones. |
| sha256_zip | Texto | Huella exacta de los bytes recibidos. |
| huella_contenido | Texto, admite NULL hasta inventariar | Compara rutas internas y huellas de archivos; no depende de la compresión o fecha del ZIP. |
| tamano_bytes | Entero | Tamaño del ZIP. |
| fecha_carga | Fecha/hora con zona | Recepción en VPS, no fecha del reporte. |
| ruta_storage | Texto privado | Localizador interno del ZIP conservado. |
| relacion_version | Categoría | nueva, contenido_identico, ampliacion, contenido_parcial, cambio_de_medios, por_revisar. |
| carga_relacionada_id | UUID, admite NULL | Carga con la que se comparó. |
| estado_carga | Categoría | recibida, inventariando, lista, duplicada, error. |

Los mensajes y evidencias reutilizados mantienen vínculos a cada carga donde aparecieron. Detectar una ampliación no significa sobrescribir o eliminar la versión anterior. Si una exportación contiene menos mensajes, no se interpretan sus ausencias como órdenes de borrado.

## 5. Mensajes y evidencias

### Mensaje

| Variable | Tipo | Regla |
|---|---|---|
| id_mensaje | UUID | Identidad estable dentro de la conversación, con coincidencias revisables entre exportaciones. |
| id_conversacion | UUID | Origen conversacional. |
| id_remitente | UUID, admite NULL | Vinculación al contacto, cuando sea identificable. |
| remitente_literal | Texto privado | Valor visible en chat.txt. |
| fecha_mensaje_literal | Texto | Conserva lo exportado. |
| fecha_mensaje_local | Fecha/hora local, admite NULL | Resultado del parser; no sustituir por fecha de carga si falla. |
| zona_horaria_origen | Texto, admite NULL | Zona conocida o asumida según procedencia registrada. |
| zona_horaria_asumida | Booleano | Distingue configuración del importador de información explícita. |
| texto_original | Texto | Mensaje completo, sin resumir. |
| cita_limpia | Texto | Presentación sin etiquetas de adjuntos; conserva las palabras del mensaje. |
| referencias_origen | Lista de referencias | Archivo, carga, líneas/rango y orden donde se encontró. |

No deduplicar únicamente porque dos mensajes tengan el mismo texto: la persona puede haberlo repetido en momentos distintos. Las coincidencias ambiguas se conservan para revisión.

### Evidencia y derivados

| Variable | Tipo | Regla |
|---|---|---|
| id_evidencia | UUID | Identificador estable del archivo. |
| modalidad | Categoría | chat, imagen, audio, video, ubicacion, fotograma, imagen_anotada, otro. |
| es_derivado | Booleano | Distingue original de salida de procesamiento. |
| evidencia_padre_id | UUID, admite NULL | Video del que salió audio/cuadro o imagen de la que salió copia anotada. |
| nombre_original / ruta_original | Texto | Nombres recibidos dentro de la carpeta, preservados como metadata. |
| ruta_storage | Texto privado | Ubicación efectiva y controlada del archivo. |
| url_evidencia | URL resuelta por la aplicación | Enlace estable con control de acceso; no URL pública del volumen. |
| sha256 | Texto | Integridad e identificación de contenido. |
| mime_type / tamano_bytes | Texto / entero | Tipo y tamaño. |
| disponibilidad | Categoría | original, derivado, solo_miniatura, ausente, pendiente_recuperacion. |
| duracion_segundos | Número, admite NULL | Audio/video. |
| ancho_px / alto_px | Enteros, admiten NULL | Imágenes/cuadros utilizados. |
| tiempo_relativo_segundos | Número, admite NULL | Instante del cuadro en el video; nunca fecha calendario inventada. |
| indice_frame / pts_original | Entero / número, admiten NULL | Trazabilidad del cuadro decodificado. |
| intervalo_segundo / regla_muestreo | Entero / categoría, admiten NULL | primeros_10_ultimo o ultimos_5_primero. |
| ejecucion_derivacion_id | UUID, admite NULL | Qué procesamiento generó el archivo. |

Relaciones auxiliares: carga–evidencia, mensaje–evidencia y reporte–evidencia. La proximidad entre mensajes no se tomará como prueba suficiente para asignar una foto a un cruce diferente cuando exista ambigüedad.

## 6. Reportes y afirmaciones por fuente

### Reporte

| Variable | Tipo | Regla |
|---|---|---|
| id_reporte / codigo_reporte | UUID / texto | Identidad y código legible. |
| id_conversacion | UUID | Conversación que lo originó. |
| mensaje_reporte_id | UUID, admite NULL | Mensaje principal que comunica el hecho. |
| fecha_reporte | Fecha/hora local, admite NULL | La del mensaje principal; en audio/video, la de su mensaje de WhatsApp si está identificado. |
| fecha_ultimo_mensaje_asociado | Fecha/hora local, admite NULL | Intervalo de mensajes que complementan el reporte. No es duración del daño. |
| observacion_fecha_literal | Texto, admite NULL | Fecha/momento dicho por el ciudadano, si existe. |
| id_cruce | UUID, admite NULL | Cruce vinculado; no forzar si es ambiguo. |
| id_incidente | UUID, admite NULL | Agrupación de hechos confirmada durante revisión, opcional en esta etapa. |
| descripcion_sintetica | Texto, admite NULL | Síntesis respaldada por fuentes; no reemplaza el relato. |
| categoria_falla_reportada | Lista de categorías | apagado_reportado, falla_parcial_reportada, intermitencia_reportada, descoordinacion_reportada, luces_conflictivas_reportadas, otra, no_precisada. No implica diagnóstico técnico. |
| revision_humana | Categoría | pendiente, revisado, descartado. Revisado significa cotejado con las fuentes, no inspección física del semáforo. |
| estado_procesamiento | Categoría | en_cola, procesando, completado, parcial_con_errores, error. |
| motivos_revision | Lista de categorías | ubicacion_ambigua, evidencia_sin_asociar, posible_duplicado, fuentes_discrepantes, transcripcion_incierta, imagen_no_evaluable, otro. |
| fecha_creacion / fecha_actualizacion | Fechas/hora con zona | Momentos del sistema. |
| version_reporte | Entero | Cambia al incorporar o corregir información; historial preservado. |

La vinculación de ciudadanos al reporte se obtiene de sus mensajes, no de un nombre inventado por el modelo. Los reportes extraídos repetidamente de fragmentos superpuestos deben consolidarse antes de incorporarse a los conteos.

### Afirmaciones: conservación de varias versiones de lo dicho

Para evitar ocho columnas rígidas que pierdan información si dos mensajes discrepan, cada afirmación se guarda con su fuente. El panel presenta las ocho variables pedidas por Esteban como vistas de estas afirmaciones.

| Variable interna | Tipo | Regla |
|---|---|---|
| id_afirmacion / id_reporte | UUID | Identidad y reporte relacionado. |
| variable | Categoría | ubicacion, descripcion_dano, tiempo_sin_funcionar, afectaciones. |
| origen | Categoría | chat, audio_whatsapp, audio_video. |
| valor_literal | Texto | Fragmento exacto del chat o de la transcripción automática identificada. |
| valor_interpretado | Texto, admite NULL | Normalización/síntesis identificada como interpretación; no obligatoria para duración. |
| mensaje_id / transcripcion_id | Referencias | Al menos la fuente aplicable debe existir. |
| inicio_fin_fuente | Rangos, admiten NULL | Posición textual o tiempos del audio cuando existan. |
| ejecucion_id | UUID | Modelo/prompt que extrajo la afirmación. |

### Las ocho variables visibles solicitadas

| Variable en tabla/API | Fuente | Presentación |
|---|---|---|
| ubicacion_semaforo_texto | Chat | Literal(es) de ubicación. |
| descripcion_dano_texto | Chat | Descripción(es) del ciudadano. |
| tiempo_sin_funcionar_texto | Chat | Expresión(es) literal(es), sin duración continua calculada. |
| afectaciones_ciudadanos_texto | Chat | Relato(s) de afectación. |
| ubicacion_semaforo_audio | Transcripciones | Literal(es), distinguiendo nota de voz y audio de video. |
| descripcion_dano_audio | Transcripciones | Descripción(es) transcrita(s). |
| tiempo_sin_funcionar_audio | Transcripciones | Expresión(es) transcrita(s). |
| afectaciones_ciudadanos_audio | Transcripciones | Relato(s) transcrito(s). |

En la API, cada variable será una lista de valores con referencias; una lista vacía significa que no se extrajo una afirmación. El estado de la etapa indica si se buscó y no apareció o si aún falta procesar. En la tabla, se muestran los valores y un acceso al detalle. No seleccionar silenciosamente una sola afirmación cuando haya varias incompatibles.

## 7. Audio e imagen

### Transcripción

| Variable | Tipo | Regla |
|---|---|---|
| id_transcripcion / id_evidencia / ejecucion_id | UUID | Relación entrada–salida–modelo. |
| texto_transcrito_modelo | Texto | Salida completa inicial; puede contener errores. |
| segmentos | JSON | Texto y tiempos cuando los produzca el modelo. |
| idioma_detectado | Texto, admite NULL | Dato del modelo, no identidad del hablante. |
| salida_original_modelo | JSON/texto | Resultado original para reproducibilidad. |

La corrección humana se guarda como etiqueta/revisión separada. No se incluye inferencia emocional ni identificación de hablantes por voz en esta entrega.

### Detección y luces por objeto

| Variable | Tipo | Regla |
|---|---|---|
| id_deteccion / id_evidencia / ejecucion_id | UUID | Una fila por semáforo detectado. |
| bbox_xyxy | Cuatro enteros | xmin, ymin, xmax, ymax en píxeles de la imagen analizada, con dimensiones registradas. |
| puntuacion_deteccion | Número, admite NULL | Salida del detector; no llamarla probabilidad calibrada sin evaluación. |
| luz_roja / luz_amarilla / luz_verde | Booleanos, admiten NULL | true visible encendida; false evaluada y no visible encendida; NULL no determinable. |
| estado_lectura_luces | Categoría | alguna_visible, ninguna_visible, indeterminado. |
| motivo_indeterminado | Texto/categoría, admite NULL | Tamaño, desenfoque, obstrucción, exposición, cara no visible u otro. |
| evidencia_anotada_id | UUID, admite NULL | Copia con cajas; el original se conserva. |

El estado por imagen registra pendiente, procesada o error y cantidad de detecciones. Tras una inferencia válida con cero detecciones se muestra “no se detectó semáforo”; eso no prueba que no hubiera uno.

“Ninguna visible” exige que las tres luces se hayan podido evaluar y estén en false. Si alguna está en true, el objeto tiene alguna luz visible aunque otra sea NULL. Si no hay true y falta evaluar alguna, queda indeterminado.

Una fotografía con varias cajas conserva resultados separados. No mezclar luces de semáforos distintos ni decidir que todo un cruce funciona porque una luz aparece encendida. Las observaciones de video conservan sus instantes: no demuestran el estado entre cuadros ni permiten estimar ciclos completos.

## 8. Cruce, coordenadas y mapa

| Variable | Tipo | Regla |
|---|---|---|
| id_cruce | UUID | Identidad del cruce una vez resuelto. |
| interseccion_normalizada | Texto | Nombre interpretado/revisado. Los textos originales siguen en afirmaciones. |
| latitud / longitud | Números, admiten NULL | Coordenadas geográficas WGS84, con validación de rango. |
| origen_coordenadas | Categoría | ubicacion_whatsapp, catalogo, geocodificador, ajuste_humano, desconocido. |
| estado_ubicacion | Categoría | sin_ubicacion, candidata, reportada, validada, por_corregir. |
| dentro_perimetro_urbano | Booleano, admite NULL | Resultado frente al perímetro cuya fuente y versión se registran. |
| fuente_geografica_version | Texto, admite NULL | Catálogo/perímetro utilizado. |
| fecha_validacion / revisor_id | Fecha/hora / referencia, admiten NULL | Revisión de la ubicación. |

Se proponen pines públicos para coordenadas explícitamente asociadas al cruce por la fuente o validadas por una persona. Un candidato inferido de una dirección queda en el panel privado hasta validación; el reporte sigue disponible en la tabla. Puntos fuera del perímetro se conservan y señalan para revisión. La posición GPS de una cámara, por sí sola, no se toma como ubicación exacta del semáforo.

## 9. Seis indicadores sintéticos propuestos

Se calculan desde las fuentes canónicas; no se guardan copias manuales que puedan quedar desactualizadas. Los indicadores por cruce dependen de que los reportes estén asociados a ese cruce y consolidados sin duplicados.

| Variable | Cálculo y utilidad |
|---|---|
| cantidad_reportes_cruce | Reportes distintos vigentes del cruce. Excluye descartados, duplicados y multiplicación por fotogramas. |
| cantidad_contactos_distintos_cruce | IDs de contacto distintos identificados en esos reportes. No asegura personas físicas distintas. No expone sus teléfonos. |
| fecha_ultimo_reporte_cruce | Máxima fecha válida del mensaje de reporte. No usar última carga ni última ejecución. |
| modalidades_evidencia | Modalidades originales disponibles y derivadas, identificadas por separado. Muestra si hay solo relato o material adicional. |
| afectaciones_categorizadas | Lista sugerida a partir de afirmaciones: congestion, riesgo_vial, casi_siniestro, siniestro_relatado, dificultad_peatonal, demora_declarada, otra. Cada categoría conserva su cita de respaldo. |
| discrepancias_entre_fuentes | Lista de conflictos candidatos sobre ubicación, descripción o tiempo, con referencias. Distintos instantes de video no son automáticamente contradicción. |

No se propone un puntaje opaco de “peor semáforo”, severidad inventada ni días continuos de daño. Los seis indicadores son parte de esta propuesta y quedan aprobados con el diccionario.

## 10. Ejecución, evaluación y revisión humana

### Ejecución de procesamiento

Campos: id_ejecucion (UUID), etapa (inventario/video/audio/texto/imagen/ubicacion/consolidacion), entradas_ids (lista), huellas_entradas (JSON), version_codigo, imagen_contenedor, modelo_identificador, modelo_revision_o_digest, version_prompt, configuracion (JSON), inicio, fin, duracion_segundos, estado, numero_intento, error_codigo, error_detalle_depurado, salida_original_uri, cpu_segundos y memoria_pico_bytes cuando sea medible.

El significado y alcance de cada métrica de recursos se registra: proceso, contenedor o servidor. No atribuir el consumo de todo el VPS a un modelo. Los logs no contienen contraseñas ni chats completos por defecto. Cada resultado enlaza a la ejecución que lo produjo.

### Etiquetado y revisión

Campos: id_revision, entidad_tipo, entidad_id, version_prediccion, campo, prediccion_referenciada, etiqueta_humana, comentario, revisor_id y fecha_revision. Se conserva la predicción original. Una modificación posterior de los datos relacionados requiere revisar las etiquetas afectadas, sin borrar el trabajo previo.

### Evaluación

Campos: id_evaluacion, version_conjunto_etiquetado, seleccion_de_casos, etapa_modelo, version_modelo_prompt_codigo, metricas (JSON), cantidad_casos_evaluados y fecha_evaluacion.

Métricas previstas: WER y errores de direcciones para audio; aciertos, omisiones y afirmaciones sin respaldo para texto; precisión/recall con criterio IoU explícito para cajas; desempeño por luz y estados no evaluables; acierto de cruce para ubicación. Registrar también cobertura: cuántos casos quedaron indeterminados. Hasta disponer de etiquetas suficientes, las métricas de calidad quedan sin calcular, no en cero.

Los 36 ZIP son exploratorios. Se separarán conversaciones nuevas para evaluación, revisando duplicados y material del mismo evento. Los fotogramas de un video no se repartirán artificialmente entre ajuste y evaluación.

## 11. Correo, PDF y control de acceso

### Notificación

Campos: id_notificacion, id_reporte, version_reporte_notificada, evento (reporte_nuevo), destinatario_configurado, estado (pendiente/enviando/enviada/error/entrega_incierta), intentos, fecha_programada, fecha_envio, referencia_proveedor y ultimo_error_depurado. La combinación reporte+evento identifica la notificación automática inicial.

La salida se registra de manera persistente después de guardar el reporte. Un fallo del correo no obliga a repetir la inferencia. Si el proveedor acepta el mensaje y se pierde la confirmación, se señala entrega incierta para evitar un reenvío ciego; la aplicación no promete entrega exactamente una vez con cualquier servidor de correo.

La notificación incluye todos los campos del registro disponibles en ese corte y enlaces privados pertinentes. Si se agotaron reintentos de una modalidad, comunica el estado parcial. No adjunta medios. En la propuesta, las actualizaciones posteriores no generan otro correo automático; un reenvío manual podrá ser una acción explícita.

### Informe general

Campos: id_informe, fecha_generacion, fecha_corte, version_consulta, versiones_registros_incluidos, cantidad_reportes, criterios_inclusion, captura_mapa_id, ruta_pdf y log_generacion. Una vez generado, el archivo conserva su contenido; una nueva descarga genera otro corte identificado.

Contenido: fecha del mensaje, intersección interpretada, descripción, estado de revisión/procesamiento, cantidad de reportes por cruce, enlaces autorizados a evidencias, captura del mapa del mismo corte y logo personal. No firma digital ni documento jurídico redactado automáticamente.

### Visibilidad propuesta

| Información | Pública | Equipo / juez autorizado |
|---|---|---|
| ID reporte, fecha, cruce, descripción publicable, indicadores y estados | Sí | Sí |
| Cita depurada o resumen publicable | Sí, si no contiene datos personales | Sí |
| Chat íntegro, teléfono/@, archivos originales | No | Según autorización |
| Copias visuales | Solo si existe una copia depurada apta para publicar; no exponer originales automáticamente | Sí |
| Logs técnicos completos, configuración y etiquetas de trabajo | No | Equipo; extractos pertinentes según autorización |

Esta visibilidad es parte de la decisión 3. No agrega nuevamente una columna “permiso de publicación”; se implementa mediante vistas y permisos del sistema.

## 12. Reglas operativas para la entrega integrada

1. Inspeccionar la versión de Easypanel, conectividad y recursos libres antes de elegir el mecanismo exacto de despliegue. Paquete único, configuración inicial única y dependencias automatizadas.
2. Reutilizar n8n/Ollama propios si son compatibles; aislar la base y servicios de Semáforos de otros proyectos. No modificar bases ajenas.
3. Respaldar el lote actual y probar una importación que mantenga origen, resultados y conteos. La migración no acredita mejora de calidad ni autoriza borrar originales.
4. Cola persistente, un trabajo pesado de IA a la vez y carga/descarga controlada de modelos. n8n coordina; Python procesa; una fuente canónica mantiene estados para no tener dos colas contradictorias.
5. El panel muestra etapas por reporte y archivo. Un error de audio no impide conservar texto y fotografías procesadas.
6. Reutilizar una salida solamente cuando sean compatibles la entrada y las versiones relevantes de modelo, prompt y procesamiento. Incorporar contexto al analizar mensajes nuevos de una exportación ampliada.
7. Mostrar espacio disponible y consumo. Límites de carga/video y margen de disco se fijan tras medir; un archivo que exceda un límite se señala, nunca se recorta silenciosamente.
8. Descargar modelos con versiones registradas y comprobar su carga. La selección concreta del modelo de luces requiere validar que produzca las salidas acordadas; instalar un detector general no basta para dar esa función por terminada.
9. Guardar credenciales en configuración privada. El correo necesita proveedor y credenciales aún pendientes; el dominio definitivo se integra después. Las credenciales no se solicitan en un documento descargable.
10. Código y pruebas del paquete se preparan antes de pedir una única instalación al usuario. Quedan necesarias pruebas integradas en el VPS y evaluación humana de las predicciones.

## 13. Aprobación y verificaciones pendientes

**Aprobación recibida:** seis decisiones, diccionario e indicadores aprobados. Requisito adicional: arquitectura fácil de modificar, resultados de pruebas comparables, documentación paralela y repositorio estebanoli8/semaforosCALI.

**Verificación técnica posterior:** versión real y soporte de despliegue de Easypanel; instalación efectiva de v0.3; persistencia y rutas del lote; recursos disponibles; identidad/digest del modelo textual; proveedor de correo; datos cartográficos disponibles; acceso a logo original.

Estas verificaciones no necesitan convertirse en una serie de instalaciones manuales del usuario. La implementación integrada debe reunirlas en un diagnóstico inicial y una configuración breve.

El desarrollo procede con estas reglas. Los cambios futuros se registran con versión y decisión; las verificaciones técnicas pendientes no reabren lo aprobado.
