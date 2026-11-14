from pathlib import Path
from statistics import mean

TRANSCRIPTION_PROMPT = (
    "Transcripción literal en español colombiano. Vocabulario posible: semáforo, "
    "intersección, calle, carrera, avenida, cruce, agente de tránsito. "
    "Respeta los números y las palabras que realmente se oyen."
)


def decode(model, path, options, on_progress, phase):
    segments, info = model.transcribe(str(path), **options)
    rows = []
    preview = ''
    for segment in segments:
        rows.append({
            'start': segment.start, 'end': segment.end, 'text': segment.text,
            'avg_logprob': segment.avg_logprob, 'no_speech_prob': segment.no_speech_prob,
            'compression_ratio': segment.compression_ratio,
        })
        preview = (preview + segment.text)[-2500:]
        if on_progress:
            fraction = min(0.99, segment.end / info.duration) if info.duration else None
            on_progress(phase=phase, fraction=fraction, preview=preview,
                        seconds=segment.end, duration=info.duration)
    return rows, info


def usable_segments(rows):
    return [row for row in rows if row['text'].strip()
            and row['compression_ratio'] < 2.4
            and (row['avg_logprob'] >= -1.25 or row['no_speech_prob'] < 0.5)]


def score(rows):
    usable = usable_segments(rows)
    if not usable:
        return float('-inf')
    return mean(row['avg_logprob'] for row in usable) - (len(rows) - len(usable)) / len(rows)


def transcribe(path, config, models_dir, on_progress=None):
    from huggingface_hub import snapshot_download
    from faster_whisper import WhisperModel

    if on_progress:
        on_progress(phase='Cargando modelo de audio')
    cache = str(Path(models_dir) / 'hf')
    try:
        snapshot = snapshot_download(config['repository'], revision=config['revision'],
                                     cache_dir=cache, local_files_only=True)
    except FileNotFoundError:
        snapshot = snapshot_download(config['repository'], revision=config['revision'], cache_dir=cache)
    model = WhisperModel(snapshot, device='cpu', compute_type=config['compute_type'],
                         cpu_threads=config['cpu_threads'], num_workers=1)
    options = dict(language=config.get('language'), beam_size=config['beam_size'],
                   vad_filter=config['vad_filter'], vad_parameters={'min_silence_duration_ms': 500,
                   'speech_pad_ms': 400}, condition_on_previous_text=False,
                   initial_prompt=TRANSCRIPTION_PROMPT, word_timestamps=True,
                   hallucination_silence_threshold=2.0)
    rows, info = decode(model, path, options, on_progress, 'Transcribiendo audio')
    alternate_used = False
    second_pass_failed = False
    if info.duration and score(rows) < -0.85:
        # Quiet speech and voice under street noise can be missed by the first VAD pass.
        alternate = dict(options, vad_filter=False, initial_prompt=None)
        try:
            other, other_info = decode(model, path, alternate, on_progress, 'Revisando audio difícil')
        except (RuntimeError, ValueError):
            second_pass_failed = True
        else:
            if score(other) > score(rows):
                rows, info, alternate_used = other, other_info, True
    usable = usable_segments(rows)
    needs_review = not usable or len(usable) != len(rows) or score(rows) < -0.85 or second_pass_failed
    parts = []
    offset = 0
    for row in rows:
        if row in usable:
            if parts and parts[-1]['offset'] + len(parts[-1]['text']) == offset:
                parts[-1]['text'] += row['text']
            else:
                parts.append({'text': row['text'], 'offset': offset})
        offset += len(row['text'])
    result = {'analysis_parts': parts, 'text': ''.join(row['text'] for row in rows),
              'analysis_text': ''.join(row['text'] for row in usable),
              'segments': rows, 'language': info.language, 'language_probability': info.language_probability,
              'duration': info.duration, 'needs_review': needs_review,
              'status': 'sin_voz_clara' if not usable else 'revisar' if needs_review else 'transcrito',
              'alternate_pass_used': alternate_used, 'alternate_pass_failed': second_pass_failed}
    identity = {'provider': 'faster_whisper_local', 'repository': config['repository'],
                'revision': Path(snapshot).name, 'compute_type': config['compute_type'],
                'profile': 'es-co-audio-v2'}
    return result, identity
