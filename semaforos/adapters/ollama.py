import json
import os
from urllib.request import Request, urlopen


def request(path, data=None):
    base=os.environ['OLLAMA_URL'].rstrip('/')
    if not base.startswith(('http://','https://')):raise ValueError('invalid_ollama_url')
    req=Request(base+path,data=None if data is None else json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urlopen(req,timeout=1800) as response:
        raw=response.read(16*1024**2+1)
        if len(raw)>16*1024**2:raise ValueError('model_response_too_large')
        return json.loads(raw)


def identity(config):
    found=next((x for x in request('/api/tags')['models'] if x['name']==config['model']),None)
    if found is None:raise ValueError('model_not_installed')
    expected=config.get('expected_digest')
    if expected and found['digest']!=expected:raise ValueError('model_digest_mismatch')
    return {'provider':'ollama_local','model':config['model'],'digest':found['digest']}


def chat(config, messages):
    model_id=identity(config)
    result=request('/api/chat',{'model':config['model'],'messages':messages,'stream':False,'think':False,
        'format':'json','keep_alive':0,'options':{'temperature':0,'num_ctx':config['context'],'num_predict':config['max_tokens'],'num_thread':config['threads']}})
    if result.get('done_reason')=='length':raise ValueError('truncated_model_output')
    if not result.get('done',False):raise ValueError('incomplete_model_output')
    # Evitar aceptar una respuesta si cambiaron el tag durante la inferencia.
    if identity(config)['digest']!=model_id['digest']:raise ValueError('model_changed_during_run')
    content=json.loads(result['message']['content'])
    return content, model_id, {k:result.get(k) for k in ('total_duration','load_duration','prompt_eval_count','prompt_eval_duration','eval_count','eval_duration')}
