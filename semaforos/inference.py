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
    if stage=='audio':
        from .adapters.audio import transcribe
        result,identity=transcribe(path,config,os.getenv('SC_MODELS_DIR','/models'))
    elif stage=='detect':
        from .adapters.vision import detect
        result,identity=detect(path,config,out)
    elif stage=='lights':
        from .adapters.vision import read_lights
        result,identity=read_lights(path,spec['payload']['detections'],config)
    elif stage=='text':
        from .adapters.text import extract
        result,identity=extract(spec['payload']['sources'],config)
    elif stage=='video':
        from prototype.v0_3 import video
        video.MAX_SECONDS=config['max_duration_seconds']
        result=video.prepare(path,out,{'evidence_id':spec['evidence_id']})
        identity={'provider':'ffmpeg','sampling_version':video.SAMPLING_VERSION,'ffmpeg_version':result['ffmpeg_version']}
    else:raise ValueError('unsupported_stage')
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
