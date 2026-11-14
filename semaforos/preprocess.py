"""Reusable audio derivative; original evidence is never modified."""
import fcntl
import os
import subprocess
from .files import contained


def mono_audio(root,source,digest):
    if len(digest)!=64 or any(c not in '0123456789abcdef' for c in digest):raise ValueError('invalid_digest')
    folder=contained(root,'derived/audio-v1/'+digest);folder.mkdir(parents=True,exist_ok=True)
    target=folder/'mono-16000.wav'
    with (folder/'prepare.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        if target.is_file() and target.stat().st_size>44:return target
        temporary=folder/'preparing.wav'
        try:
            subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-threads','1','-i',str(source),
                '-vn','-ac','1','-ar','16000','-c:a','pcm_s16le','-threads','1',str(temporary)],
                check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=1800)
            os.replace(temporary,target)
        finally:temporary.unlink(missing_ok=True)
    return target
