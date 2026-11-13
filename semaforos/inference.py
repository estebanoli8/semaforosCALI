"""Un proceso corto por inferencia libera RAM al terminar, incluso si el modelo falla."""
import importlib.metadata
import json
import os
from pathlib import Path
import resource
import sys
import time
from .files import atomic_json, contained, sha256


def execute(spec):
    root=Path(spec['storage']);path=contained(root,spec['path'])
    if sha256(path)!=spec['sha256']:raise ValueError('input_checksum_mismatch')
    out=contained(root,spec['output_dir']);out.mkdir(parents=True,exist_ok=True)
    stage=spec['stage'];config=spec['config'][stage]
    started=time.perf_counter();cpu=time.process_time()
    progress_file=out.parent/'progress.json';last=[0.0]
    def progress(**fields):
        now=time.monotonic()
        if now-last[0]<0.5 and fields.get('phase')==progress_state.get('phase'):return
        progress_state.update(fields)
        progress_state['updated_at_unix']=time.time()
        atomic_json(progress_file,progress_state)
        last[0]=now
    progress_state={'stage':stage,'phase':'Iniciando'}
    progress(phase='Iniciando')
    if stage=='audio':
        from .adapters.audio import transcribe
        result,identity=transcribe(path,config,os.getenv('SC_MODELS_DIR','/models'),on_progress=progress)
    elif stage=='detect':
        from .adapters.vision import detect
        progress(phase='Analizando imagen')
        result,identity=detect(path,config,out)
    elif stage=='lights':
        from .adapters.vision import read_lights
        result,identity=read_lights(path,spec['payload']['detections'],config)
    elif stage=='text':
        from .adapters.text import extract
        progress(phase='Generando JSON')
        result,identity=extract(spec['payload']['sources'],config,
                                on_partial=lambda content:progress(phase='Generando JSON',preview=content[-2500:],characters=len(content)))
    elif stage=='video':
        from prototype.v0_3 import video
        video.MAX_SECONDS=config['max_duration_seconds']
        progress(phase='Extrayendo fotogramas y audio')
        result=video.prepare(path,out,{'evidence_id':spec['evidence_id']})
        identity={'provider':'ffmpeg','sampling_version':video.SAMPLING_VERSION,'ffmpeg_version':result['ffmpeg_version']}
    else:raise ValueError('unsupported_stage')
    progress(phase='Guardando resultados',fraction=1.0)
    libraries={}
    for name in ('faster-whisper','ctranslate2','ultralytics','torch','Pillow'):
        try:libraries[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    return {'result':result,'model_identity':identity,'metrics':{
        'wall_seconds':time.perf_counter()-started,'cpu_seconds':time.process_time()-cpu,
        'peak_rss_bytes':resource.getrusage(resource.RUSAGE_SELF).ru_maxrss*(1024 if sys.platform!='darwin' else 1),
        'scope':'isolated_python_process_excludes_ollama_and_ffmpeg_children','libraries':libraries}}


if __name__=='__main__':
    spec=json.loads(Path(sys.argv[1]).read_text())
    try:
        atomic_json(sys.argv[2],execute(spec))
    except Exception as exc:
        # Mensajes de terceros pueden incluir rutas, fuentes o credenciales: solo tipo público.
        atomic_json(sys.argv[2],{'error_code':type(exc).__name__})
        raise SystemExit(1)
