# Experimentos y resultados visibles

El objetivo es cambiar una variable, observar su efecto y poder volver al resultado anterior. Las 36 conversaciones son exploratorias; reservar nuevos datos sin duplicados para evaluación.

## Registro por ejecución

Cada ejecución llevará run_id, git_commit, versión/digest del modelo, prompt/configuración, dataset_id, labels_version, fecha, métricas, tamaño evaluado, errores y rutas privadas a predicciones. Registrar métricas por modalidad y cobertura de casos indeterminados. Sin etiquetas, calidad desconocida; no cero.

La interfaz futura tendrá una tabla de experimentos, comparador A/B, ejemplos correctos/erróneos y acceso a evidencia. Por ahora se incluye un comparador de archivos JSON que genera Markdown.

## Formato del comparador disponible

```json
{
  "run_id": "ejemplo-sintetico",
  "dataset_id": "evaluacion-01",
  "labels_version": "etiquetas-01",
  "metrics": {
    "texto_f1": {"value": 0.8, "direction": "higher"},
    "audio_wer": {"value": 0.2, "direction": "lower"},
    "latencia_segundos": {"value": 30.0, "direction": "lower"}
  }
}
```

Estos números ilustran el formato, no son resultados del proyecto. Los campos adicionales de procedencia pueden incluirse. Para comparar, nombres de métricas y dirección deben coincidir. Una métrica ausente o NULL se muestra sin comparación. No comparar ejecuciones con distinto dataset o etiquetas mediante esta herramienta.

Los archivos runs permanecen privados. El resumen también puede incluir información sensible en nombres o referencias; publicar solo resultados agregados revisados.

## Métricas previstas

Audio: WER, errores de ubicación y tiempo relativo de procesamiento. Texto: precisión/cobertura, omisiones y afirmaciones sin respaldo. Visión: precisión/recall de cajas con IoU definido, desempeño por luz y cobertura indeterminada. Geografía: ubicación correcta y cobertura. Sistema: tiempo, memoria máxima, CPU, fallos, reintentos y recuperación.

Cada cambio de código actualiza CHANGELOG, documentación afectada y pruebas pertinentes. Pruebas de regresión comprueban reglas aprobadas; evaluación mide calidad del modelo. Son verificaciones diferentes.
