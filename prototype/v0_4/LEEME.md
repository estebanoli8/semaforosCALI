# v0.4 — carga continua reanudable

**Implementado y probado localmente; no desplegado en VPS.** La transcripción/visión, PostgreSQL, panel integral, mapa, PDF, correo e integración n8n siguen pendientes. Esta versión no es el instalador completo.

Las 36 conversaciones son la referencia exploratoria inicial. El usuario ya dispone de más de 100 carpetas y recibirá cargas diarias variables. No hay cupo fijo de conversaciones.

## Operación

Seleccionar ZIP individuales en la interfaz HTTPS. Se envían uno a uno en bloques de 4 MiB, escritos a disco antes de confirmar. Si se interrumpe la conexión, seleccionar los mismos archivos desde el mismo navegador: se releen y verifican los bloques previos con SHA-256, sin retransmitir los coincidentes. Nombre, fecha y tamaño solos no prueban igualdad.

Mantener la pestaña abierta hasta completar la transferencia. Después puede cerrarse: la validación y la cola de análisis se ejecutan en el servidor. Pulsar Iniciar para activar análisis; la validación de cargas es independiente de la pausa del modelo. Se pueden agregar archivos mientras se procesan los anteriores.

Estados de carga: recibiendo → pendiente → validando → recibido / error. Recibido significa ZIP aceptado y registrado, no inferencia terminada. El panel muestra por separado el estado de procesamiento. Un ZIP inválido no detiene los siguientes.

Las cargas incompletas/con error pueden cancelarse explícitamente desde el panel para liberar espacio. Si se pierde el almacenamiento local del navegador se inicia otra sesión y puede cancelarse la anterior. Al volver a subir un ZIP completo se verifica su contenido; los duplicados no crean otro trabajo. Los sufijos (1)/(2) no autorizan reemplazar información.

## Tamaños y recursos

Se elimina el límite fijo de 1 GiB por ZIP de la ruta anterior. El tamaño admisible depende del disco libre, la reserva y las cargas ya comprometidas; **no es almacenamiento ilimitado**.

| Configuración | Valor inicial | Motivo |
|---|---|---|
| Bloque HTTP | 4 MiB | Memoria de recepción acotada por petición |
| STORAGE_RESERVE_BYTES | 3221225472 (3 GiB) | Reserva de disco; comprobación por bloque |
| MAX_ZIP_ENTRIES | 100000 | Protección del inventario de un ZIP |
| MAX_CHAT_BYTES | 33554432 (32 MiB) | El parser actual carga el chat en memoria |
| Trabajadores de validación | 1 | Hash y registro seriales |
| Trabajadores de análisis | 1 | Comportamiento del prototipo existente |
| Réplicas | 1 | Recuperación SQLite/bloqueos locales |

El espacio mostrado pertenece al filesystem compartido. Otros servicios pueden consumirlo: por eso se comprueba de nuevo durante las transferencias. También se valida espacio para el tamaño descomprimido declarado y se rechazan rutas inseguras. Los derivados requieren espacio adicional. No ampliar límites sin medir recursos. La preparación audiovisual conserva su duración máxima previa de 600 segundos por video.

El panel muestra hasta 200 sesiones de carga recientes; no limita cuántas se aceptan. La tabla de trabajos conserva todos los registros. Paginación completa pendiente del panel integrado.

## Persistencia

- cola.sqlite: trabajos históricos compatibles con v0.2/v0.3.
- cargas.sqlite: sesiones, tamaños, bytes confirmados y estado.
- cargas/<id>.part: transferencias en curso.
- <sha256_zip>/original.zip: archivo aceptado y estructura histórica de resultados.

Tras caída en medio de un bloque se conserva el offset confirmado y se descarta la escritura no confirmada al reintentar. Durante registro se conserva un enlace al ZIP hasta guardar estado final; si el proceso cae después de mover el archivo, al reiniciar puede reconocerse como duplicado. No ejecutar dos instancias sobre este volumen.

## Construcción y validación

Contexto Docker: prototype/v0_4. Puerto interno 8000. Volumen /data. Conserva APP_PASSWORD (mínimo 16 caracteres), OLLAMA_URL, OLLAMA_MODEL, DATA_DIR. Dockerfile incluye uploads.py. Construcción Docker y validación en VPS pendientes.

```bash
python -m unittest discover -s prototype/v0_4 -p 'test_*.py' -v
```

Once pruebas: 125 cargas sintéticas con nuevas llegadas, error aislado, bloques repetidos/alterados/incompletos, reinicio, reserva de disco, tamaño declarado superior a 1 GiB, HTTP real local, duplicados y compatibilidad audiovisual. La prueba de tamaño declarado no transfiere un ZIP real de más de 1 GiB. No equivale a evaluación ML ni rendimiento de 125 conversaciones reales.

Próximo paso: integrar esta recepción en la aplicación modular, manteniendo su contrato y pruebas. Validar respaldo y volumen antes de cualquier sustitución del servicio VPS.
