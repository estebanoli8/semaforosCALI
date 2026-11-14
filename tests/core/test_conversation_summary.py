import unittest

from semaforos.conversation_summary import gps_coordinates, report_context, summarize
from semaforos.worker import text_chunks


class ConversationSummaryTests(unittest.TestCase):
    def test_spoken_streets_and_duration_are_separate(self):
        context = report_context('Semáforo dañado en calle quinta con carrera ochenta y tres hace siete días.')
        self.assertEqual(context['locations'][0]['label'], 'calle 5 con carrera 83')
        self.assertEqual(context['durations'], ['siete días'])
        self.assertEqual(context['quantities'], [])
        ambiguous = report_context('Semáforo de la quinta con la ochenta.')
        self.assertFalse(ambiguous['locations'][0]['road_types_explicit'])

    def test_map_pin_precedes_viewport_and_untrusted_links_are_ignored(self):
        pins = gps_coordinates('https://www.google.com/maps/@3.411,-76.500,17z?query=3.432%2C-76.531 '
                               'GPS: 3.432,-76.531 GPS: 91.500,-76.543 '
                               'https://example.org/?q=3.433,-76.535')
        self.assertEqual([(p['latitude'], p['longitude']) for p in pins], [(3.432, -76.531)])

    def test_near_miss_and_negated_accident_are_not_counted_as_accidents(self):
        context = report_context('Casi hubo un choque. No hubo accidentes. ¿Hay guardas?')
        kinds = {(m['category'], m['qualifier']) for m in context['mentions']}
        self.assertIn(('accidente_mencionado', 'riesgo_o_casi'), kinds)
        self.assertIn(('accidente_mencionado', 'negado'), kinds)
        self.assertIn(('agentes_de_transito', 'pregunta'), kinds)
        self.assertNotIn(('accidente_mencionado', 'mencionado'), kinds)

    def test_repeated_reports_do_not_add_counts_or_mix_reporters(self):
        source = 'Dos semáforos apagados en calle quinta con carrera ochenta.'
        reports = summarize([
            {'id': 'chat', 'sender': 'Vecina', 'origin': 'chat', 'text': source},
            {'id': 'audio', 'sender': 'Vecina', 'origin': 'audio_video', 'text': source},
            {'id': 'team', 'sender': 'Esteban Oli', 'origin': 'chat', 'text': source},
            {'id': 'unknown', 'sender': None, 'origin': 'audio_whatsapp', 'text': 'Hay guardas regulando el tránsito.'},
        ])
        self.assertEqual([r['reporter'] for r in reports], ['Vecina', None])
        self.assertEqual(reports[0]['reported_estimate'], 2)
        self.assertEqual(len(reports[0]['locations']), 1)
        self.assertIsNone(reports[1]['reported_estimate'])

    def test_transcript_parts_retain_offsets(self):
        whole = 'Inciso omitido. ' + ('Texto con palabras. ' * 145)
        start = len('Inciso omitido. ')
        chunks = [part[0] for part in text_chunks(whole[start:], 'audio', 'audio_video', start)]
        self.assertGreater(len(chunks), 1)
        self.assertEqual(''.join(chunk['text'] for chunk in chunks), whole[start:])
        for chunk in chunks:
            offset = chunk['char_start']
            self.assertEqual(whole[offset:offset+len(chunk['text'])], chunk['text'])

    def test_audio_fallback_keeps_original_and_excludes_unreliable_spans(self):
        import sys
        from types import SimpleNamespace
        from unittest.mock import Mock, patch
        from semaforos.adapters.audio import transcribe

        info = SimpleNamespace(duration=10, language='es', language_probability=1)
        clear = SimpleNamespace(start=3, end=5, text=' Calle quinta con carrera ochenta.',
                                avg_logprob=-0.2, no_speech_prob=0.01, compression_ratio=1)
        noise = SimpleNamespace(start=0, end=2, text=' Repetición espuria.',
                                avg_logprob=-2, no_speech_prob=0.9, compression_ratio=3)
        model = Mock()
        model.transcribe.side_effect = [(iter([]), info), (iter([noise, clear]), info)]
        modules = {
            'huggingface_hub': SimpleNamespace(snapshot_download=Mock(return_value='/models/hf/revision')),
            'faster_whisper': SimpleNamespace(WhisperModel=Mock(return_value=model)),
        }
        with patch.dict(sys.modules, modules):
            result, _ = transcribe('audio.wav', {'repository':'synthetic', 'revision':'main',
                'compute_type':'int8','cpu_threads':2,'beam_size':5,'vad_filter':True}, '/models')
        self.assertTrue(result['alternate_pass_used'])
        self.assertTrue(result['needs_review'])
        self.assertEqual(result['text'], noise.text + clear.text)
        self.assertEqual(result['analysis_parts'], [{'text':clear.text,'offset':len(noise.text)}])
        self.assertFalse(model.transcribe.call_args.kwargs['vad_filter'])
