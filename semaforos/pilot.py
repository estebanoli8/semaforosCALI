"""Choose five distinct conversations that cover the relevant WhatsApp sources."""
from .detailed import read_conversations
from .messages import is_team_message

CASES = ('gps', 'audio_whatsapp', 'audio_video', 'multiples_cruces', 'remitente_operador')


def select_five(db, experiment):
    previous = db.execute("""
        SELECT DISTINCT e.conversation_id,j.payload->>'pilot_case' AS caso
        FROM jobs j JOIN evidence e ON e.id=j.evidence_id
        WHERE j.experiment_id=%s AND j.payload ? 'pilot_case'
        ORDER BY caso,e.conversation_id
    """,(experiment,)).fetchall()
    if previous:
        covered={row['caso'] for row in previous}
        return previous,[case for case in CASES if case not in covered]
    rows, _ = read_conversations(db, include_evidence=True)
    transcripts = {row['evidence_id'] for row in db.execute("""
        SELECT DISTINCT t.evidence_id FROM transcripts t JOIN runs r ON r.id=t.run_id
        WHERE r.state='completed' AND NOT (r.output ? 'excluded')
          AND length(btrim(t.literal_text))>0
    """)}
    team, team_with_audio = set(), set()
    for row in db.execute("""
        WITH latest AS (
          SELECT DISTINCT ON (evidence_id) id, evidence_id FROM chat_parses
          ORDER BY evidence_id, created_at DESC, id DESC
        )
        SELECT e.conversation_id,m.sender_visible,split_part(m.raw_text,chr(10),1) AS header,
               EXISTS(SELECT 1 FROM message_attachments a JOIN evidence media ON media.id=a.evidence_id
                      WHERE a.message_id=m.id AND a.state='linked'
                        AND media.modality IN ('audio','video')) AS has_media
        FROM latest p JOIN messages m ON m.parse_id=p.id JOIN evidence e ON e.id=p.evidence_id
    """):
        if is_team_message(row['sender_visible'],row['header']):
            team.add(row['conversation_id'])
            if row['has_media']:
                team_with_audio.add(row['conversation_id'])

    cases = {key: [] for key in CASES}
    eligible = []
    for row in rows:
        cid = row['id']
        audio_types = {item['type'] for item in row['evidence'] if item['id'] in transcripts}
        episodes = row['episodes']
        has_findings = any(ep['fields'][field] for ep in episodes for field in ep['fields'])
        if row['analysis_state']!='completed' or not (audio_types or has_findings):
            continue
        eligible.append(cid)
        features = {
            'gps': any(hit.get('gps') for ep in episodes for fields in ep['fields'].values() for hit in fields),
            'audio_whatsapp': 'audio' in audio_types,
            'audio_video': 'audio_video' in audio_types,
            'multiples_cruces': len({ep['location'] for ep in episodes if ep['location']})>1,
            'remitente_operador': cid in team,
        }
        for key, present in features.items():
            if present:
                cases[key].append(cid)
    cases['remitente_operador'].sort(key=lambda cid: cid not in team_with_audio)

    # A conversation can match several cases. Reassign earlier cases when needed.
    owners = {}

    def reserve(key, seen):
        for cid in cases[key]:
            if cid in seen:
                continue
            seen.add(cid)
            if cid not in owners or reserve(owners[cid],seen):
                owners[cid]=key
                return True
        return False

    for key in sorted(cases,key=lambda key:len(cases[key])):
        reserve(key,set())
    selected = {key:cid for cid,key in owners.items()}
    result = [{'caso':key,'conversation_id':selected[key]} for key in cases if key in selected]
    missing = [key for key in cases if key not in selected]
    fallback = (cid for cid in eligible if cid not in owners)
    result.extend({'caso':'contraste','conversation_id':cid} for _,cid in zip(missing,fallback))
    return result, missing
