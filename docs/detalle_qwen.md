# Detalle de reporte, evaluación y Qwen

## Alcance y señales

La vista privada `/reportes` reúne las conversaciones bajo la identidad que aparece en el chat. Vincula exportaciones si comparten un teléfono inequívoco. La fecha abarca el primer y último mensaje ciudadano con hora reconocida, incluidos adjuntos. En un chat grupal se muestran los remitentes identificados. Cuando no se puede atribuir un remitente se conserva el nombre del archivo. Los originales y las transcripciones completas se consultan en Evidencia.

La descripción se compone con afirmaciones de Qwen y referencias locales de fuentes ya procesadas. Se comprueba que cada frase se encuentre literalmente en la fuente. La interfaz distingue el tipo de falla, **desde cuándo lleva dañado** y la reincidencia tras reparación. Gestión registra guarda o agente, incluida la ausencia explícita. Peligro registra accidentes o riesgos y a quiénes afectan cuando se menciona. Las ubicaciones aproximadas se conservan como tales, y una ubicación sola marca el daño como inferido. Cuando termina el barrido, cada parte faltante se muestra como **No detectado**. Mientras hay fuentes en procesamiento, los campos faltantes aparecen pendientes y la inferencia de daño por ubicación sola espera al cierre. La fecha que acompaña la duración corresponde al mensaje que la declara, sin convertir el intervalo de la conversación en tiempo de falla.

El PDF incluye todas las conversaciones del corte, los campos desplegados, fecha de generación, logo, título y subtítulo en cada página. Los archivos tienen enlaces firmados individuales válidos siete días. Quien reciba uno de esos enlaces puede abrir la evidencia concreta hasta que venza.

En cada foto o fotograma, YOLO se evalúa con conteos. En audios y audio de video, la evaluación de Whisper compara lo escuchado con la transcripción. En cada salida de Qwen se compara lo observado en el fragmento y lo detectado. Los cuatro campos tienen casillas Observado y Detectado. Guardar confirma la evaluación de los campos, incluidas ausencias explícitamente revisadas. El tablero usa la última evaluación guardada por ejecución, informa el conteo exacto para YOLO y promedia el F1 de campos con positivos observados o detectados para Whisper y Qwen. Estas medidas complementan WER y las métricas de detección por caja. La coincidencia de conteo mide cantidades. El F1 de campos mide detección de presencia; la revisión de la cita permite cotejar su contenido.

## Inferencia compacta

`compact-v1` elimina avisos reconocidos, cabeceras y marcadores técnicos del prompt conservando los tramos y sus posiciones originales. En una solicitud puede empacar más de un episodio y marca cambios de remitente o distancia temporal superior a 30 minutos. Qwen recibe referencias cortas a frases y el subconjunto pertinente del [catálogo de Cali](../semaforos/assets/referentes-cali-v0.1.csv). Una ubicación de otro episodio de la misma solicitud no se usa como ancla. El adaptador recupera las citas desde los tramos y conserva métricas por llamada, también cuando Ollama termina con truncamiento. El texto de chat solicita seis hilos a Ollama. La inferencia de transcripciones conserva cuatro hilos. La cuota efectiva la define el contenedor Ollama.

El **15 de noviembre de 2026**, el análisis local de **22 TXT únicos** produjo 20 lotes compactos frente a 25 históricos, y 4.977 frente a 19.207 caracteres de cuerpo enviado. Esta comparación excluye prompt fijo, esquema y etiquetas y mide agrupación antes de llamar al modelo. El tiempo de inferencia, tokens reales y exactitud solo se establecen con el piloto en el VPS.

## Preparar la tanda pendiente en Easypanel

1. Despliega `semaforos-core` con `SC_PROCESS=api` y pausa el worker aparte, si lo tienes separado. El arranque aplica la migración de PostgreSQL. Con el host HTTPS disponible, confirma que **Detalle de reporte** abra y que el PDF genere sus enlaces desde el dominio correcto. Si la aplicación recibe HTTP desde el proxy, configura `SC_REPORT_ORIGIN` con el origen público HTTPS.
2. En la terminal del contenedor, ejecuta:

   ```bash
   /usr/local/bin/python -m semaforos.optimize_queue
   ```

   Distingue conversaciones ya importadas, trabajos antiguos pendientes y cargas ZIP pendientes de importar. Un reporte ciudadano puede originar varias tareas. El comando apunta a la cola antigua pendiente. Revisa que corresponda a la tanda esperada. Si necesitas preparar solo una conversación importada, usa `--conversation UUID`.

