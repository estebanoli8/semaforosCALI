import json
import unittest
from unittest.mock import patch
from semaforos.adapters.ollama import chat
from semaforos.inference import safe_error_code


class StreamTests(unittest.TestCase):
    def test_errors_identify_static_validation_failure_without_leaking_inputs(self):
        self.assertEqual(safe_error_code(ValueError('unbacked_quote')), 'unbacked_quote')
        self.assertEqual(safe_error_code(ValueError('citizen name and text')), 'ValueError')
        self.assertEqual(safe_error_code(RuntimeError('secret database URL')), 'RuntimeError')

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
