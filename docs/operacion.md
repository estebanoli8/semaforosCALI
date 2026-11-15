# Operación y despliegue

El núcleo integrado opera en Easypanel. Mantener el Deploy manual de una versión identificada después de revisar las pruebas y preservar el respaldo. El [procedimiento de despliegue](despliegue_easypanel.md) y la [verificación de la cola](observabilidad.md#corte-agregado-del-piloto) describen el flujo de uso actual.

El prototipo disponible tiene instrucciones específicas en prototype/v0_3/LEEME.md. Su Dockerfile se construye con ese directorio como contexto. No usar la raíz del repositorio como contexto de ese Dockerfile.

Antes de una instalación, comprobar recursos libres, versiones, redes, puertos y volúmenes existentes. Reutilizar servicios propios compatibles y conservará el lote. Las credenciales se configuran en el VPS; no se guardan en Git, ejemplos ni logs. Los nombres/rutas de volúmenes se comprueban antes de migrar.

Respaldo consistente de base y archivos antes de migraciones; registrar conteos y referencias antes/después. Una copia en el mismo VPS no protege la pérdida completa del servidor. El alcance aprobado de almacenamiento sigue siendo solo VPS.

Criterios de aceptación del paquete: carga/duplicados, reinicio y recuperación, referencias originales, separación público/privado, límites de recursos, resultados parciales, correo recuperable, PDF con corte consistente y restauración probada. El despliegue no equivale a calidad del modelo: esta se evalúa con etiquetas humanas.
