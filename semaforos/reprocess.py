"""Versioned, selective replay of source audio and WhatsApp text."""
import argparse
import json
from collections import Counter
from uuid import UUID

from .config import load_config
from .messages import chat_sources, team_audio
from .preprocess import VOICE_PROFILE
from .store import Store

EXPERIMENT = 'accion-popular-v2'


def queue_sources(store,config,*,apply=False,conversation=None):
    counts=Counter()
    with store.connect() as c:
        rows=c.execute("""
            SELECT e.id,e.modality,p.id AS video_id
            FROM evidence e LEFT JOIN evidence p ON p.id=e.parent_id AND p.modality='video'
            WHERE (e.modality='chat' AND EXISTS (SELECT 1 FROM source_texts s WHERE s.evidence_id=e.id)
                OR e.modality='audio' AND (e.parent_id IS NULL OR p.id IS NOT NULL))
              AND (%s::uuid IS NULL OR e.conversation_id=%s)
            ORDER BY e.created_at,e.id
        """,(conversation,conversation)).fetchall()
    if config['audio'].get('preprocessing')!=VOICE_PROFILE:
        raise ValueError('El reproceso requiere el perfil voice-v2')
    for row in rows:
        ident=row['id']
        if row['modality']=='chat':
            counts['chats']+=1
            if apply:
                for sources in chat_sources(store,ident,config):
                    store.enqueue(ident,'text',EXPERIMENT,config,{'sources':sources})
                    counts['tareas_de_chat']+=1
        elif not team_audio(store,ident):
            parent=row['video_id']
            counts['audios_de_video' if parent else 'audios_de_whatsapp']+=1
            if apply:
                payload={'from_video':True,'video_evidence_id':str(parent)} if parent else {}
                store.enqueue(ident,'audio',EXPERIMENT,config,payload)
        else:
            counts['audios_del_equipo_omitidos']+=1
    return {'modo':'encolado' if apply else 'estimación','experimento':EXPERIMENT,**counts}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true',help='encolar en la base configurada')
    parser.add_argument('--conversation',type=UUID,help='limitar a una conversación para una prueba piloto')
    args=parser.parse_args()
    print(json.dumps(queue_sources(Store(),load_config(),apply=args.apply,conversation=args.conversation),
                     ensure_ascii=False))


if __name__=='__main__':
    main()
