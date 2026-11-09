import json
import unittest
from semaforos.whatsapp import parse_chat, message_chunks


class WhatsAppTests(unittest.TestCase):
    def test_ios_unicode_span_and_colombian_timezone(self):
        text='\u200e[01/11/26, 10:00:00] \u2068@vecina\u2069: Quinta con quinta.\r\nSigue apagado.\r\n[01/11/26, 10:01:02] Otro: Gracias\r\n'
        rows=parse_chat(text)
        self.assertEqual(len(rows),2)
        self.assertEqual(''.join(r['raw_text'] for r in rows),text)
        for r in rows:self.assertEqual(text[r['char_start']:r['char_end']],r['raw_text'])
        self.assertEqual(rows[0]['sender_visible'],'\u2068@vecina\u2069')
        self.assertEqual(rows[0]['body_text'],'Quinta con quinta.\r\nSigue apagado.\r\n')
        self.assertEqual(rows[0]['sent_at'],'2026-11-01T15:00:00+00:00')
        self.assertTrue(rows[0]['timezone_assumed']);self.assertTrue(rows[0]['century_assumed'])

    def test_android_spanish_am_pm_system_and_colons(self):
        text='1/11/2026, 12:01 a.\u202fm. - Mensajes cifrados\n1/11/2026, 12:30 p. m. - Vecina: Ubicación: quinta con 5\n'
        rows=parse_chat(text)
        self.assertEqual(rows[0]['kind'],'system');self.assertEqual(rows[0]['sent_at'],'2026-11-01T05:01:00+00:00')
        self.assertEqual(rows[1]['body_text'],'Ubicación: quinta con 5\n')
        self.assertEqual(rows[1]['sent_at'],'2026-11-01T17:30:00+00:00')

    def test_ambiguous_dates_remain_unresolved_in_auto(self):
        rows=parse_chat('[03/04/26, 10:00] A: Test\n',{'date_order':'AUTO'})
        self.assertIsNone(rows[0]['sent_at']);self.assertEqual(rows[0]['timestamp_status'],'ambiguous_date')
        self.assertEqual(parse_chat('[13/04/26, 10:00] A: Test',{'date_order':'AUTO'})[0]['sent_at'],'2026-04-13T15:00:00+00:00')
        self.assertEqual(parse_chat('[04/13/26, 10:00] A: Test',{'date_order':'AUTO'})[0]['sent_at'],'2026-04-13T15:00:00+00:00')

    def test_invalid_dates_and_missing_headers_preserved(self):
        rows=parse_chat('Preambulo\n[31/02/2026, 10:00] A: imposible\n[01/11/26, 25:00] A: hora inválida\n')
        self.assertEqual(rows[0]['kind'],'unparsed')
        self.assertEqual([r['timestamp_status'] for r in rows[1:]],['invalid_datetime']*2)
        self.assertTrue(all(r['sent_at'] is None for r in rows))

    def test_attachment_names_only_explicit_not_omitted_or_guessed(self):
        text='[1/11/26, 10:00] A: <attached: imagen.jpg>\n<adjunto: audio.opus>\nvideo.mp4 (archivo adjunto)\nfoto omitida\n'
        row=parse_chat(text)[0]
        self.assertEqual(row['attachment_names'],['imagen.jpg','audio.opus','video.mp4'])
        self.assertIn('<attached: imagen.jpg>',row['raw_text'])

    def test_chunking_retains_message_ids_and_all_literal_characters(self):
        text='[01/11/26, 10:00] A: '+('é "\n'*1300)+'\n[01/11/26, 11:00] B: segundo\n'
        records=parse_chat(text)
        for i,r in enumerate(records):r.update(id=f'm{i}',evidence_id='e0')
        batches=list(message_chunks(records));flat=[s for batch in batches for s in batch]
        self.assertTrue(all(len(json.dumps(b,ensure_ascii=False))<6000 for b in batches))
        self.assertEqual(''.join(s['text'] for s in flat),text)
        self.assertEqual({s['message_id'] for s in flat},{'m0','m1'})
        for s in flat:self.assertEqual(text[s['char_start']:s['char_start']+len(s['text'])],s['text'])

    def test_iso_dates_and_no_training_or_inferred_duration(self):
        row=parse_chat('[2026-11-01, 10:30] A: Lleva tres días apagado.')[0]
        self.assertEqual(row['sent_at'],'2026-11-01T15:30:00+00:00')
        self.assertEqual(row['date_order_used'],'YMD')
        self.assertEqual(row['body_text'],'Lleva tres días apagado.')

    def test_unknown_text_can_still_be_analyzed_without_a_date(self):
        rows=parse_chat('Semáforo apagado, no hay cabecera.')
        rows[0].update(id='unknown',evidence_id='e0')
        source=list(message_chunks(rows))[0][0]
        self.assertIsNone(source['sent_at']);self.assertEqual(source['timestamp_status'],'unparsed')


if __name__=='__main__':unittest.main()
