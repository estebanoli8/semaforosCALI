from pathlib import Path


def transcribe(path, config, models_dir):
    from huggingface_hub import snapshot_download
    from faster_whisper import WhisperModel
    snapshot=snapshot_download(config['repository'],revision=config['revision'],cache_dir=str(Path(models_dir)/'hf'))
    model=WhisperModel(snapshot,device='cpu',compute_type=config['compute_type'],cpu_threads=config['cpu_threads'],num_workers=1)
    segments, info=model.transcribe(str(path),language=config.get('language'),beam_size=config['beam_size'],vad_filter=config['vad_filter'])
    # faster-whisper produce un generador; medir después de consumirlo completamente.
    rows=[{'start':s.start,'end':s.end,'text':s.text,'avg_logprob':s.avg_logprob,'no_speech_prob':s.no_speech_prob} for s in segments]
    result={'text':''.join(r['text'] for r in rows),'segments':rows,'language':info.language,
            'language_probability':info.language_probability,'duration':info.duration}
    identity={'provider':'faster_whisper_local','repository':config['repository'],'revision':Path(snapshot).name,'compute_type':config['compute_type']}
    return result,identity
