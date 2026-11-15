"""Public content is generated from approved field types, not raw conversation text."""
import unittest
from datetime import datetime, timezone
from uuid import uuid4

from semaforos.public_results import make_item, source_features


class PublicResultsTests(unittest.TestCase):
    def test_no_contact_link_or_transcript_appears_in_result(self):
        source={'text':'Soy Martina. Mi teléfono es 3001234567. Apagado hace dos días, '
                'Carrera 70 con Calle 5. Me da miedo el cruce. https://example.test/call',
                'origin':'chat','sent_at':datetime(2026,11,14,tzinfo=timezone.utc)}
        features=source_features(source,{'descripcion_dano','afectaciones'})
        self.assertEqual(features['locations'],{'calle 5 con carrera 70'})
        result=make_item(uuid4(),'Martina',source['sent_at'].date(),'calle 5 con carrera 70',
                         [(source,features)],{'running':False,'pending':False,'errors':False,'images':0},
                         points_allowed=False)
        self.assertTrue(result['preliminary'])
        self.assertIn('dos dias',result['description'])
        self.assertIn('Miedo expresado',result['description'])
        for private in ('Martina','3001234567','example.test','Me da miedo el cruce'):
            self.assertNotIn(private,str(result))

    def test_only_explicit_intersection_coordinates_are_eligible(self):
        examples=[
            ('Calle 5 con Carrera 70. GPS: 3.430, -76.530',None),
            ('GPS del semáforo: 3.430, -76.530',None),
            ('Calle 5 con Carrera 70. GPS del semáforo: 3.430, -76.530',(3.43,-76.53)),
        ]
        for text,point in examples:
            with self.subTest(text=text):
                self.assertEqual(source_features({'text':text},set())['point'],point)
