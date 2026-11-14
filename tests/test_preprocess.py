import shutil
import tempfile
import unittest
import wave
from pathlib import Path
from semaforos.files import sha256
from semaforos.preprocess import mono_audio


@unittest.skipUnless(shutil.which('ffmpeg'),'Requires ffmpeg')
class AudioPreparationTests(unittest.TestCase):
    def test_mono_derivative_reused_without_changing_original(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder);source=root/'stereo.wav'
            with wave.open(str(source),'wb') as f:
                f.setnchannels(2);f.setsampwidth(2);f.setframerate(44100);f.writeframes(b'\0'*44100*4)
            digest=sha256(source);prepared=mono_audio(root,source,digest);stamp=prepared.stat().st_mtime_ns
            with wave.open(str(prepared),'rb') as f:
                self.assertEqual(f.getnchannels(),1);self.assertEqual(f.getframerate(),16000)
            self.assertEqual(mono_audio(root,source,digest).stat().st_mtime_ns,stamp)
            self.assertEqual(sha256(source),digest)
