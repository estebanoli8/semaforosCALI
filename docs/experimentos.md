# Experimentos y resultados visibles

El objetivo es cambiar una variable, observar su efecto y poder volver al resultado anterior. Las 36 conversaciones son exploratorias; reservar nuevos datos sin duplicados para evaluación.

## Registro por ejecución

Cada ejecución llevará run_id, git_commit, versión/digest del modelo, prompt/configuración, dataset_id, labels_version, fecha, métricas, tamaño evaluado, errores y rutas privadas a predicciones. Registrar métricas por modalidad y cobertura de casos indeterminados. Sin etiquetas, calidad desconocida; no cero.

El portal privado **Desempeño de modelos** filtra por experimento y presenta latencia, fallos y calidad según evaluaciones guardadas. El comparador local de archivos JSON genera Markdown cuando ambas ejecuciones comparten conjunto y etiquetas.

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

## Comparación de Qwen en el VPS

Para medir la aceleración del perfil completo, usar las mismas conversaciones y las mismas fuentes originales en los dos perfiles. Fijar la identidad del modelo, versión de Ollama, recursos y condiciones de concurrencia. Anotar los hilos efectivos por perfil y separar arranque en frío de modelo residente. Si interesa aislar el preprocesamiento, fijar también los hilos. Si interesa medir el efecto de los hilos, fijar el preprocesamiento.

Comparar lotes cerrados. Sumar por conversación la duración de sus llamadas, incluidos rescates y reintentos registrados, y conservar el tamaño de muestra, errores y truncamientos. Reportar mediana y p90, tokens de entrada/salida y, por separado, tiempo del proceso completo incluida la espera. Si el perfil anterior solo tiene `wall_seconds`, comparar esa misma métrica en ambos. El historial por tarea y el acumulado de Ollama por conversación tienen denominadores diferentes.

Para medir calidad, usar referencias humanas por los cuatro campos. Registrar verdaderos positivos, falsos positivos y omisiones. Una ausencia revisada y una fuente aún pendiente se codifican por separado. [Consulta y lectura del corte operativo](observabilidad.md#corte-agregado-del-piloto).

## Métricas por modalidad

Audio: WER, errores de ubicación y tiempo relativo de procesamiento. Texto: precisión/cobertura, omisiones y afirmaciones sin respaldo. Visión: precisión y exhaustividad de cajas con IoU definido y coincidencia de conteos revisados. Geografía: ubicación correcta y cobertura. Sistema: tiempo, memoria máxima, CPU, fallos, reintentos y recuperación.

Cada cambio de código actualiza CHANGELOG, documentación afectada y pruebas pertinentes. Pruebas de regresión comprueban reglas aprobadas; evaluación mide calidad del modelo. Son verificaciones diferentes.
