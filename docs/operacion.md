# Operación y despliegue

El paquete integral está pendiente. No conectar auto-deploy a main mientras se construye. Instalar solo una versión identificada tras pruebas y respaldo.

El prototipo disponible tiene instrucciones específicas en prototype/v0_3/LEEME.md. Su Dockerfile se construye con ese directorio como contexto. No usar la raíz del repositorio como contexto de ese Dockerfile.

La próxima instalación comprobará recursos libres, versiones, redes, puertos y volúmenes existentes. Reutilizará servicios propios compatibles y conservará el lote. Las credenciales se configuran en el VPS; no se guardan en Git, ejemplos ni logs. Los nombres/rutas de volúmenes se comprueban antes de migrar.

Respaldo consistente de base y archivos antes de migraciones; registrar conteos y referencias antes/después. Una copia en el mismo VPS no protege la pérdida completa del servidor. El alcance aprobado de almacenamiento sigue siendo solo VPS.

Criterios de aceptación del paquete: carga/duplicados, reinicio y recuperación, referencias originales, separación público/privado, límites de recursos, resultados parciales, correo recuperable, PDF con corte consistente y restauración probada. El despliegue no equivale a calidad del modelo: esta se evalúa con etiquetas humanas.
