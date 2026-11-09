# Semáforos Cali

IA multimodal para conservar, interpretar y consultar reportes ciudadanos de semáforos en Cali. Proyecto de Esteban Oliveros Montoya, Maestría en IA Aplicada, Icesi.

## Estado real

- Mensajes WhatsApp versionados: fechas, remitentes privados, texto literal y referencias a archivos. [Trazabilidad y supuestos](docs/mensajes_whatsapp.md).

- Panel privado integrado: cargas reanudables → PostgreSQL → trabajador multimodal. [Carga web y recuperación](docs/carga_web.md).
- Nuevo núcleo privado `semaforos/`: PostgreSQL, cola, adaptadores audio/visión/texto, etiquetas y métricas. [Implementación y límites](docs/nucleo_multimodal.md). Inferencia real y despliegue pendientes.

- Ingesta continua: más de 100 carpetas disponibles según el usuario, con cargas diarias variables. No hay tamaño fijo de lote.
- `prototype/v0_4/` añade carga por bloques y validación independiente; probada localmente, sin despliegue. [Alcance y límites](prototype/v0_4/LEEME.md).

- 36 conversaciones completaron el procesamiento textual en el VPS, según el operador.
- `prototype/v0_3/` conserva el código disponible: texto mediante Ollama, extracción de audio y hasta 15 fotogramas por video. Incluye sus pruebas.
- Audio e imagen todavía no se interpretan automáticamente en este prototipo.
- La carga web ya está conectada al núcleo. Consolidación de reportes, mapa, PDF, correo e integración operativa n8n siguen pendientes. Este repositorio no despliega automáticamente al VPS.

## Documentación vigente

- [Diccionario y seis decisiones aprobadas](docs/diccionario.md)
- [Arquitectura modular y extensibilidad](docs/arquitectura.md)
- [Experimentos y comparación](docs/experimentos.md)
- [Estado y plan de implementación](docs/estado.md)
- [Operación y despliegue](docs/operacion.md)
- [Historial de cambios](CHANGELOG.md)

## Pruebas locales

Requisitos: Python 3.11 o 3.12 y FFmpeg/ffprobe en PATH.

```bash
python -m unittest discover -s tests -v
python -m unittest discover -s prototype/v0_3 -p 'test_*.py' -v
```

Las pruebas del prototipo generan archivos sintéticos temporales. No necesitan ZIP ciudadanos, acceso al VPS ni modelos descargados. La inferencia real se evaluará aparte con datos privados y etiquetas humanas.

## Comparar experimentos

```bash
python tools/compare_runs.py runs/base.json runs/candidato.json --output runs/comparacion.md
```

El comparador exige el mismo conjunto de datos y la misma versión de etiquetas. Muestra métricas y diferencias; no inventa una calificación global. Formato y ejemplo: [experimentos](docs/experimentos.md).

## Evolución

Cada cambio debe incluir código, pruebas pertinentes y actualización de documentación. Modelos, prompts y parámetros se versionarán por configuración. Una configuración propuesta no cambia el prototipo hasta conectar su lector. El despliegue integral se entregará en un paquete reproducible después de las pruebas y comprobación de compatibilidad con el VPS.

El repositorio contiene código y ejemplos sintéticos. Originales ciudadanos, contactos, modelos binarios, salidas privadas y secretos se conservan fuera de Git.
