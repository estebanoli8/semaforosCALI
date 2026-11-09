# Mensajes y fechas originales — v0.7

Esta etapa agrega trazabilidad antes de consolidar reportes. No convierte cada mensaje ni cada ZIP en un reporte. Implementación en `semaforos/whatsapp.py` (parser), `messages.py` (persistencia) y migración nueva `003_messages.sql`.

## Qué queda almacenado

- Texto completo de `chat.txt`, bloques de mensaje y cuerpo literal, sin limpiar ni corregir declaraciones. Los ZIP originales siguen intactos. Las cargas nuevas conservan CRLF; una lectura histórica almacenada conserva su versión anterior, sin reescribirla.
- Remitente visible, exclusivamente privado. No se transforma en un ID público ni se interpreta como identidad verificada.
- Cabecera temporal original y fecha UTC interpretada, separadas de los tiempos de carga y procesamiento.
- Posición inicial/final en caracteres del texto decodificado para reconstruir el fragmento exacto. No son offsets de bytes del ZIP.
- ID de mensaje, ID de evidencia y versión/configuración del parser. Cambiar la configuración crea otra lectura y conserva la anterior.
- Referencias explícitas a archivos (`<attached: ...>`, `<adjunto: ...>` o `archivo adjunto`). Un nombre único se vincula; varias coincidencias quedan `ambiguous`; ninguna, `missing`. No se relaciona un audio por mera proximidad al mensaje anterior.

El adaptador de texto recibe fuentes con ID de mensaje, fecha interpretada, indicador de incertidumbre y offsets. Las salidas conservan esas fuentes. Los mensajes grandes se fragmentan conservando el mismo ID; los pequeños se agrupan dentro del límite de contexto. Los avisos sin remitente se conservan pero no se envían como denuncias al modelo; texto sin formato reconocido sí puede analizarse, con fecha desconocida.

## Fechas: decisión explícita, no certeza inventada

`config/modelos.json` incluye `whatsapp.date_order=DMY`, `timezone=America/Bogota` y `two_digit_century=2000`. Son convenciones configuradas para este piloto, no metadatos acreditados del teléfono. Los indicadores `date_order_assumed`, `timezone_assumed` y `century_assumed` lo registran. La zona horaria normalmente no viene en la cabecera: no se confunde la fecha del mensaje con una fecha de observación.

Para un lote de formato desconocido, `date_order=AUTO` deja `03/04/26` sin resolver. `13/04/26` o `04/13/26` permiten resolver el orden. `MDY` es una opción explícita. Una fecha imposible queda nula y marcada `invalid_datetime`; el texto se conserva. No se utiliza la fecha del servidor para completarla. Los años de dos dígitos usan el siglo configurado, sin una ventana temporal implícita.

No se calculan días continuos de avería. “Hace tres días” sigue siendo una declaración literal. Tampoco se atribuye la fecha de un texto a todas las fotos de una carpeta. Un enlace explícito mensaje→evidencia permite una futura consolidación con revisión humana; aún no certifica el momento de captura del archivo.

## Consulta privada

- `GET /evidence/{id}/chat-parses`: lecturas disponibles y configuraciones.
- `GET /chat-parses/{id}/messages?offset=0&limit=50`: mensajes, fechas, remitentes y vínculos; máximo 200 por página.
- Ambas rutas requieren el Bearer privado. Ninguna se publica en el portal ciudadano.

La importación web indexa después de guardar todos los originales y antes de encolar texto. Las cargas repetidas conservan los IDs del mismo contenido/configuración. Ejecutar texto desde `/jobs` también asegura el índice. El nuevo esquema no modifica migraciones aplicadas ni resultados anteriores.

## Límites y validación

Se prueban exportaciones sintéticas iOS/Android, AM/PM en español, segundos opcionales, formatos DMY/MDY/YMD, Unicode y mensajes multilínea. Un texto que imite exactamente una cabecera puede parecer otro mensaje; formatos no reconocidos necesitan revisión. No se promete detectar todos los idiomas de exportación.

Las pruebas PostgreSQL verifican idempotencia, versiones, enlaces únicos/ambiguos/ausentes, autenticación y trazabilidad. No se han evaluado aquí las más de 100 conversaciones reales ni la calidad de Whisper/YOLO/Qwen.

Siguiente bloque: consolidación revisable de hechos/reportes y versiones de conversaciones; interfaz de revisión. Mapa, PDF general, correo y n8n siguen pendientes. Despliegue VPS no realizado.
