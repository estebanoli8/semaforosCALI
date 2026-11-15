# Seguimiento del procesamiento privado

## Prueba controlada después de detener el lote

Desplegar con `SC_PROCESS=api` mantiene el panel disponible sin iniciar el
trabajador automático. Con Ollama activo, ejecutar desde el contenedor core:

```bash
python -m semaforos.trial --stage text
```

Cada comando selecciona la entrada más pequeña de esa etapa que ya falló y
crea un trabajo en un experimento nuevo con la configuración actual y un solo
intento. El bloqueo global evita inferencias simultáneas; la selección por ID
evita consumir tareas del lote anterior. Las salidas quedan en el panel. El
comando devuelve código distinto de cero si falla: revisar ese resultado antes
de continuar. La indexación de hallazgos y la cola completa se reanudan cuando
se vuelve a desplegar con `SC_PROCESS=all`.

El panel de `semaforos-core` muestra el avance total de **tareas conocidas**.
Un video crea nuevas tareas cuando termina la extracción de sus fotogramas y
audio, por lo que el porcentaje puede disminuir sin perder trabajo. Cuenta las
tareas terminadas, incluso las fallidas, y muestra aparte los errores. No se
confunde con el número de conversaciones ni de reportes revisados.

Cada fila identifica la conversación original y el archivo; para fotogramas,
también el video de origen y el segundo. Las barras de una tarea en ejecución
son indeterminadas si la herramienta no informa avance medible. Whisper puede
dar segundos transcritos; Qwen expone texto provisional a medida que responde.
Ese texto es un borrador privado, sujeto a validación de formato y origen al
finalizar. Una respuesta parcial nunca se registra como predicción terminada.

Las imágenes anotadas se consultan mediante la API privada con el token de la
sesión en memoria. El navegador libera cada copia al cerrar o cambiar de
tarea. Los archivos originales, las salidas y los reintentos permanecen en
`/data/core`; el panel no cambia su contenido.

Si falla la extracción de texto o la transcripción, el panel ofrece
**Reintentar modelo** para una ejecución adicional con la configuración de esa
tarea. Conserva los intentos anteriores y solo permite reintentar una tarea
ya fallida, hasta cinco intentos en total. Los códigos de error conocidos de validación se muestran
sin incluir el texto ciudadano; los mensajes arbitrarios del modelo y de las
librerías siguen ocultos. Un nuevo intento no garantiza una salida válida.

Antes de cambiar recursos en Easypanel, medir CPU/RAM del host y de los dos
contenedores bajo carga (`docker stats --no-stream`), y revisar `wall_seconds`,
`cpu_seconds`, `peak_rss_bytes` y tiempos de Ollama en la salida de una tarea.
Con 6 núcleos y 12 GB compartidos con otras aplicaciones, subir todos los
límites sin medir puede degradar servicios ajenos. Un aumento de CPU del núcleo
solo ayuda a las etapas locales que pueden usar esos hilos; Ollama consume CPU
en su propio servicio. Cambiar límites en Easypanel requiere desplegar y
reinicia el servicio; esperar a que termine la tarea actual y comprobar después
el estado del trabajador, los volúmenes y la cola.

## Corte agregado del piloto

Ejecuta este bloque en la consola de `semaforos-core` mientras se procesa
`detalle-qwen-v3`. La consulta de solo lectura es compatible con el despliegue
`bc03ef2` y usa un mismo corte de PostgreSQL para todos los conteos.

```bash
/usr/local/bin/python - <<'PY'
from collections import Counter
from semaforos.detailed import read_conversations
from semaforos.quality_metrics import collect
from semaforos.store import Store
from semaforos.text_fields import FIELDS

batch = "detalle-qwen-v3"
with Store().connect() as db:
    db.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
    cut = db.execute("SELECT now() AT TIME ZONE 'America/Bogota' AS local").fetchone()
    tasks = db.execute("""
        SELECT stage, CASE WHEN state='running' AND lease_until<=now()
                           THEN 'running_vencido' ELSE state END AS status, count(*) AS n
        FROM jobs WHERE experiment_id=%s AND NOT (payload ? 'superseded_by_review')
        GROUP BY 1,2 ORDER BY 1,2
    """, (batch,)).fetchall()
    uploads = db.execute("""
        SELECT state,count(*) AS n FROM uploads WHERE experiment_id=%s
        GROUP BY state ORDER BY state
    """, (batch,)).fetchall()
    cohort = {row["id"] for row in db.execute("""
        SELECT e.conversation_id::text AS id FROM jobs j JOIN evidence e ON e.id=j.evidence_id
        WHERE j.experiment_id=%s AND NOT (j.payload ? 'superseded_by_review')
        UNION
        SELECT result->>'conversation_id' FROM uploads
        WHERE experiment_id=%s AND state='received'
    """, (batch,batch))}
    rows = [row for row in read_conversations(db)[0] if str(row["id"]) in cohort]
    profiles = db.execute("""
        SELECT r.model_identity->>'extraction' AS profile,
               r.model_identity->>'threads' AS threads, count(*) AS n
        FROM runs r JOIN jobs j ON j.id=r.job_id
        WHERE j.experiment_id=%s AND j.stage='text' AND r.state='completed'
          AND NOT (j.payload ? 'superseded_by_review') AND NOT (r.output ? 'excluded')
        GROUP BY 1,2 ORDER BY 1,2
    """, (batch,)).fetchall()
    metrics = collect(db,batch,None)

print("Corte Cali:", cut["local"])
print("Tareas:", tasks)
print("ZIP:", uploads)
print("Conversaciones del detalle por estado:",
      dict(Counter(row["analysis_state"] for row in rows)))
print("Conversaciones con hallazgos por campo:", {
    field: sum(any(episode["fields"][field] for episode in row["episodes"]) for row in rows)
    for field in FIELDS
})
print("Qwen por perfil e hilos:", profiles)
print("Qwen llamadas y tiempos:", dict(metrics["qwen_calls"]))
print("Evaluaciones Qwen por campo:", {
    field: item["samples"] for field,item in metrics["human_evaluations"]["text"]["fields"].items()
})
PY
```

| Señal | Cómo leerla |
| --- | --- |
| `pending`, `running`, `running_vencido` | Pendiente, en curso y ejecución cuyo lease expiró, respectivamente. Una tarea con lease vencido queda por recuperar. |
| ZIP `receiving`, `queued`, `importing`, `received` | Recepción incompleta, listo para importar, importándose e importado. Reanudar una recepción incompleta seleccionando el mismo ZIP. |
| Conversaciones y hallazgos | Una conversación cuenta una vez por campo aunque tenga varios episodios. El detalle puede incorporar resultados previos compatibles. El hallazgo indica cobertura, y su acierto requiere cotejo con la evidencia. |
| `completed` en el detalle | Las etapas de texto, audio y preparación de video seleccionadas para la conversación no muestran trabajo pendiente ni fallos conocidos. La categoría `partial` identifica fallos de alguna de esas etapas. |
| Perfil e hilos | Una fila `compact-v1` acredita ejecuciones de texto finalizadas con el adaptador nuevo. Los hilos son los solicitados a Ollama. |
| Qwen | Los percentiles suman llamadas instrumentadas por conversación, incluidos rescates. Durante la tanda pueden reflejar conversaciones aún abiertas. Para medir aceleración usar el [protocolo emparejado](experimentos.md#comparación-de-qwen-en-el-vps). |
