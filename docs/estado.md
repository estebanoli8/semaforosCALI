# Checkpoint del repositorio — 2026-11-08

## Decisiones vigentes

El usuario aprobó las seis decisiones, el diccionario completo y los seis indicadores del documento de 2026-11-08. Añadió modificabilidad, comparación sencilla de pruebas, documentación paralela y este repositorio como fuente de código. docs/diccionario.md contiene el detalle aprobado.

## Avance

Actualización: más de 100 carpetas disponibles según el usuario; las 36 iniciales son referencia exploratoria, no el total ni el límite. v0.4 incorpora carga reanudable y validación independiente; 11 pruebas locales, incluyendo 125 cargas sintéticas. Sin despliegue VPS.

| Elemento | Estado |
|---|---|
| Lote textual de 36 conversaciones / 39 fragmentos | Completado según usuario; calidad pendiente |
| Código v0.3 de preparación audiovisual | Disponible y probado localmente; despliegue VPS no confirmado |
| Reglas y diccionario | Aprobados |
| Repositorio, documentación y comparador local | Incluidos en esta entrega |
| Whisper, detector/lectura de luces | Adaptadores implementados en núcleo privado; inferencia real pendiente |
| PostgreSQL | Esquema, cola y revisión implementados; validación CI y VPS por registrar |
| Integración operativa n8n | Pendiente |
| Panel completo de experimentos, mapa, PDF y correo | Pendiente |
| Instalador integral | Pendiente de construcción y verificación de infraestructura |

## Plan

1. Verificar infraestructura y definir instalación compatible sin cambios a otros proyectos.
2. Implementar contratos, persistencia y migración del lote con respaldo y validación de conteos.
3. Integrar adaptadores, etapas reanudables y evaluación por modalidad.
4. Añadir revisión, mapa, PDF general y notificaciones persistentes.
5. Empaquetar, probar recuperación y validar en VPS.

No se acredita ninguna acción nueva en el VPS por crear este repositorio. Chatbot, reentrenamiento, Drive y X siguen fuera de esta entrega.
