"""Derivados de video, sin inferencia. FFmpeg/ffprobe son las únicas dependencias."""
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import time

SAMPLING_VERSION = 'segundos-v1'
VIDEO_SUFFIXES = {'.mp4', '.mov', '.m4v', '.avi', '.webm', '.mkv', '.3gp'}
MAX_SECONDS = 600

def atomic_json(path, value):
    temp = path.with_suffix('.json.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)

def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()

def run(args, timeout=180):
    proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          timeout=timeout, check=False)
    if proc.returncode:
        raise ValueError('FFmpeg/ffprobe: ' + proc.stderr.decode(errors='replace')[-1200:])
    return proc.stdout

def select_frames(frames, duration):
    """Un objeto por intervalo [s,s+1). Iniciales prevalecen sobre finales."""
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError(f'Duración no admitida; máximo {MAX_SECONDS} segundos')
    count = math.ceil(duration - 1e-7)
    initial = set(range(min(10, count)))
    tail = set(range(max(0, count - 5), count)) if count > 10 else set()
    picked = {}
    origin = None
    for index, frame in enumerate(frames):
        value = frame.get('best_effort_timestamp_time')
        if value is None:
            continue
        stamp = float(value)
        if not math.isfinite(stamp):
            continue
        if origin is None:
            origin = stamp
        t = stamp - origin
        if t < -1e-7 or t >= duration:
            continue
        bucket = math.floor(t + 1e-7)
        if bucket not in initial | tail:
            continue
        rule = 'ultimo_inicial' if bucket in initial else 'primero_final'
        if bucket not in picked or rule == 'ultimo_inicial':
            picked[bucket] = dict(indice_frame=index, tiempo_segundos=round(t, 7),
                                  pts_original_segundos=stamp, segundo=bucket + 1,
                                  regla=rule)
    if not picked:
        raise ValueError('No se encontraron fotogramas con tiempos válidos')
    return sorted(picked.values(), key=lambda x: x['indice_frame'])

def prepare(source, output, source_info):
    """Conserva manifest y reutiliza derivados íntegros después de reiniciar."""
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise ValueError('Faltan ffmpeg/ffprobe en el contenedor')
    digest = sha256(source)
    target = output / digest
    target.mkdir(parents=True, exist_ok=True)
    manifest_path = target / 'manifest.json'
    if manifest_path.exists():
        cached = json.loads(manifest_path.read_text())
        files = cached.get('fotogramas', []) + ([cached['audio']] if cached.get('audio') else [])
        if cached.get('muestreo_version') == SAMPLING_VERSION and files and all(
                (target / f['archivo']).is_file() and sha256(target / f['archivo']) == f['sha256'] for f in files):
            return dict(cached, fuente=source_info)
    started = time.time()
    metadata = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-show_format',
                               '-of', 'json', str(source)]))
    streams = metadata.get('streams', [])
    video = next((s for s in streams if s.get('codec_type') == 'video'
                  and not s.get('disposition', {}).get('attached_pic')), None)
    if video is None:
        raise ValueError('El archivo no contiene pista de video')
    duration = float(video.get('duration') or metadata.get('format', {}).get('duration') or 0)
    if not math.isfinite(duration) or not 0 < duration <= MAX_SECONDS:
        raise ValueError(f'Duración no admitida; máximo {MAX_SECONDS} segundos')
    if shutil.disk_usage(target).free < 512 * 1024**2:
        raise ValueError('Se necesitan al menos 512 MiB libres para preparar video')
    frames = json.loads(run(['ffprobe', '-v', 'error', '-select_streams', str(video['index']),
        '-show_frames', '-show_entries', 'frame=best_effort_timestamp_time', '-of', 'json',
        str(source)], timeout=300)).get('frames', [])
    selected = select_frames(frames, duration)
    expression = '+'.join(f'eq(n\\,{r["indice_frame"]})' for r in selected)
    # Un solo recorrido del video; ningún seek aproximado por keyframe.
    run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-threads', '1', '-i', str(source),
         '-map', f'0:{video["index"]}', '-vf', f'select={expression},scale=1280:1280:force_original_aspect_ratio=decrease',
         '-vsync', '0', '-frames:v', str(len(selected)), '-threads', '1', '-q:v', '3',
         str(target / 'frame-%02d.jpg')], timeout=300)
    for number, row in enumerate(selected, 1):
        frame_path = target / f'frame-{number:02d}.jpg'
        if not frame_path.exists():
            raise ValueError('Falta un fotograma seleccionado')
        row.update(archivo=frame_path.name, sha256=sha256(frame_path), analisis='pendiente_mlfoto')
    audio_streams = sorted(
        (stream for stream in streams if stream.get('codec_type') == 'audio'),
        key=lambda stream: not stream.get('disposition', {}).get('default'),
    )
    audio = None
    audio_state = 'sin_pista_audio'
    for stream in audio_streams:
        audio_path = target / 'audio.wav'
        try:
            run(['ffmpeg', '-nostdin', '-v', 'error', '-y', '-threads', '1', '-i', str(source),
                 '-map', f'0:{stream["index"]}', '-vn', '-ac', '1', '-ar', '16000',
                 '-c:a', 'pcm_s16le', str(audio_path)], timeout=300)
            if audio_path.stat().st_size <= 78:
                raise ValueError('Audio vacío')
        except (ValueError, OSError, subprocess.TimeoutExpired):
            audio_path.unlink(missing_ok=True)
            audio_state = 'error_extraccion'
            continue
        audio = dict(archivo=audio_path.name, sha256=sha256(audio_path),
                     analisis='pendiente_mlaudio', stream_index=stream['index'])
        audio_state = 'extraido'
        break
    result = dict(version='0.3-video', muestreo_version=SAMPLING_VERSION,
                  fuente=source_info, sha256_video=digest, duracion_segundos=duration,
                  fotogramas=selected, audio=audio, estado_audio=audio_state,
                  creado_unix=time.time(), duracion_procesamiento_s=round(time.time()-started, 3),
                  ffmpeg_version=run(['ffmpeg', '-version']).decode().splitlines()[0],
                  regla='Último frame de segundos 1..10; primero de los últimos cinco intervalos; sin duplicar intervalos. El intervalo final parcial cuenta.')
    atomic_json(manifest_path, result)
    return result