3. Aplica la preparación con los workers en pausa. Si se interrumpió un trabajo de la versión anterior, espera que expire su arrendamiento de hasta 90 segundos para que aparezca en la estimación.

   ```bash
   /usr/local/bin/python -m semaforos.optimize_queue --apply
   ```

   El comando crea lotes `detalle-qwen-v3` y deja las tareas antiguas pendientes como sustituidas en la misma transacción. Los ZIP en transporte se actualizan para usar la configuración nueva al importarse. Los chats parcialmente procesados se empaquetan junto con el resto de su texto para aplicar el nuevo agrupador. Se conservan originales, transcripciones y ejecuciones anteriores. El comando es repetible con la misma configuración.

4. Restablece `SC_PROCESS=all` o levanta el worker separado. En **Desempeño de modelos**, filtra `detalle-qwen-v3` y registra total de conversaciones procesadas, mediana y p90 del tiempo acumulado de las llamadas, tokens y truncamientos. Para comparar velocidad, coteja la misma evidencia en ambos perfiles, con el mismo modelo y cuota de Ollama. Revisa manualmente duración de la falla, reparaciones seguidas de recaídas, negaciones de gestión y cruces ambiguos. Los indicadores del panel no incluyen tiempo de espera de la cola.

Tras cotejar el piloto, se puede estimar un reproceso histórico de texto con `/usr/local/bin/python -m semaforos.optimize_queue --historico`. Agrega `--apply` con los workers pausados para encolar `detalle-qwen-v3-historico`. Reutiliza transcripciones, incluidas correcciones guardadas. Las tareas de imágenes y video se generan durante la carga normal.

## Demostrar la alerta MLOps

Sube una conversación sintética de WhatsApp con una cabecera compatible y la otra con un separador de fecha/hora cambiado. Ejemplo compatible `[15/11/26, 10:00] Ciudadana: Calle 16 con Carrera 80.`. Ejemplo de cambio `15/11/26 10.05 | Ciudadana | El semáforo sigue dañado.`.

En **Desempeño de modelos**, abre **Alertas del formato de WhatsApp**. Una cabecera probable desconocida o una variante de separador de remitente o adjunto produce aviso. El estado pasa a degradado si el TXT con contenido carece de cabeceras reconocidas, o si la fracción de cabeceras probables no interpretables supera el 10 %. Las líneas de continuación no cuentan como cabeceras. Una línea que parece cabecera y usa un formato desconocido se separa sin atribuirla al remitente anterior. Se guarda el archivo, el conteo y la versión del parser para reproducir el caso. El monitor detecta cambios estructurales observables. Un cambio semántico con la misma estructura requiere evaluación humana.

## Piloto en el VPS

Corte del operador del 15 de noviembre de 2026, después del Deploy. El comando de preparación encontró 33 conversaciones importadas con 36 tareas pendientes. Creó 19 lotes de chat y reencoló 17 tareas de otras etapas o fuentes. Tres cargas ZIP en trámite también recibieron la configuración nueva. Una carga todavía en recepción requiere completar la subida antes de entrar a la importación.

| Etapa | Completadas | En ejecución | Pendientes |
| --- | ---: | ---: | ---: |
| Audio | 1 | 0 | 3 |
| Detección de semáforos | 11 | 1 | 34 |
| Extracción de texto | 0 | 1 | 37 |
| Preparación de video | 3 | 0 | 0 |
| Total del corte | 15 | 2 | 74 |

El contenedor informó `SC_PROCESS=all` y dos trabajadores. Un ZIP figuraba importado y dos en recepción. Los derivados de la preparación multimedia explican que el número de tareas conocidas aumente durante una tanda. La tabla es una fotografía del arranque. El corte final, la cobertura de los cuatro campos y los tiempos de Qwen siguen pendientes de verificación en el VPS.

Para comprobar la función en producción, cotejar en **Detalle de reporte** conversaciones del piloto con referencias de cada campo. Distinguir análisis pendiente, parcial y terminado. Un campo ausente al terminar figura como **No detectado**. La cantidad de conversaciones con un valor mide cobertura. La validación del contenido requiere revisar el original; también cuenta si se omitió un valor que sí aparecía en la fuente. Una ubicación sola puede originar una inferencia de daño que se identifica como tal.

La comprobación técnica de `compact-v1` usa la identidad guardada en los runs completados. El valor de hilos es el solicitado al modelo. En **Desempeño de modelos** filtrar `detalle-qwen-v3`. Reportar el denominador al lado de los tiempos. [Consulta agregada](observabilidad.md#corte-agregado-del-piloto) y [protocolo de comparación](experimentos.md#comparación-de-qwen-en-el-vps).
