# Semáforos Cali v0.3

Actualización compatible con el lote de texto v0.2. Esta entrega prepara videos para los modelos; todavía no ejecuta transcripción, detección de semáforos, clasificación de luces, mapa, correo ni la base PostgreSQL propuesta. Mantiene el procesador Qwen de texto existente.

## Funciones de esta entrega

- Audio del primer stream disponible, WAV mono a 16 kHz, con relación al video y mensajes fuente.
- Hasta quince fotogramas JPEG por video. Conserva video original, instantes exactos, índices de fotograma, regla, huellas y versión de FFmpeg.
- Diez primeros intervalos de un segundo: último fotograma existente de cada intervalo. Cinco últimos intervalos: primero, salvo intervalos ya cubiertos por la regla inicial.
- Un intervalo final incompleto cuenta. 8 s produce 8 cuadros; 8,4 s produce 9; 12 s produce 12; 14 s produce 14; 20 s produce 15.
- Para 20 s: segundos 1 a 10 y 16 a 20. El tramo final toma instantes 15, 16, 17, 18 y 19 s si existen. No intenta leer en el instante final fuera del video.
- Si un intervalo no tiene fotogramas, no inventa uno. Máximo diez minutos por video en este prototipo. Un error de un archivo no impide preparar los demás de la conversación; conserva detalle y permite reintento.
- Procesamiento secuencial. Los trabajos de video tienen estados independientes del texto. La inferencia textual ya completada no se repite al preparar videos.
- Reutiliza derivados íntegros tras reinicio. Si falta o se altera un derivado, vuelve a prepararlo.
- Consulta de manifiestos y archivos derivados bajo la misma autenticación privada.
- El panel muestra espacio libre del disco compartido. No representa una cuota exclusiva del proyecto.

## ZIP y versiones

El contenido se compara por nombres internos y SHA-256 de cada archivo, ignorando fechas y método de compresión. Un ZIP idéntico por contenido se omite aunque se llame `(1)` o `(2)`. Un cambio en las rutas internas se conserva como otra entrada, aunque los bytes sean iguales.

Las conversaciones con el mismo nombre base se relacionan como candidatas. Se compara si el chat amplió sus mensajes, contiene menos mensajes, mantiene el mismo texto con otros medios o requiere revisión. El sufijo y las fechas no eligen una versión vigente. No se fusionan ni borran reportes automáticamente. Cada ZIP distinto conserva un directorio independiente. La carga de una versión modificada aún procesa su chat completo: la consolidación incremental de reportes entre versiones queda para la base de conocimiento y no debe interpretarse como implementada aquí.

## Actualizar el servicio existente

1. En Easypanel abre solamente `semaforos / procesador-semaforos`.
2. Pulsa **Pausar tras conversación actual** en la web del procesador y espera que no haya trabajo ejecutándose.
3. Confirma en **Storage** que el volumen existente `lote-datos` sigue montado en `/data`. Conserva ese volumen y las variables actuales. No borres ni vuelvas a crear el servicio.
4. Si existe la opción de backup del volumen, crea una copia local antes de desplegar. Las copias locales no protegen una pérdida total del VPS.
5. En **Source → Upload**, carga `Semaforos_Cali_Video_v0.3.zip` como código. Usa **Dockerfile**, contexto raíz y archivo `Dockerfile`.
6. Conserva `DATA_DIR`, `OLLAMA_URL`, `OLLAMA_MODEL` y `APP_PASSWORD`. No hacen falta credenciales nuevas. Una sola réplica.
7. Mantén inicialmente el límite actual del procesador de 0,5 CPU y 512 MB. FFmpeg usa un hilo. Si un video excede la capacidad, revisamos ese caso antes de aumentar recursos; no modifiques Ollama ni otros proyectos.
8. Save y Deploy únicamente en este servicio. El build descargará FFmpeg y puede tardar.
9. Reabre la interfaz: debe mostrar **v0.3**, las conversaciones previas y el espacio libre. `/health` debe incluir `ffmpeg: true` y el modelo existente.
10. Pulsa **Preparar videos de los ZIP recibidos**, luego **Iniciar / continuar lote**. La columna Texto debe conservar `texto_completado`; Video avanzará de `pendiente` a `procesando` y `derivados_listos`.
11. Abre el vínculo de Video de una conversación. El JSON contiene `url_archivo` para escuchar WAV o abrir fotogramas dentro del mismo dominio autenticado.
12. Puedes cerrar el navegador después de confirmar la cola activa. La pausa se aplica después del trabajo actual, no a mitad de un video.

El botón de preparación encola todos los ZIP recibidos y reintenta errores, pero no vuelve a preparar los completados. Tras nuevas cargas, vuelve a pulsarlo. Los ZIP sin videos terminan con una lista vacía, sin error.

## Almacenamiento

Se mantiene `/data/cola.sqlite`, `/data/<sha_zip>/original.zip` y los JSON de v0.2. Se agregan `contenido.json`, candidatas en `origen.json`, `videos.json`, `originales/<nombre ZIP sin extensión>/<ruta interna original>` y `derivados/<sha_video>/manifest.json`, WAV y JPEG.

La extracción añade una copia del video fuera del ZIP y archivos derivados. No se elimina el original. La descarga de resultados incluye manifiestos JSON, no los WAV/JPEG ni videos. Los derivados se consultan individualmente desde la interfaz privada.

## Pruebas y límites

Ejecuta `python -m unittest -v test_video`. Las pruebas verifican muestreo, extracción con FFmpeg, audio, videos silenciosos, offsets de tiempo, reparación de caché, duplicados por contenido, candidatas de versión y conservación de una base v0.2. Los videos de prueba generados no se incorporan a los datos ciudadanos.

La detección de luces, transcripción y extracción sobre el audio se conectarán después a estos derivados. El campo `analisis` permanece explícitamente como `pendiente_mlfoto` o `pendiente_mlaudio`. No se crean nuevos reportes a partir de cada fotograma.

No se probó Docker build ni el despliegue real de esta versión en el VPS desde el entorno de desarrollo. La validación del servidor debe hacerse primero con sus ZIP existentes. Las contraseñas y originales privados siguen protegidos por la autenticación del procesador y HTTPS del proxy.

Validación local adicional: seis videos distintos de los ZIP ciudadanos disponibles se decodificaron correctamente, con duraciones de 1,77 a 6,31 segundos. Se obtuvieron 26 fotogramas y seis pistas de audio. Estos derivados de validación no se incluyen en el paquete de código ni se enviaron a servicios externos.

## Reversión

Si el contenedor nuevo no arranca, vuelve a cargar el paquete v0.2 en Source y despliega manteniendo `/data`. La tabla nueva de video no altera las cinco columnas de `jobs`; v0.2 simplemente la ignora. Los archivos derivados permanecen en el volumen. No edites SQLite manualmente ni borres carpetas para hacer la reversión.
