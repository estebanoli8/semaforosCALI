import unittest
from semaforos.contracts import assertions, boxes, lights
from semaforos.evaluation import wer,detection_metrics,light_metrics
from semaforos.worker import text_chunks


class ContractTests(unittest.TestCase):
    def test_dark_unknown_and_multiple_lights_are_different(self):
        self.assertEqual(lights({'red':False,'yellow':False,'green':False})['reading_state'],'ninguna_visible')
        self.assertEqual(lights({'red':False,'yellow':None,'green':False})['reading_state'],'indeterminado')
        self.assertEqual(lights({'red':True,'yellow':None,'green':True})['reading_state'],'alguna_visible')
        with self.assertRaises(ValueError):lights({'red':'false'})

    def test_reject_unbacked_quote_or_invented_source(self):
        source={'m1':'Casi se chocan dos motos en quinta con quinta.'}
        good={'assertions':[{'source_id':'m1','variable':'afectaciones','literal':'Casi se chocan dos motos'}]}
        self.assertEqual(assertions(good,source),good)
        bad={'assertions':[{'source_id':'m1','variable':'afectaciones','literal':'Se chocaron dos motos'}]}
        with self.assertRaises(ValueError):assertions(bad,source)
        bad['assertions'][0]['source_id']='inventado'
        with self.assertRaises(ValueError):assertions(bad,source)

    def test_bbox_bounds(self):
        with self.assertRaises(ValueError):boxes([{'bbox':[0,0,101,50],'score':.8}],100,100)
        self.assertEqual(len(boxes([{'bbox':[0,0,100,100],'score':.8}],100,100)),1)

    def test_chunking_preserves_every_character(self):
        original=('Desde hace días: áéí 🙂\n'*1000)
        chunks=list(text_chunks(original,'evidence','audio_whatsapp'))
        self.assertEqual(''.join(c[0]['text'] for c in chunks),original)
        self.assertEqual(len({c[0]['id'] for c in chunks}),len(chunks))

    def test_metrics_distinguish_absent_labels_from_zero_error(self):
        self.assertIsNone(wer('','hola')['wer'])
        self.assertEqual(wer('semáforo rojo','semáforo verde')['wer'],.5)
        self.assertEqual(detection_metrics([{'bbox':[0,0,10,10],'score':.9}],[[0,0,10,10]])['recall'],1)
        self.assertEqual(light_metrics({'red':True,'yellow':None,'green':None},{'red':True,'yellow':False,'green':False})['coverage'],1/3)
