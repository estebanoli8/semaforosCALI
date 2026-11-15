"""Shared labels for extraction, citizen descriptions and model evaluation."""
FIELDS = {
    'dano': 'Daño',
    'gestion': 'Gestión',
    'peligro': 'Peligro',
    'ubicacion': 'Ubicación',
}

TAGS = {
    'D': ('descripcion_dano', 'dano', 'Tipo de falla'),
    'T': ('tiempo_sin_funcionar', 'dano', 'Desde cuándo está dañado'),
    'R': ('descripcion_dano', 'dano', 'Reincidencia tras reparación'),
    'G': ('afectaciones', 'gestion', 'Guarda o agente de tránsito'),
    'P': ('afectaciones', 'peligro', 'Accidente o riesgo'),
    'U': ('ubicacion', 'ubicacion', 'Ubicación'),
}
WEB_TITLE = 'Acción Popular - Cali Semáforos Dañados'
WEB_SUBTITLE = 'Procesamiento y presentación de evidencias enviadas por ciudadanos a través de WhatsApp'
