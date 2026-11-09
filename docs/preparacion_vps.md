# Inspección previa del VPS — 2026-11-09

## Bloqueo de acceso actual

La apertura del panel histórico `http://5.189.163.123:3000` desde el navegador de trabajo devolvió `ERR_CERT_COMMON_NAME_INVALID`. No se omitió la advertencia ni se inició sesión. Es necesario el dominio administrativo HTTPS correcto o que el operador obtenga el diagnóstico desde la consola del host. No compartir contraseñas por el chat.

## Diagnóstico disponible

`deploy/inspect-vps.sh` consulta recursos del host, Docker/Swarm, servicios, uso instantáneo, redes, nombres de volúmenes y montajes/límites de los servicios semaforos. No imprime variables de entorno, credenciales, logs de aplicación ni contenidos de conversaciones. No inicia contenedores, modifica redes, instala paquetes ni ejecuta migraciones. Cada consulta principal tiene límite de 25 segundos cuando existe `timeout`. Se rechaza la ejecución dentro de contenedores.

Ejecutar con Bash en **consola del VPS de Contabo o SSH al host**, con permisos para consultar Docker. La terminal Bash de `ollama_semaforos`, `procesador-semaforos` o `n8n` no sirve para este inventario del host. Ante permiso denegado, no cambiar permisos del socket ni añadir usuarios automáticamente; usar la sesión administrativa habitual.

El informe es una instantánea: no representa máximos de consumo ni garantiza que un volumen tenga respaldo. Conservar la salida en un lugar privado y compartirla con el equipo técnico para definir los límites.

## Decisiones pendientes de la inspección

- Confirmar espacio real y margen de RAM/CPU mientras trabajan los proyectos existentes; los datos de capturas antiguas no son la capacidad actual.
- Identificar los volúmenes originales del procesador y Ollama. Nunca montar la base de contratos o n8n como base del nuevo núcleo.
- Elegir integración administrada por Easypanel compatible con el Swarm existente. `compose.core.yaml` es un candidato de integración, no un instalador validado de Easypanel; no usarlo a ciegas con `docker stack deploy`.
- Preparar base `semaforos_core`, volúmenes propios, red privada y acceso autenticado HTTPS. Confirmar la ruta interna de Ollama sin exponer su API públicamente.
- Construir la imagen, verificar versiones y archivos de modelos, y fijar sus identidades. El núcleo tiene adaptadores, pero no todos los pesos están provisionados ni probados en el VPS.
- Registrar respaldo verificable del lote existente antes de migrarlo. La primera prueba usa copias autorizadas de unas pocas conversaciones; no reemplaza el procesador actual.
- Validar carga, procesamiento, recursos, conservación de evidencia, reinicio y recuperación. Después se puede ampliar el lote.

## Qué está hecho y qué no

Código de diagnóstico preparado y sintaxis revisada. **Inventario real, construcción de imagen, instalación, respaldo y prueba con modelos en el VPS pendientes.** No se han modificado servicios existentes.
