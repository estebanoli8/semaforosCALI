import json
import unittest
from urllib.error import HTTPError
from unittest.mock import patch
from semaforos.adapters.ollama import chat
from semaforos.inference import safe_error_code
from semaforos.adapters.text import extract, extraction_schema


class StreamTests(unittest.TestCase):
    def test_source_alias_is_resolved_and_raw_prediction_is_preserved(self):
        sources=[{'id':'uuid-real:0','text':'Quinta con quinta está apagado.'}]
        prediction={'assertions':[{'source_id':'S1','variable':'ubicacion',
            'literal':'Quinta con quinta','interpretation':None}],'summary':'Reporte'}
        with patch('semaforos.adapters.text.chat',return_value=(prediction,{'digest':'abc'},{'eval_count':10})) as model:
            result,_=extract(sources,{})
        self.assertEqual(result['extraction']['assertions'][0]['source_id'],'uuid-real:0')
        self.assertEqual(result['raw_extraction']['assertions'][0]['source_id'],'S1')
        self.assertEqual(result['normalizations'][0]['reason'],'prompt_alias')
        schema=model.call_args.kwargs['format_schema']
        self.assertEqual(schema['properties']['assertions']['items']['properties']['source_id']['enum'],['S1'])

    def test_text_schema_rejects_empty_source_catalog(self):
        with self.assertRaisesRegex(ValueError,'text_requires_sources'):extraction_schema({})

    def test_unknown_source_is_resolved_only_by_unique_exact_quote(self):
        sources=[{'id':'a','text':'Semáforo apagado.'},{'id':'b','text':'Otro mensaje.'}]
        prediction={'assertions':[{'source_id':'inventado','variable':'descripcion_dano',
            'literal':'Semáforo apagado','interpretation':None}],'summary':None}
        with patch('semaforos.adapters.text.chat',return_value=(prediction,{},{})):
            result,_=extract(sources,{})
        self.assertEqual(result['extraction']['assertions'][0]['source_id'],'a')
        self.assertEqual(result['normalizations'][0]['reason'],'unique_literal_match')

    def test_ambiguous_quote_does_not_repair_unknown_source(self):
        sources=[{'id':'a','text':'Está apagado.'},{'id':'b','text':'Está apagado.'}]
        prediction={'assertions':[{'source_id':'inventado','variable':'descripcion_dano',
            'literal':'Está apagado','interpretation':None}],'summary':None}
        with patch('semaforos.adapters.text.chat',return_value=(prediction,{},{})):
            with self.assertRaisesRegex(ValueError,'unknown_source'):extract(sources,{})

    def test_errors_identify_static_validation_failure_without_leaking_inputs(self):
        self.assertEqual(safe_error_code(ValueError('unbacked_quote')), 'unbacked_quote')
        self.assertEqual(safe_error_code(ValueError('citizen name and text')), 'ValueError')
        self.assertEqual(safe_error_code(RuntimeError('secret database URL')), 'RuntimeError')
        error = HTTPError('http://private', 503, 'sensitive response', None, None)
        self.assertEqual(safe_error_code(error), 'http_503')

    def test_preserves_original_literal_and_keeps_partial_extraction_auditable(self):
        sources = [{'id': 'chat', 'text': 'Semáforo fuera\n de servicio.'}]
        prediction = {'assertions': [
            {'source_id': 'S1', 'variable': 'descripcion_dano', 'literal': 'semáforo fuera de servicio'},
            {'source_id': 'S1', 'variable': 'tiempo_sin_funcionar', 'literal': 'desde hace 30 días'},
        ], 'summary': 'Fuera de servicio desde hace 30 días'}
        with patch('semaforos.adapters.text.chat', return_value=(prediction, {}, {})):
            result, _ = extract(sources, {})
        self.assertEqual(result['extraction'], {'assertions': [
            {'source_id': 'chat', 'variable': 'descripcion_dano', 'literal': 'Semáforo fuera\n de servicio'}
        ], 'summary': None})
        self.assertEqual(result['omitted_assertions'], [{'assertion_index': 1, 'reason': 'unbacked_quote'}])
        self.assertEqual(result['raw_extraction'], prediction)
        self.assertEqual(prediction['assertions'][0]['literal'], 'semáforo fuera de servicio')

    def test_keeps_unbacked_task_failed_when_no_claim_can_be_verified(self):
        sources = [{'id': 'chat', 'text': 'No está apagado.'}]
        prediction = {'assertions': [
            {'source_id': 'S1', 'variable': 'descripcion_dano', 'literal': 'Está fuera de servicio'},
        ]}
        with patch('semaforos.adapters.text.chat', return_value=(prediction, {}, {})):
            with self.assertRaisesRegex(ValueError, 'unbacked_quote'):
                extract(sources, {})

    def test_truncated_extraction_retries_smaller_groups_with_original_ids(self):
        sources = [{'id': 'chat-1', 'text': 'Cruce 1'}, {'id': 'chat-2', 'text': 'Cruce 2'}]
        responses = [ValueError('truncated_model_output')] + [
            ({'assertions': [{'source_id': 'S1', 'variable': 'ubicacion', 'literal': source['text']}]},
             {'model': 'test'}, {}) for source in sources
        ]
        with patch('semaforos.adapters.text.chat', side_effect=responses):
            result, _ = extract(sources, {})
        self.assertEqual([item['source_id'] for item in result['extraction']['assertions']], ['chat-1', 'chat-2'])
        self.assertEqual(result['recovery']['strategy'], 'split_sources')

    def test_partial_text_is_displayed_without_changing_final_json(self):
        class Response:
            def __init__(self):
                self.parts=iter([
                    json.dumps({'message':{'content':'{"assertions":'}}).encode()+b'\n',
                    json.dumps({'message':{'content':'[],"summary":null}'}}).encode()+b'\n',
                    json.dumps({'done':True,'done_reason':'stop','eval_count':12}).encode()+b'\n'])
            def readline(self, size):return next(self.parts,b'')
            def __enter__(self):return self
            def __exit__(self,*args):pass
        seen=[]
        config={'model':'synthetic','context':100,'max_tokens':60,'threads':2}
        with patch('semaforos.adapters.ollama.identity',return_value={'digest':'abc'}),\
             patch('semaforos.adapters.ollama.urlopen',return_value=Response()) as url,\
             patch.dict('os.environ',{'OLLAMA_URL':'http://127.0.0.1:11434'}):
            output,_,metrics=chat(config,[{'role':'user','content':'Sintético'}],seen.append)
        self.assertEqual(output,{'assertions':[],'summary':None})
        self.assertEqual(seen[-1],'{"assertions":[],"summary":null}')
        self.assertEqual(metrics['eval_count'],12)
        self.assertTrue(json.loads(url.call_args[0][0].data)['stream'])
        self.assertEqual(json.loads(url.call_args[0][0].data)['keep_alive'],0)

    def test_model_keeps_its_configured_cache_duration(self):
        class Response:
            def read(self, size):return json.dumps({'done':True,'message':{'content':'{}'}}).encode()
            def __enter__(self):return self
            def __exit__(self,*args):pass
        config={'model':'synthetic','context':100,'max_tokens':60,'threads':2,'keep_alive':'2m'}
        with patch('semaforos.adapters.ollama.identity',return_value={'digest':'abc'}),\
             patch('semaforos.adapters.ollama.urlopen',return_value=Response()) as url,\
             patch.dict('os.environ',{'OLLAMA_URL':'http://127.0.0.1:11434'}):
            chat(config,[{'role':'user','content':'imagen sintética'}])
        self.assertEqual(json.loads(url.call_args[0][0].data)['keep_alive'],'2m')

    def test_incomplete_stream_is_rejected(self):
        class Response:
            def readline(self, size):return b''
            def __enter__(self):return self
            def __exit__(self,*args):pass
        with patch('semaforos.adapters.ollama.urlopen',return_value=Response()),\
             patch.dict('os.environ',{'OLLAMA_URL':'http://127.0.0.1:11434'}):
            with self.assertRaisesRegex(ValueError,'incomplete_model_output'):
                from semaforos.adapters.ollama import stream_chat
                stream_chat({},lambda _:None)


if __name__=='__main__':unittest.main()
