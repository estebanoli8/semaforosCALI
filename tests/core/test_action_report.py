import unittest
from datetime import datetime, timedelta, timezone

from semaforos.cali import locations
from semaforos.conversation_summary import report_context
from semaforos.public_results import source_features
from semaforos.situation import synthesize
from semaforos.source_detail import media_location, result_for


class ActionReportTests(unittest.TestCase):
    def test_cali_crossings_and_literal_source(self):
        for literal, expected in (
            ('Cra12 calle 22', {'calle 22 con carrera 12'}),
            ('la quinta con la 44', {'calle 5 con carrera 44'}),
            ('Rosbelt con treinta y nueve', {'avenida Roosevelt con carrera 39'}),
            ('CalLe 29 con carrera 10, carrera 28 y carrera 12', {
                'calle 29 con carrera 10', 'calle 29 con carrera 12','calle 29 con carrera 28'}),
            ('Av. Circunvalar con cll 12', {'avenida Circunvalar con calle 12'}),
        ):
            with self.subTest(literal=literal):
                self.assertEqual({x['label'] for x in locations(literal) if x['intersection']}, expected)
                self.assertIn(locations(literal)[0]['literal'], literal)
        self.assertEqual(locations('Vivo en la ciudad de Cali. El cruce es 20 con 30.'), [])
        self.assertEqual(len(report_context('GPS sintético\n3.451234, -76.551234')['gps']), 1)

    def test_reported_situation_distinguishes_danger_from_accident(self):
        features=source_features({'text':('El semáforo no funciona desde ayer en calle 19 con carrera 42. '
            'Casi hubo un choque. Unos muchachos dirigen el tráfico y hay trancón. No hay guardas.')}, set())
        value=synthesize('calle 19 con carrera 42',features['topics'],features['fault_types'],features['durations'])
        for phrase in ('desde ayer','casi accidente','particulares','congestión'):
            self.assertIn(phrase,value)
        self.assertNotIn('guardas',value)
        self.assertNotIn('accidentes o choques',value)

    def test_attachment_uses_unique_nearby_same_sender_or_own_audio(self):
        def message(text, ordinal, sender='Ciudadana'):
            return {'body_text':text,'ordinal':ordinal,'evidence_id':'synthetic','sender_visible':sender,
                    'sent_at':datetime(2026,1,1,tzinfo=timezone.utc)+timedelta(seconds=ordinal*10)}
        attachment=message('Video',2)
        address=message('Pasoancho con 42',3)
        other_sender=message('calle 18 con carrera 25',4,'Otro')
        self.assertEqual(media_location(attachment,[attachment,address,other_sender],None)[0],
                         'avenida Pasoancho con carrera 42')
        before=message('calle 12 con carrera 70',1)
        self.assertIsNone(media_location(attachment,[before,attachment,address],None)[0])
        self.assertEqual(media_location(attachment,[before,attachment,address],'calle 22 con carrera 66')[2],
                         'audio vinculado')

    def test_unsaved_and_negative_location_review_are_distinct(self):
        run={'state':'completed','output':{'text':'la calle'},'error_code':None,'literal_text':'la calle',
             'run_id':'test','human_label':False}
        self.assertFalse(result_for([run],'audio')['review'])
        self.assertIsNone(result_for([dict(run,human_label=None)],'audio')['review'])
