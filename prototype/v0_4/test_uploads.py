import hashlib
import io
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import unittest
import zipfile
from unittest.mock import patch

from uploads import Uploads


def digest(data):
    return hashlib.sha256(data).hexdigest()


class UploadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Uploads(self.root, reserve_bytes=0, chunk_bytes=4)

    def tearDown(self):
        self.temp.cleanup()

    def test_resume_after_restart_and_repeated_chunk(self):
        ident = self.store.create('chat.zip', 8)['id']
        self.store.append(ident, 0, b'abcd', digest(b'abcd'))
        # Simula escritura sin confirmación de offset antes de caer el proceso.
        with self.store.path(ident).open('ab') as f:
            f.write(b'corrupto')
        recovered = Uploads(self.root, reserve_bytes=0, chunk_bytes=4)
        self.assertTrue(recovered.check(ident, 0, 4, digest(b'abcd')))
        recovered.append(ident, 0, b'abcd', digest(b'abcd'))
        recovered.append(ident, 4, b'efgh', digest(b'efgh'))
        self.assertEqual(recovered.path(ident).read_bytes(), b'abcdefgh')
        self.assertEqual(recovered.finish(ident)['state'], 'pendiente')
        self.assertEqual(recovered.finish(ident)['state'], 'pendiente')

    def test_size_not_fixed_at_one_gib_and_reserved_space(self):
        from collections import namedtuple
        Disk = namedtuple('Disk', 'total used free')
        with patch('uploads.shutil.disk_usage', return_value=Disk(10**10, 0, 2*1024**3)):
            self.store.create('grande.zip', 1024**3 + 1)
            with self.assertRaises(ValueError):
                self.store.create('segundo.zip', 1024**3)

    def test_wrong_source_offset_hash_incomplete_and_cancel(self):
        ident = self.store.create('chat.zip', 8)['id']
        self.store.append(ident, 0, b'abcd', digest(b'abcd'))
        with self.assertRaises(ValueError):self.store.check(ident, 0, 4, digest(b'otro'))
        with self.assertRaises(ValueError):self.store.append(ident, 6, b'ef', digest(b'ef'))
        with self.assertRaises(ValueError):self.store.append(ident, 4, b'efgh', digest(b'otro'))
        with self.assertRaises(ValueError):self.store.finish(ident)
        self.store.cancel(ident)
        self.assertFalse(self.store.path(ident).exists())
        self.assertEqual(self.store.get(ident)['state'], 'cancelado')

    def test_recover_after_register_moved_file_before_commit(self):
        ident = self.store.create('chat.zip', 4)['id']
        self.store.append(ident, 0, b'abcd', digest(b'abcd'))
        self.store.finish(ident)
        def interrupted(path, name):
            path.replace(self.root/'already_registered.zip')
            raise KeyboardInterrupt('Simulación de caída abrupta')
        with self.assertRaises(KeyboardInterrupt):self.store.process_one(interrupted)
        self.assertTrue(self.store.path(ident).exists())
        recovered = Uploads(self.root, reserve_bytes=0)
        recovered.process_one(lambda path, name: {'duplicado': True})
        self.assertEqual(recovered.get(ident)['state'], 'recibido')
        self.assertFalse(recovered.path(ident).exists())

    def test_over_100_uploads_continue_after_error_and_new_arrivals(self):
        seen = []
        def receive(n):
            ident = self.store.create(f'{n}.zip', 4)['id']
            self.store.append(ident, 0, b'abcd', digest(b'abcd'))
            self.store.finish(ident)
            return ident
        ids = [receive(n) for n in range(110)]
        def register(path, name):
            if name == '2.zip':raise ValueError('ZIP corrupto de prueba')
            seen.append(name)
            return {'ok': True}
        for _ in range(10):self.store.process_one(register)
        ids.extend(receive(n) for n in range(110, 125))
        while self.store.process_one(register):pass
        self.assertEqual(len(seen), 124)
        self.assertEqual(self.store.get(ids[2])['state'], 'error')
        self.assertEqual(self.store.get(ids[-1])['state'], 'recibido')


class IntegratedTests(unittest.TestCase):
    def test_http_chunks_registration_and_existing_queue(self):
        import base64
        from http.server import ThreadingHTTPServer
        from urllib.request import Request, urlopen
        import server
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(server, 'ROOT', Path(directory)), patch.object(server, 'PASSWORD', 'test-only-password-000'), patch.object(server, 'RESERVE_BYTES', 0):
                server.init()
                http = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
                thread = threading.Thread(target=http.serve_forever, daemon=True)
                thread.start()
                auth = 'Basic '+base64.b64encode(b'semaforos:test-only-password-000').decode()
                def request(route, data, binary=False):
                    encoded = data if binary else json.dumps(data).encode()
                    req = Request(f'http://127.0.0.1:{http.server_port}'+route, data=encoded,
                                  headers={'Authorization': auth, 'X-Semaforos': '1'})
                    with urlopen(req, timeout=10) as response:return json.load(response)
                try:
                    archive = io.BytesIO()
                    with zipfile.ZipFile(archive, 'w') as z:
                        z.writestr('_chat.txt', '[01/11/26, 10:00:00] Vecino: Semáforo apagado.\n')
                    data = archive.getvalue()
                    def upload(name):
                        ident = request('/uploads/create', {'name': name, 'size': len(data)})['id']
                        check = request('/uploads/check?id='+ident, {'offset': 0, 'length': len(data), 'sha256': digest(data)})
                        self.assertFalse(check['exists'])
                        request('/uploads/chunk?id='+ident+'&offset=0&sha256='+digest(data), data, True)
                        self.assertEqual(request('/uploads/finish?id='+ident, {})['state'], 'pendiente')
                        server.UPLOADS.process_one(server.register_archive)
                        return server.UPLOADS.get(ident)
                    first = upload('Vecino.zip')
                    second = upload('Vecino (1).zip')
                    self.assertEqual(first['state'], 'recibido')
                    self.assertTrue(second['result']['duplicado'])
                    with server.db() as c:
                        self.assertEqual(c.execute('SELECT COUNT(*) FROM jobs').fetchone()[0], 1)
                        self.assertEqual(c.execute('SELECT state FROM jobs').fetchone()[0], 'pendiente')
                finally:
                    http.shutdown();http.server_close();thread.join()


if __name__ == '__main__':
    unittest.main()
