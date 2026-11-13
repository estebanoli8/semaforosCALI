# Despliegue del núcleo en Easypanel

Para la interfaz de curaduría y activación de dos carriles, seguir [Curaduría y rendimiento](curaduria_rendimiento.md). La configuración de un solo trabajador descrita abajo sigue siendo compatible si `SC_PARALLEL` no está activado.

El despliegue inicial usa un solo servicio de aplicación con `SC_PROCESS=all`.
La API privada y el trabajador comparten el mismo volumen de evidencias, mientras
PostgreSQL y Ollama permanecen como servicios independientes del proyecto
`semaforos`. Al iniciar, el servicio aplica las migraciones versionadas bajo un
bloqueo de PostgreSQL y luego supervisa ambos procesos.

## Servicios

- `semaforos-core-db`: PostgreSQL exclusivo, base y usuario `semaforos_core`.
- `semaforos-core`: imagen construida desde este repositorio con
  `deploy/Dockerfile.core`, puerto interno 8000 y volumen `data` en `/data`.
- `ollama_semaforos`: API interna de Ollama ya existente; no se expone a Internet.

## Variables privadas de `semaforos-core`

```dotenv
SC_PROCESS=all
SC_DATABASE_URL=<URL interna de semaforos-core-db>
SC_API_TOKEN=<token aleatorio de al menos 32 caracteres>
OLLAMA_URL=http://ollama_semaforos:11434
SC_STORAGE=/data/core
SC_MODELS_DIR=/models
OMP_NUM_THREADS=2
MKL_NUM_THREADS=2
```

No se almacenan contraseñas ni tokens en Git. El dominio HTTPS apunta al puerto
interno 8000. El panel pide el token y lo conserva únicamente en memoria del
navegador. El volumen `data` es obligatorio antes de cargar ZIP.

## Límites iniciales

- Servicio `semaforos-core`: 3 GB de memoria y 2 CPU.
- PostgreSQL: 512 MB y 0.5 CPU.
- Ollama: 4 GB; no ejecutar más de una inferencia pesada simultánea.

La primera validación comprueba migraciones, estado de API, conexión privada con
Ollama, persistencia tras un redeploy y un ZIP de prueba copiado del lote ya
respaldado. El lote histórico no se migra hasta superar esas comprobaciones.
