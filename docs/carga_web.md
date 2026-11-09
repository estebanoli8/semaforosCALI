# Carga web integrada — v0.6

Fecha de actualización: 2026-11-08 (Colombia).

## Resultado de esta etapa

El núcleo tiene una página privada de carga y seguimiento, en `/`. Las sesiones de carga, las conversaciones y las tareas viven en PostgreSQL. No se arranca el servidor antiguo v0.4 ni se mantiene una segunda cola de análisis en SQLite. Esta implementación todavía no está desplegada en el VPS.

1. El equipo abre la página mediante HTTPS e ingresa la clave `SC_API_TOKEN` del entorno. Se conserva solo en memoria de la pestaña; nunca en URL, Git, localStorage ni cookies.
2. Selecciona los ZIP y el experimento. Se pueden seleccionar más de 100 y agregar lotes posteriormente. El número de archivos no tiene un límite fijo de lote.
3. Cada ZIP se transmite secuencialmente en bloques de hasta 4 MiB, con SHA-256 por bloque. El servidor confirma los offsets en PostgreSQL después de escribir y sincronizar el archivo.
4. Al terminar, la carga queda `queued`. El trabajador valida/importa fuera de la petición HTTP y encola sus tareas de texto, audio, foto o video.
5. El panel distingue `received` (ZIP importado) de tareas de modelo `completed`. Una copia original queda persistida con su nombre; la copia temporal de transporte se elimina tras confirmar la importación.

No se promete almacenamiento infinito: la carga depende del espacio libre y de la reserva configurable (3 GiB iniciales). La reserva contempla los bytes que faltan de otras cargas abiertas. La importación comprueba además el tamaño descomprimido anunciado y el espacio durante la extracción. No se publica aún un número de reportes: las conversaciones pueden contener varios hechos y la consolidación está pendiente.

## Interrupciones y versiones

- Recargar/cerrar la página no detiene el trabajador. Para reanudar una subida incompleta hay que entrar y volver a seleccionar el mismo ZIP.
- Los bloques previos se reenvían y verifican; esto consume red pero evita confiar en nombres/fechas. Los bloques iguales ya confirmados no vuelven a escribirse.
- Un bloque distinto para la misma sesión produce `resume_content_mismatch`. El operador cancela la carga incompleta y carga el archivo correcto. Nunca se sobrescribe una sesión por llamarse igual.
- ZIP idéntico con otro nombre conserva ambas referencias de archivo fuente, pero comparte conversación/evidencias/tareas del mismo experimento, configuración y versión de código.
- ZIP ampliado o cambiado conserva otra versión de contenido. Su asociación con conversaciones/reportes anteriores requiere la futura consolidación; `(1)` y `(2)` no prueban que una versión sustituya a otra.
- Una caída entre escribir disco y confirmar offset descarta la cola no confirmada al reanudar. Una caída después de importar pero antes de confirmar la carga recupera la importación idempotentemente.
- Tres interrupciones de importación llevan a error. Los ZIP corruptos se marcan de inmediato sin frenar los otros. Reintentar es explícito y conserva el ZIP; cancelar elimina solo la copia temporal, no las evidencias previamente persistidas.

## Configuración y aislamiento

La migración `002_uploads.sql` agrega el transporte sin editar `001_processing.sql`. Cada sesión conserva el experimento, configuración completa y su huella. Cambiar `config/modelos.json` no altera sesiones ya abiertas.

Importación y una tarea pesada comparten el bloqueo global PostgreSQL. El trabajador importa como máximo un ZIP y procesa una tarea por ciclo, para que ambos progresen. La API no carga modelos ni descomprime ZIP. El CLI de importación respeta el mismo bloqueo y se niega a competir con el trabajador.

El panel es privado. Las rutas estáticas de acceso no contienen información ciudadana; todas las consultas y acciones requieren Bearer. No se usan recursos JavaScript de terceros. Respuestas con `Cache-Control: no-store` y política CSP. El token identifica al equipo, no a cada operador: cuentas individuales y auditoría por usuario están pendientes. Publicar solo detrás de HTTPS y con la API y el trabajador apuntando al mismo volumen y base exclusiva.

## Rutas añadidas

| Ruta | Función |
|---|---|
| GET /summary | Conversaciones, originales, tareas por estado, espacio y reserva |
| GET /uploads?offset=0&limit=100 | Historial paginado (máximo 200 por página) |
| POST /uploads | `name`, `size`, `experiment_id`; congela configuración |
| GET /uploads/{id} | Estado y resultado de importación |
| PUT /uploads/{id}/chunk?offset=N | Bytes del bloque; cabecera `X-Chunk-SHA256` |
| POST /uploads/{id}/finish | Confirma subida completa y pone en cola |
| POST /uploads/{id}/cancel | Cancela una carga incompleta/en cola/con error |
| POST /uploads/{id}/retry | Reintenta una importación fallida |

GET /jobs ahora incluye el ID del último intento para abrir su salida y métricas. El panel muestra estados pendientes, errores y salidas crudas; aún no es el panel final de etiquetado ni el sitio ciudadano.

## Verificación

`tests/core/test_uploads.py` usa PostgreSQL real en GitHub Actions y ZIP sintéticos. Verifica autenticación, límite de memoria por bloque, reanudación, bloque duplicado concurrente, configuración congelada, rutas maliciosas, reserva de disco, paginación por encima de 100 cargas, recuperación tras importación y el camino HTTP → trabajador → resultado. La inferencia en estas pruebas es una función sintética: no acredita calidad de modelos reales.

Próximo bloque: parser de WhatsApp con fechas y mensajes fuente, consolidación de hechos/versiones y panel de revisión. Luego mapa, PDF general, correo y n8n; finalmente empaquetado integral y validación en el VPS sin modificar otros proyectos.
