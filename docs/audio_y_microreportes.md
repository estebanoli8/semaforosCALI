# Audio y microreportes por conversación

Desplegar `semaforos-core` desde `main` con `SC_PROCESS=all` y `SC_PARALLEL=1`.
La migración 006 retira los trabajos activos de lectura visual de luces. Las imágenes
y fotogramas se procesan con el detector y se muestran con cajas.

Whisper local usa vocabulario vial, ventanas independientes y un segundo intento
sin filtro de voz cuando la primera transcripción queda vacía o tiene baja confianza.
Esto puede tomar más tiempo en audios difíciles. El texto original del modelo queda
disponible para cotejo, con una advertencia cuando requiere revisión. El análisis
automático utiliza los pasajes que superan los controles de calidad o la corrección
humana. El WAV mono de video se reutiliza.

En **Procesamiento y resultados de los modelos**, abre la conversación. El
microreporte agrupa los mensajes por remitente y atribuye un audio o un video
solo cuando el chat contiene un vínculo explícito. Los demás audios aparecen
bajo **Remitente sin identificar**. Reconoce coordenadas escritas con etiqueta y
en enlaces compatibles que contienen el pin. Enlaces abreviados o que solo
contienen el centro del mapa requieren revisión manual. No se infiere GPS a partir
de una dirección ni se envía evidencia a servicios de geocodificación.

La cantidad es una estimación conservadora por relato basada en cantidades
explícitas o cruces distintos, sin sumar cajas ni repetir la misma ubicación.
Los temas se muestran con citas. El conteo estadístico registra un tema una vez
por reportante y conversación. Reportes de personas distintas pueden corresponder
al mismo cruce. Los datos son preliminares y requieren cotejo, especialmente
negaciones, ambigüedad, cambios de tema y números en audios con ruido.

En **Estadísticas base de reportes → Calcular estadísticas**, consulta el corte de
los chats y transcripciones procesados hasta ese momento. Para verificar una
noche de procesamiento, revisa cargas recibidas, tareas fallidas y espacio libre.
La pestaña debe seguir abierta hasta completar la transferencia de los ZIP.
Para repetir un lote ya procesado con el perfil nuevo, usa otro nombre de
experimento, por ejemplo `audio-contexto-v2`.
