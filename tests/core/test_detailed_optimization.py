import unittest
from unittest.mock import patch

from semaforos.adapters.compact_text import extract_compact
from semaforos.detailed import compose, location_values
from semaforos.quality_metrics import summarize_reviews
from semaforos.whatsapp import compact_sources, format_health, parse_chat


class DetailedOptimizationTests(unittest.TestCase):
    def test_cali_ordinal_pair_is_kept_as_a_short_location(self):
        self.assertEqual(location_values('Quinta con 5, apagado'),
                         [('Calle 5 con Carrera 5','por_confirmar')])

    def test_alerts_preserve_unknown_header_with_no_inherited_sender(self):
        text='[15/11/26, 10:00] Equipo: Hola\n15/11/26 10.05 | Persona | Falla desde ayer\nContinuación.'
        parsed=parse_chat(text)
        self.assertEqual(parsed[1]['kind'],'unparsed')
        self.assertIsNone(parsed[1]['sender_visible'])
        status=format_health(text,parsed)
        self.assertEqual(status['severity'],'degraded')
        self.assertEqual(status['probable_headers'],2)
        self.assertEqual(status['unreadable_fraction'],.5)
        alternative='15/11/26 10:05 - Persona: Una referencia\nSegunda línea.'
        self.assertEqual(format_health(alternative,parse_chat(alternative))['severity'],'ok')

    def test_compact_input_preserves_literal_offsets_with_partial_attachment(self):
        text=('[15/11/26, 10:00] Ciudadana: Messages and calls are end-to-end encrypted. '
              'Only people in this chat can read, listen to, or share them.\r\n'
              '[15/11/26, 10:02] Ciudadana: Desde ayer <attached: test.mp4> sigue dañado.\r\n')
        rows=[dict(row,id=str(i),evidence_id='synthetic') for i,row in enumerate(parse_chat(text))]
        chunks=list(compact_sources(rows))
        self.assertEqual([[s['text'] for s in batch] for batch in chunks],[['Desde ayer','sigue dañado.']])
        for source in chunks[0]:
            self.assertEqual(text[source['char_start']:source['char_start']+len(source['text'])],source['text'])

    def test_model_and_projection_keep_recurrence_under_damage_and_merge_sources(self):
        sources=[{'id':'a','text':'Calle 16 con carrera 84.','origin':'chat'},
                 {'id':'b','text':'Lo arreglaron, volvió a fallar. Desde hace dos días está dañado.','origin':'chat'}]
        prediction={'hits':[{'k':'U','s':'S1','u':'S1'},{'k':'R','s':'S2','u':'S1'},{'k':'T','s':'S3','u':'S1'}]}
        with patch('semaforos.adapters.compact_text.chat',return_value=(prediction,{'digest':'x'},{'eval_count':15})) as request:
            output,_=extract_compact(sources,{'threads':4,'chat_threads':6})
        self.assertEqual(request.call_args.args[0]['threads'],6)
        self.assertEqual(output['ollama_calls'][0]['eval_count'],15)
        audio={'id':'v','origin':'audio_video','text':'Un motociclista casi choca en calle 16 con carrera 84.'}
        video_out={'extraction':{'assertions':[{'source_id':'v','variable':'afectaciones','field_code':'P','literal':audio['text']}]}}
        combined=compose([{'job_id':'a','evidence_id':'a','payload':{'sources':sources},'output':output},
                          {'job_id':'b','evidence_id':'v','payload':{'sources':[audio]},'output':video_out}])
        self.assertEqual(len(combined),1)
        self.assertEqual({x['code'] for x in combined[0]['fields']['dano']},{'R','T'})
        self.assertEqual(combined[0]['fields']['gestion'],[])
        self.assertEqual(combined[0]['fields']['peligro'][0]['origin'],'audio_video')

    def test_detailed_claim_retains_clickable_coordinate_provenance(self):
        url='https://maps.google.com/?q=3.472345,-76.511703'
        source={'id':'a','text':'Calle 18 con carrera 15. '+url,'origin':'chat'}
        episodes=compose([{'job_id':'x','evidence_id':'a','payload':{'sources':[source]},'output':{'assertions':[]}}])
        location=episodes[0]['fields']['ubicacion'][0]
        self.assertEqual(location['literal'],source['text'])
        self.assertEqual(location['gps'],[{'literal':url,'latitude':3.472345,'longitude':-76.511703}])

    def test_asr_outros_do_not_become_reported_locations(self):
        for credit in ('Subtítulos realizados por la comunidad de Amara.org',
                       'Subtítulos por la comunidad de Amara.org','¡Suscríbete!'):
            source={'id':'a','text':credit,'origin':'audio_video'}
            assertion={'source_id':'a','variable':'ubicacion','field_code':'U','literal':credit}
            episodes=compose([{'job_id':'x','evidence_id':'a','payload':{'sources':[source]},
                               'output':{'assertions':[assertion]}}])
            self.assertIsNone(episodes[0]['location'])
            self.assertFalse(episodes[0]['inferred_fault'])

    def test_location_heading_never_falls_back_to_a_long_quote(self):
        literal=('Este semáforo está dañado y todos andan de afán, los peatones, '
                 'las motos y las bicicletas eléctricas corren peligro.')
        source={'id':'a','text':literal,'origin':'audio_video'}
        assertion={'source_id':'a','variable':'ubicacion','field_code':'U','literal':literal}
        episodes=compose([{'job_id':'x','evidence_id':'a','payload':{'sources':[source]},
                           'output':{'assertions':[assertion]}}])
        self.assertEqual(len(episodes),1)
        self.assertIsNone(episodes[0]['location'])
        self.assertEqual(episodes[0]['fields']['ubicacion'][0]['literal'],literal)

    def test_pilot_references_are_short_location_headings(self):
        cases={
            'Buenas, para reportar semáforo malo en Guadalupe, lleva demasiado rato.':'Guadalupe',
            'Vivo en Puertas del Sol, sector 1, en la Comuna 14.':'Puertas del Sol, sector 1',
            'Esto es al frente del Coliseo de María Isabel Urrutia.':'Coliseo María Isabel Urrutia',
            'Barrio Atanasio Girardot comuna 8.':'barrio Atanasio Girardot, comuna 8',
        }
        for literal,expected in cases.items():
            source={'id':'a','text':literal,'origin':'chat'}
            assertion={'source_id':'a','variable':'ubicacion','field_code':'U','literal':literal}
            episodes=compose([{'job_id':'x','evidence_id':'a','payload':{'sources':[source]},
                               'output':{'assertions':[assertion]}}])
            self.assertIn(expected,{episode['location'] for episode in episodes})

    def test_inferred_fault_is_explicit_and_field_scores_only_use_saved_labels(self):
        source={'id':'a','text':'5 x 5','origin':'chat'}
        episodes=compose([{'job_id':'x','evidence_id':'a','payload':{'sources':[source]},'output':{'assertions':[]}}])
        self.assertTrue(episodes[0]['inferred_fault'])
        self.assertEqual(episodes[0]['fields']['dano'],[])
        metrics=summarize_reviews([{'stage':'text','human_label':{'gestion':{'observed':True,'detected':False}}},
                                   {'stage':'detect','human_label':{'observed':0,'detected':0}}])
        self.assertEqual(metrics['text']['macro_f1'],0)
        self.assertEqual(metrics['text']['fields']['dano']['samples'],0)
        self.assertIsNone(metrics['audio']['macro_f1'])
        self.assertEqual(metrics['detect']['exact_rate'],1)
