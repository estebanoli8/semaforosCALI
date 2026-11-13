# Seguimiento del procesamiento privado

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

Si falla la extracción de texto o la lectura de luces, el panel ofrece
**Reintentar modelo** para una ejecución adicional con la configuración de esa
tarea. Conserva los intentos anteriores y solo permite reintentar una tarea
ya fallida, hasta cinco intentos en total. Los códigos de error conocidos de validación se muestran
sin incluir el texto ciudadano; los mensajes arbitrarios del modelo y de las
librerías siguen ocultos. Un nuevo intento no garantiza una salida válida.

En los nuevos trabajos de lectura de luces el modelo visual permanece cargado
dos minutos entre solicitudes (`keep_alive`); el de texto continúa descargándose
después de cada petición para limitar la RAM simultánea. La configuración de
cada trabajo se fija al crearlo, por lo que esta mejora no modifica trabajos
ya encolados. Comparar `load_duration` y `wall_seconds` entre trabajos nuevos y
anteriores antes de atribuirle una ganancia. La evidencia original no se escala
ni se recomprime; la detección redimensiona internamente a 960 píxeles y la
lectura de luces usa un recorte de hasta 640 píxeles. Los fotogramas derivados
ya tienen un límite de 1280 píxeles y el audio de video usa mono de 16 kHz.

Antes de cambiar recursos en Easypanel, medir CPU/RAM del host y de los dos
contenedores bajo carga (`docker stats --no-stream`), y revisar `wall_seconds`,
`cpu_seconds`, `peak_rss_bytes` y tiempos de Ollama en la salida de una tarea.
Con 6 núcleos y 12 GB compartidos con otras aplicaciones, subir todos los
límites sin medir puede degradar servicios ajenos. Un aumento de CPU del núcleo
solo ayuda a las etapas locales que pueden usar esos hilos; Ollama consume CPU
en su propio servicio. Cambiar límites en Easypanel requiere desplegar y
reinicia el servicio; esperar a que termine la tarea actual y comprobar después
el estado del trabajador, los volúmenes y la cola.
