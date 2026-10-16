import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from api import create_app
from auth import AuthService, normalizar_cpf
from persistence import EventDatabase
from state import LiveFrameStore, SharedState


CPF_VALIDO = '529.982.247-25'  # mesmo CPF da conta de demonstracao do Rebano
SENHA = 'senha-correta'


class FakeRebano:
    """Simula o POST /api/auth/login do Rebano (aceita CPF formatado)."""

    def __init__(self, usuario_cpf=CPF_VALIDO, status=None):
        self.usuario_cpf = usuario_cpf
        self.status = status
        self.requests = []

    def handler(self, request):
        body = json.loads(request.content)
        self.requests.append(body)
        if self.status is not None:
            return httpx.Response(self.status)
        if body['login'] != CPF_VALIDO or body['senha'] != SENHA:
            return httpx.Response(401, text='Login ou senha inválidos')
        return httpx.Response(200, json={
            'token': 'token-do-rebano',
            'usuario': {'id': 2, 'nome': 'Usuario Demo', 'email': 'demo@rebano.com', 'cpf': self.usuario_cpf},
        })

    def patch(self):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(self.handler)
        return mock.patch('auth.httpx.AsyncClient',
                          lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs))


def build_app(temp):
    db = EventDatabase(Path(temp) / 'events.db')
    db.set_camera_owner('camera_1', 2, 'Usuario A')
    db.set_camera_owner('camera_2', 3, 'Usuario B')
    service = AuthService(rebano_api_url='http://127.0.0.1:5148',
                          jwt_secret='chave-de-testes-local-123456789012345',
                          integration_key='integration', admin_user='admin', admin_password='pass')
    cameras = {}
    for camera_id in ('camera_1', 'camera_2'):
        state = SharedState(camera_id, camera_id)
        state.update_metrics(sistema_rodando=True)
        frames = LiveFrameStore()
        frames.update_jpeg(b'fake-jpeg')
        cameras[camera_id] = {'state': state, 'frames': frames}
    app = create_app(cameras, db, lambda: {}, auth_service=service, integration_key='integration')
    return app, service


class CpfFormatTests(unittest.TestCase):
    def test_accepts_with_and_without_mask(self):
        self.assertEqual(normalizar_cpf('529.982.247-25'), '52998224725')
        self.assertEqual(normalizar_cpf(' 52998224725 '), '52998224725')

    def test_rejects_invalid_formats(self):
        for value in ('', None, '5299822472', '529982247250', '529.982.247-26',
                      '111.111.111-11', 'abc52998224725', '529-982-247.25', 'demo@rebano.com'):
            with self.subTest(value=value):
                self.assertIsNone(normalizar_cpf(value))


class LoginCpfTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app, self.service = build_app(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def login(self, rebano, body):
        with rebano.patch(), TestClient(self.app) as client:
            return client.post('/api/auth/login', json=body)

    def test_valid_cpf_with_or_without_mask(self):
        for cpf in (CPF_VALIDO, '52998224725'):
            with self.subTest(cpf=cpf):
                rebano = FakeRebano()
                response = self.login(rebano, {'cpf': cpf, 'senha': SENHA})
                self.assertEqual(response.status_code, 200)
                # O Rebano recebe o CPF no formato gravado e verifica a senha.
                self.assertEqual(rebano.requests, [{'login': CPF_VALIDO, 'senha': SENHA}])
                claim = self.service.decode_token(response.json()['token'])
                self.assertEqual(claim['role'], 'user')
                self.assertEqual(claim['sub'], '2')

    def test_invalid_cpf_is_rejected_before_calling_rebano(self):
        rebano = FakeRebano()
        response = self.login(rebano, {'cpf': '529.982.247-26', 'senha': SENHA})
        self.assertEqual(response.status_code, 400)
        self.assertIn('CPF invalido', response.json()['detail'])
        self.assertEqual(rebano.requests, [])

    def test_empty_fields(self):
        for body in ({'cpf': '', 'senha': SENHA}, {'cpf': CPF_VALIDO, 'senha': ''}, {}):
            with self.subTest(body=body):
                rebano = FakeRebano()
                response = self.login(rebano, body)
                self.assertEqual(response.status_code, 400)
                self.assertEqual(response.json()['detail'], 'Informe o CPF e a senha')
                self.assertEqual(rebano.requests, [])

    def test_wrong_password_does_not_reveal_which_field(self):
        rebano = FakeRebano()
        response = self.login(rebano, {'cpf': CPF_VALIDO, 'senha': 'errada'})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'CPF ou senha incorretos')
        self.assertNotIn('token', response.json())

    def test_account_found_by_phone_with_same_digits_is_rejected(self):
        # Com 11 digitos o Rebano tambem procura telefone; so vale a conta do CPF.
        rebano = FakeRebano(usuario_cpf='111.444.777-35')
        response = self.login(rebano, {'cpf': CPF_VALIDO, 'senha': SENHA})
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()['detail'], 'CPF ou senha incorretos')

    def test_rebano_offline(self):
        def offline(request):
            raise httpx.ConnectError('offline', request=request)

        rebano = FakeRebano()
        rebano.handler = offline
        response = self.login(rebano, {'cpf': CPF_VALIDO, 'senha': SENHA})
        self.assertEqual(response.status_code, 502)

    def test_login_page_asks_for_cpf(self):
        with TestClient(self.app) as client:
            html = client.get('/').text
        self.assertIn('id="cpf"', html)
        self.assertIn('id="senha"', html)


class OtherUserCameraTests(unittest.TestCase):
    def test_user_cannot_access_camera_of_another_user(self):
        with tempfile.TemporaryDirectory() as temp:
            app, service = build_app(temp)
            headers = {'Authorization': f"Bearer {service._issue_token({'role': 'user', 'sub': '2'})}"}
            with TestClient(app) as client:
                # Lista apenas as cameras do token, mesmo com um id forjado na URL.
                listed = client.get('/api/minhas-cameras', params={'usuario_id': 3}, headers=headers)
                self.assertEqual([c['id'] for c in listed.json()], ['camera_1'])
                self.assertEqual(client.get('/api/minhas-cameras/camera_1/detalhes',
                                            headers=headers).status_code, 200)
                for method, path in (('GET', 'contagem'), ('GET', 'detalhes'), ('GET', 'eventos'),
                                     ('GET', 'frame.jpg'), ('GET', 'stream.mjpg'),
                                     ('POST', 'stream-ticket')):
                    with self.subTest(path=path):
                        response = client.request(method, f'/api/minhas-cameras/camera_2/{path}',
                                                  headers=headers)
                        self.assertEqual(response.status_code, 404)
                # Ticket de uma camera propria nao abre o stream de outra.
                ticket = service.issue_stream_ticket(2, 'camera_1')
                self.assertEqual(client.get('/api/minhas-cameras/camera_2/stream.mjpg',
                                            params={'ticket': ticket}).status_code, 401)
                self.assertEqual(client.get('/api/minhas-cameras/camera_2/contagem').status_code, 401)

    def test_user_without_cameras_gets_empty_list(self):
        with tempfile.TemporaryDirectory() as temp:
            app, service = build_app(temp)
            headers = {'Authorization': f"Bearer {service._issue_token({'role': 'user', 'sub': '9'})}"}
            with TestClient(app) as client:
                response = client.get('/api/minhas-cameras', headers=headers)
                self.assertEqual(response.status_code, 200)
                self.assertEqual(response.json(), [])


if __name__ == '__main__':
    unittest.main()
