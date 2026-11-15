# Reportes, mapa e informe general

## Flujo de validación

1. En **Procesamiento**, cargar un ZIP pequeño y dejar que termine. Abrir **Organizar reportes**, seleccionar las afirmaciones sobre un hecho y crear el reporte con su fuente principal. También se puede utilizar uno ya consolidado.
2. En **Reportes y mapa** (`/reportes`), usar la clave del equipo. Abrir el código del reporte, revisar la intersección y validar latitud y longitud WGS84 cuando exista evidencia suficiente. Los pares del relato se muestran como sugerencias. Un equipo puede usar el mismo nombre revisado de cruce para sumar sus reportes independientes.
3. La vista `/semaforos` presenta directamente el corte preliminar de conversaciones procesadas. Para mostrar la versión editada de un reporte, redactar una descripción depurada y activar **Mostrar la versión editada en la vista pública**. La versión editada reemplaza las fuentes equivalentes del corte automático. Descartar un reporte retira sus fuentes del corte automático. Un cambio de fuentes deja la ubicación editada pendiente de verificación.
4. Revisar **Métricas de modelos** (`/metricas`). Comprobar el experimento, los tiempos y los fallos. La calidad aparece al registrar referencias humanas utilizables.
5. Generar el PDF general. Comprobar sello de generación y corte en Colombia, logo, mapa, reportes por cruce y estados. Cada nueva generación guarda un archivo en `/data/core/informes` y una fila con identificador, versiones incluidas y huella SHA-256 en `semaforos.report_pdf_exports`.

**Enlaces de evidencia.** El equipo puede habilitarlos al generar un PDF. Cada enlace concede acceso temporal solo a un archivo de ese corte y vence en siete días. Compartir ese PDF equivale a compartir los archivos indicados durante ese plazo. Para crear enlaces, el origen debe ser HTTPS. Si Easypanel entrega un origen interno al contenedor, establecer `SC_REPORT_ORIGIN` con el dominio HTTPS de la app, sin ruta ni parámetros. Mantener la clave del equipo en el entorno privado. La consulta pública carece de enlaces y archivos originales.

## Resultados preliminares públicos

El corte se calcula en solo lectura desde la cola, los mensajes ya importados, transcripciones y hallazgos disponibles. Incluye conversaciones con tareas finalizadas, aun si quedan etapas pendientes o fallidas. Para formar las filas se agrupan fuentes por conversación, remitente y día del mensaje, y se muestran los cruces identificables por separado. Los temas sin asociación clara a uno de varios cruces quedan como contexto sin ubicación. Si faltan hallazgos publicables, la fila indica que no se identificó automáticamente una falla o cruce. Los conteos por cruce son filas del corte y conservan relatos independientes. La detección se informa por foto o fotograma de la conversación.

La descripción usa vocabulario predefinido, tipos de vía normalizados, duraciones acotadas y cantidades explícitas. La publicación automática incluye fecha y estado, sin nombres, contactos, archivos, enlaces ni texto libre de chat/transcripción. Las filas preliminares no se insertan como reportes revisados. El PDF general privado sigue siendo el corte de la tabla de reportes consolidados.

La tabla pública ordena primero los cruces que se pudieron identificar. **Registros en este cruce** cuenta las filas asociadas a esa intersección en el corte, incluida la fila abierta. El mapa está debajo de la tabla cuando aún no tiene puntos.

**Evidencias** muestra cantidades y enlaces por tipo. Distingue audio de WhatsApp, audio extraído de video, fotos, videos originales, fotogramas, TXT y otros archivos. Cuando se pueden asociar por los enlaces del chat, se cuentan los archivos del registro. Si la asociación de los medios es insuficiente, se muestra el inventario de la conversación identificado como tal. El TXT aporta el contexto de la conversación. Los enlaces abren el inventario privado con la clave del equipo. El catálogo público solo entrega las cantidades por tipo.

## Cartografía en el VPS

La capa oficial de referencia es [POT – Perímetro urbano de Cali](https://datos.cali.gov.co/dataset/pot-perimetro-urbano), publicada por Planeación/IDESC. Exportarla desde [el servicio WFS de IDESC](https://www.cali.gov.co/planeacion/publicaciones/46986/servicios-wfs-idesc/) con QGIS como GeoJSON en EPSG:4326. Seleccionar la capa `pot_2014:bcs_lim_perimetro_urbano` y colocarla en `/data/core/cartografia/cali-urbano.geojson` del volumen persistente, o indicar su ruta con `SC_URBAN_BOUNDARY`. Usar Polygon o MultiPolygon, opcionalmente envueltos en Feature o FeatureCollection. El servidor registra su huella SHA-256. La [ficha de la capa](https://mg-idesc.cali.gov.co/geonetwork/srv/api/records/8b181bf1-88d7-41c9-beaf-c7c2840ef724) documenta la licencia CC BY-SA 4.0.

La versión del PDF y la web comparten la misma proyección geográfica. Hasta cargar la capa se muestra una cuadrícula de referencia privada. Los puntos públicos requieren perímetro oficial. En los registros automáticos solo se proyectan coordenadas explícitamente asociadas al semáforo o cruce en la misma fuente que identifica las dos vías, con un par único. Las coordenadas fuera de la capa permanecen disponibles en la revisión privada y se excluyen del mapa público. El dominio definitivo puede apuntar a `/semaforos`; su configuración queda en Easypanel.

## Pausa y reanudación del piloto

1. Para consultar el mapa, el PDF y las métricas con los trabajadores detenidos, desplegar con `SC_PROCESS=api`. Esta modalidad también deja la importación de nuevos ZIP en espera. Mantener `SC_PARALLEL` y la configuración de los modelos actuales.
2. Por la noche, reactivar `SC_PROCESS=all` y desplegar. El trabajador consume la cola persistente. Al detectar una concesión vencida marca el intento anterior `worker_lost`. Si era el último intento, la tarea queda fallida y se puede reintentar una vez desde su conversación.
3. Revisar los errores nuevos antes de reencolar en bloque. Priorizar interrupciones y errores transitorios. Las citas sin respaldo y los truncamientos requieren inspeccionar la salida y su fuente para saber si repetir aporta valor. Usar **Métricas de modelos** para revisar el corte de fallos.

## Prueba reproducible

La prueba PostgreSQL recorre ZIP sintético, extracción simulada, afirmaciones, dos reportes independientes del mismo cruce, publicación depurada, métricas, corte PDF e integridad y expiración de enlaces. La prueba Chromium recorre navegación, ubicación, descarga y vista pública. Validar por separado en el VPS con una conversación elegida por el equipo y su configuración real.
