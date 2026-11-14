# Seguimiento del procesamiento privado

## Prueba controlada después de detener el lote

Desplegar con `SC_PROCESS=api` mantiene el panel disponible sin iniciar el
trabajador automático. Con Ollama activo, ejecutar desde el contenedor core:

```bash
python -m semaforos.trial --stage text
```

Cada comando selecciona la entrada más pequeña de esa etapa que ya falló y
crea un trabajo en un experimento nuevo con la configuración actual y un solo
intento. El bloqueo global evita inferencias simultáneas; la selección por ID
evita consumir tareas del lote anterior. Las salidas quedan en el panel. El
comando devuelve código distinto de cero si falla: revisar ese resultado antes
de continuar. La indexación de hallazgos y la cola completa se reanudan cuando
se vuelve a desplegar con `SC_PROCESS=all`.

El panel de `semaforos-core` muestra el avance total de **tareas conocidas**.
Un video crea nuevas tareas cuando termina la extracción de sus fotogramas y
audio, por lo que el porcentaje puede disminuir sin perder trabajo. Cuenta las
tareas terminadas, incluso las fallidas, y muestra aparte los errores. No se
confunde con el número de conversaciones ni de reportes revisados.

Cada fila identifica la conversación original y el archivo; para fotogramas,
también el video de origen y el segundo. Las barras de una tarea en ejecución
son indeterminadas si la herramienta no informa avance medible. Whisper puede
dar segundos transcritos; Qwen expone texto provisional a medida que responde.
Ese texto es un borrador privado, sujeto a validación de formato y origen al
finalizar. Una respuesta parcial nunca se registra como predicción terminada.

Las imágenes anotadas se consultan mediante la API privada con el token de la
sesión en memoria. El navegador libera cada copia al cerrar o cambiar de
tarea. Los archivos originales, las salidas y los reintentos permanecen en
`/data/core`; el panel no cambia su contenido.

Si falla la extracción de texto o la transcripción, el panel ofrece
**Reintentar modelo** para una ejecución adicional con la configuración de esa
tarea. Conserva los intentos anteriores y solo permite reintentar una tarea
ya fallida, hasta cinco intentos en total. Los códigos de error conocidos de validación se muestran
sin incluir el texto ciudadano; los mensajes arbitrarios del modelo y de las
librerías siguen ocultos. Un nuevo intento no garantiza una salida válida.

Antes de cambiar recursos en Easypanel, medir CPU/RAM del host y de los dos
contenedores bajo carga (`docker stats --no-stream`), y revisar `wall_seconds`,
`cpu_seconds`, `peak_rss_bytes` y tiempos de Ollama en la salida de una tarea.
Con 6 núcleos y 12 GB compartidos con otras aplicaciones, subir todos los
límites sin medir puede degradar servicios ajenos. Un aumento de CPU del núcleo
solo ayuda a las etapas locales que pueden usar esos hilos; Ollama consume CPU
en su propio servicio. Cambiar límites en Easypanel requiere desplegar y
reinicia el servicio; esperar a que termine la tarea actual y comprobar después
el estado del trabajador, los volúmenes y la cola.
