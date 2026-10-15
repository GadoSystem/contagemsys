import tempfile
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from api import create_app
from auth import AuthService
from persistence import EventDatabase
from state import LiveFrameStore, SharedState


class StreamTicketTests(unittest.TestCase):
    def test_scoped_ticket_and_user_isolation(self):
        with tempfile.TemporaryDirectory() as temp:
            db = EventDatabase(Path(temp) / 'events.db')
            db.set_camera_owner('camera_1', 2, 'Usuario A')
            db.set_camera_owner('camera_2', 3, 'Usuario B')
            service = AuthService(rebano_api_url='http://127.0.0.1:5148',
                                  jwt_secret='chave-de-testes-local-123456789012345',
                                  integration_key='integration', admin_user='admin', admin_password='pass')
            cameras = {}
            for camera_id in ('camera_1', 'camera_2'):
                state = SharedState(camera_id, camera_id)
                frames = LiveFrameStore()
                frames.update_jpeg(b'fake-jpeg')
                cameras[camera_id] = {'state': state, 'frames': frames}
            app = create_app(cameras, db, lambda: {}, auth_service=service, integration_key='integration')
            login_2 = service._issue_token({'role': 'user', 'sub': '2'})
            with TestClient(app) as client:
                result = client.post('/api/minhas-cameras/camera_1/stream-ticket',
                                     headers={'Authorization': f'Bearer {login_2}'})
                self.assertEqual(result.status_code, 200)
                ticket = result.json()['ticket']
                claim = service.decode_token(ticket)
                self.assertEqual(claim['role'], 'stream')
                self.assertEqual(claim['sub'], '2')
                self.assertEqual(claim['camera_id'], 'camera_1')
                self.assertEqual(client.post('/api/minhas-cameras/camera_2/stream-ticket',
                                              headers={'Authorization': f'Bearer {login_2}'}).status_code, 404)
                self.assertEqual(client.get('/api/minhas-cameras/camera_1/frame.jpg',
                                             headers={'Authorization': f'Bearer {ticket}'}).status_code, 403)
                # Falha antes de comecar streaming, sem bloquear o TestClient.
                self.assertEqual(client.get('/api/minhas-cameras/camera_2/stream.mjpg',
                                             params={'ticket': ticket}).status_code, 401)
                self.assertEqual(client.get('/api/minhas-cameras/camera_1/stream.mjpg',
                                             params={'ticket': 'invalid'}).status_code, 401)


if __name__ == '__main__':
    unittest.main()
