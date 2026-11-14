# Curaduría y dos carriles · operación en Easypanel

Esta versión conserva originales, fuentes literales, predicciones y etiquetas humanas por separado. No entrena modelos ni certifica daños. No incorpora reproductor de video.

## Despliegue único

Esperar las tres comprobaciones verdes de la revisión final en GitHub; desplegar desde `main` tras su integración. En el servicio `semaforos-core`, conservar las variables privadas actuales y añadir/modificar:

```dotenv
SC_PROCESS=all
SC_PARALLEL=1
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
OPENBLAS_NUM_THREADS=2
```

Recursos iniciales del VPS de 6 vCPU y aproximadamente 12 GB RAM:

| Servicio | Límite CPU | Límite memoria |
|---|---:|---:|
| semaforos-core | 0 (sin límite) | 4096 MB |
| ollama_semaforos | 0 (sin límite) | 5120 MB |

Reservas CPU 0. Mantener los montajes `/data`, `/models` y `/root/.ollama` actuales. Estas cifras son límites, no memoria reservada ni núcleos nuevos. La ocupación real y los demás servicios del VPS determinan el margen.

`SC_PARALLEL=1` inicia dos trabajadores: texto y audio/detección/video. Cada carril admite una tarea a la vez. Los bloqueos de PostgreSQL impiden duplicar un carril y excluyen al trabajador diagnóstico o antiguo. El modelo de texto solicita cuatro hilos y permanece residente durante 30 minutos; multimedia usa dos hilos para los modelos y FFmpeg uno por extracción.

Consulta [Audio y microreportes](audio_y_microreportes.md) para el flujo actual.

## Uso y validación

1. En el panel, abrir **Procesamiento y resultados de los modelos** y desplegar una conversación. Se actualiza al refrescar los datos cada cinco segundos.
2. Ver miniaturas de detección; **Ampliar imagen** abre la anotación completa. Los fotogramas y audio están agrupados bajo su video original. No se reproduce video.
3. Escuchar audio a 1× o 1,5×, introducir el nombre del revisor y aprobar, marcar no evaluable o corregir la transcripción. La corrección pone en cola únicamente una nueva extracción de texto. Requiere trabajador activo.
4. La salida original permanece en **Salida del modelo**. Las extracciones anteriores se marcan sustituidas. Las etiquetas y métricas se guardan privadamente; no se muestran como estadísticas del negocio. Una aprobación no es una referencia independiente para medir precisión.
5. Comparar los mismos cinco ZIP con una nueva etiqueta de experimento, por ejemplo `curaduria-dos-carriles-01`, manteniendo esa etiqueta durante el lote. El ZIP ya conocido se conserva y sus tareas nuevas se identifican por experimento, configuración y entradas. No usar los tiempos históricos como prueba de mejora si cambian los archivos.
6. Registrar duración del lote, errores por etapa, CPU, memoria máxima observada y disco antes/después. Revisar todas las fuentes ciudadanas y las correcciones. Solo después, probar 25 ZIP y luego el resto. Las pruebas de CI no miden velocidad ni precisión real de los modelos en el VPS.

Una barra sin porcentaje es actividad sin avance cuantificable, no 0 % real. El total de tareas puede crecer al descubrir derivados; no equivale al número de reportes ciudadanos.

## Filtrado y derivados

Se omiten mensajes cuyo remitente normalizado coincide exactamente con `Esteban Oli`. Solo se omite audio con vínculo explícito en el chat y todos sus remitentes identificados pertenecientes al equipo. Si falta ese vínculo o es ambiguo, se conserva para evitar perder información ciudadana. Los nombres originales y mensajes íntegros permanecen en almacenamiento. Las salidas históricas mixtas requieren reprocesar los mensajes ciudadanos; no se elimina una conversación entera.

Audio: derivado mono, 16 kHz PCM, reutilizado por SHA-256 bajo `derived/audio-v1/`. No se recomprime a MP3. Whisper conserva INT8 y detección de voz. Fotos: YOLO conserva entrada de 960 píxeles; miniatura de revisión separada de hasta 480×320. Video: se mantiene la regla aprobada de hasta 15 fotogramas por video, sin cambiar el original.

## Límites actuales

La etiqueta de aprobación evalúa la salida seleccionada, no consolida automáticamente un incidente. **Organizar reportes** conserva esa función. **Versiones de conversaciones** conserva comparación de exportaciones y decisiones de identidad sin deducir que `(2)` significa siempre una versión posterior. Los reportes ya organizados deben revisarse si se corrige una fuente; no se reescribe silenciosamente su historia.

Las salidas muy antiguas sin remitentes identificables se conservan para revisión. El almacenamiento y respaldo continúan únicamente en VPS conforme al alcance aprobado.
