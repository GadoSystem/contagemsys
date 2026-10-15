import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient
from api import create_app
from persistence import EventDatabase
from state import LiveFrameStore, SharedState


class FakeAuth:
    def decode_token(self, token):
        return {"role": "user", "sub": "2" if token == "dois" else "3"}


class ApiDetailsTests(unittest.TestCase):
    def test_details_authorized_and_isolated(self):
        with tempfile.TemporaryDirectory() as d:
            db = EventDatabase(Path(d) / 'test.db')
            db.set_camera_owner('camera_1', 2, 'Pessoa dois')
            sid = db.start_session('camera_1')
            db.insert_event(sid, 'camera_1', {
                'track_id': 1, 'direcao': 'direita_para_esquerda',
                'contabilizado': True, 'confidence': .90, 'frame_index': 10,
            })
            state = SharedState('camera_1', 'Webcam')
            state.reset_counters(session_id=sid)
            state.update_metrics(sistema_rodando=True)
            frames = LiveFrameStore()
            frames.update_jpeg(b'frame')
            app = create_app({'camera_1': {'state': state, 'frames': frames}}, db, lambda: {},
                             auth_service=FakeAuth(), integration_key='test-key')
            with TestClient(app) as c:
                url = '/api/integracao/usuarios/2/cameras/camera_1/detalhes'
                self.assertEqual(c.get(url).status_code, 401)
                r = c.get(url, headers={'X-Integration-Key': 'test-key'})
                self.assertEqual(r.status_code, 200)
                self.assertEqual(r.json()['estatisticas']['total_historico'], 1)
                self.assertEqual(len(r.json()['eventos']), 1)
                self.assertNotIn('snapshot_path', r.json()['eventos'][0])
                self.assertEqual(c.get('/api/integracao/usuarios/3/cameras/camera_1/detalhes',
                                       headers={'X-Integration-Key':'test-key'}).status_code, 404)
                self.assertEqual(c.get('/api/minhas-cameras/camera_1/detalhes',
                                       headers={'Authorization':'Bearer dois'}).status_code, 200)
                self.assertEqual(c.get('/api/minhas-cameras/camera_1/detalhes',
                                       headers={'Authorization':'Bearer tres'}).status_code, 404)


if __name__ == '__main__':
    unittest.main()
