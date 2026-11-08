import importlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
import zipfile
from unittest.mock import patch

import video
from archive import content_manifest

class SamplingTests(unittest.TestCase):
    def test_integer_and_partial_durations(self):
        for duration, count in [(0.4,1),(8,8),(10,10),(12,12),(14,14),(15,15),(20,15),(60,15),(8.4,9),(14.4,15)]:
            with self.subTest(duration=duration):
                frames=[{'best_effort_timestamp_time':str(i/10)} for i in range(int(duration*10))]
                selected=video.select_frames(frames,duration)
                self.assertEqual(len(selected),count)
                self.assertEqual(len({r['segundo'] for r in selected}),count)
                for r in selected:
                    if r['segundo']<=10:self.assertEqual(r['regla'],'ultimo_inicial')

    def test_offsets_variable_timestamps_and_missing(self):
        stamps=[100,100.2,100.97,101.1,101.9,102.05,102.4]
        selected=video.select_frames([{'best_effort_timestamp_time':str(t)} for t in stamps],2.5)
        self.assertEqual([r['tiempo_segundos'] for r in selected],[.97,1.9,2.4])
        self.assertRaises(ValueError,video.select_frames,[{}],2)

class IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name)
        cls.movie=cls.root/'test20.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','testsrc2=size=160x120:rate=10',
            '-f','lavfi','-i','sine=frequency=440:sample_rate=16000','-t','20','-c:v','mpeg4','-q:v','4',
            '-threads','1','-c:a','aac',str(cls.movie)],check=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def test_real_extraction_and_cache_repair(self):
        out=self.root/'derived'
        result=video.prepare(self.movie,out,{'archivo':'test20.mp4'})
        self.assertEqual(len(result['fotogramas']),15)
        self.assertEqual([f['segundo'] for f in result['fotogramas']],list(range(1,11))+list(range(16,21)))
        self.assertEqual([f['tiempo_segundos'] for f in result['fotogramas'][:2]],[.9,1.9])
        self.assertEqual([f['tiempo_segundos'] for f in result['fotogramas'][-5:]],[15,16,17,18,19])
        target=out/result['sha256_video']
        props=json.loads(video.run(['ffprobe','-v','error','-show_streams','-of','json',str(target/'audio.wav')]))['streams'][0]
        self.assertEqual(props['sample_rate'],'16000');self.assertEqual(props['channels'],1)
        with patch.object(video,'run',side_effect=AssertionError('No debe reprocesar')):
            self.assertEqual(video.prepare(self.movie,out,{'archivo':'otra_ruta.mp4'})['fuente']['archivo'],'otra_ruta.mp4')
        (target/'frame-01.jpg').write_bytes(b'corrupto')
        repaired=video.prepare(self.movie,out,{'archivo':'test20.mp4'})
        self.assertEqual(video.sha256(target/'frame-01.jpg'),repaired['fotogramas'][0]['sha256'])

    def test_silent_short_video(self):
        movie=self.root/'silent.mp4'
        subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(self.movie),'-t','8','-an','-c:v','copy',str(movie)],check=True)
        result=video.prepare(movie,self.root/'silent-derived',{})
        self.assertEqual(len(result['fotogramas']),8);self.assertIsNone(result['audio'])
        self.assertEqual(result['estado_audio'],'sin_pista_audio')

    def test_old_database_zip_versions_and_linked_derivatives(self):
        os.environ['DATA_DIR']=str(self.root/'app')
        import server
        server=importlib.reload(server);server.ROOT.mkdir()
        oldid='a'*64;folder=server.ROOT/oldid;folder.mkdir()
        original='[01/11/26, 10:00:00] Vecino: Semáforo apagado quinta con quinta.\n'
        def archive(file,text,date=(2026,1,1,0,0,0),movie=False):
            with zipfile.ZipFile(file,'w') as z:
                z.writestr(zipfile.ZipInfo('_chat.txt',date),text)
                if movie:z.write(self.movie,'carpeta/video.mp4')
        archive(folder/'original.zip',original)
        with sqlite3.connect(server.ROOT/'cola.sqlite') as conn:
            conn.execute('CREATE TABLE jobs(id TEXT PRIMARY KEY,name TEXT,state TEXT,error TEXT,created REAL)')
            conn.execute('INSERT INTO jobs VALUES(?,?,?,?,?)',(oldid,'WhatsApp Chat - Vecino.zip','texto_completado','',1))
        server.save(folder/'resultado.json',{'reportes':[],'archivo':'original.zip'})
        server.init()
        duplicate=self.root/'duplicate.zip';archive(duplicate,original,(2026,2,1,0,0,0))
        self.assertEqual(server.register_archive(duplicate,'WhatsApp Chat - Vecino(2).zip')['id'],oldid)
        revised=self.root/'revised.zip'
        archive(revised,original+'[02/11/26, 11:00:00] Vecino: <attached: video.mp4>\n',movie=True)
        registered=server.register_archive(revised,'WhatsApp Chat - Vecino(1).zip')
        self.assertEqual(registered['candidatas_version'][0]['relacion'],'ampliacion_del_chat')
        with server.db() as conn:
            self.assertEqual(conn.execute('SELECT state FROM jobs WHERE id=?',(oldid,)).fetchone()[0],'texto_completado')
            job=conn.execute('SELECT * FROM jobs WHERE id=?',(registered['id'],)).fetchone()
        server.prepare_media(job)
        result=json.loads((server.ROOT/registered['id']/'videos.json').read_text())
        self.assertEqual(result['videos'][0]['fuente']['mensaje_ids'],['M00002'])
        self.assertEqual(len(result['videos'][0]['fotogramas']),15)
        self.assertTrue((folder/'resultado.json').exists())

if __name__=='__main__':unittest.main(verbosity=2)
