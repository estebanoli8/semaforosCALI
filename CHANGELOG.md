# Historial

## Base de desarrollo — 2026-11-08

- Incorporado prototipo v0.3 existente con sus pruebas.
- Registrados diccionario y seis decisiones aprobadas.
- Documentadas arquitectura modular, experimentación y operación.
- Añadido comparador de métricas JSON y pruebas de regresión del comparador.
- Configuración de experimentos propuesta; todavía no conectada al worker.
- Pipeline de pruebas en GitHub; sin despliegue automático ni datos ciudadanos.

## 2026-11-08 — v0.4 carga continua

- Más de 100 conversaciones y llegadas diarias variables como requisito.
- Carga por bloques, verificación SHA-256, reanudación y validación asíncrona.
- Protección de espacio disponible y cancelación explícita de cargas incompletas.
- 11 pruebas locales (incluyen 125 cargas sintéticas); no desplegado en VPS.
