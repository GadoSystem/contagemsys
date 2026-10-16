import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import httpx
from fastapi.testclient import TestClient

from api import OUTRAS_CAMERAS, agrupar_por_fazenda, create_app
from auth import AuthService
from persistence import EventDatabase
from state import LiveFrameStore, SharedState


CPF = '529.982.247-25'
SENHA = 'senha-correta'
REBANO_TOKEN = 'token-do-rebano-secreto'


class FakeRebano:
    """Simula login, GET /Fazenda/ObterTodos e GET /Fazenda/{id}/Cameras do Rebano."""

    def __init__(self, fazendas=None, cameras_por_fazenda=None, fazendas_status=200):
        self.fazendas = fazendas if fazendas is not None else []
        self.cameras_por_fazenda = cameras_por_fazenda or {}
        self.fazendas_status = fazendas_status
        self.requests = []

    def handler(self, request):
        path = request.url.path
        self.requests.append((request.method, path, request.headers.get('Authorization')))
        if path == '/api/auth/login':
            body = json.loads(request.content)
            if body != {'login': CPF, 'senha': SENHA}:
                return httpx.Response(401, text='Login ou senha inválidos')
            return httpx.Response(200, json={
                'token': REBANO_TOKEN,
                'usuario': {'id': 2, 'nome': 'Usuario Demo', 'email': 'demo@rebano.com', 'cpf': CPF},
            })
        if request.headers.get('Authorization') != f'Bearer {REBANO_TOKEN}':
            return httpx.Response(401)
        if path == '/Fazenda/ObterTodos':
            if self.fazendas_status != 200:
                return httpx.Response(self.fazendas_status)
            return httpx.Response(200, json=self.fazendas)
        if path.startswith('/Fazenda/') and path.endswith('/Cameras'):
            fazenda_id = int(path.split('/')[2])
            return httpx.Response(200, json=self.cameras_por_fazenda.get(fazenda_id, []))
        return httpx.Response(404)

    def patch(self):
        real_client = httpx.AsyncClient
        transport = httpx.MockTransport(self.handler)
        return mock.patch('auth.httpx.AsyncClient',
                          lambda *args, **kwargs: real_client(*args, transport=transport, **kwargs))


def camera_rebano(identificacao, fazenda_id, fazenda_nome):
    return {'id': 1, 'identificacao': identificacao, 'status': 'Ativa', 'localizacao': 'Curral',
            'fazendaId': fazenda_id, 'fazendaNome': fazenda_nome}


def build_app(temp):
    db = EventDatabase(Path(temp) / 'events.db')
    # Usuario 2 tem tres cameras; camera_4 pertence a outro usuario.
    for camera_id in ('camera_1', 'camera_2', 'camera_3'):
        db.set_camera_owner(camera_id, 2, 'Usuario Demo')
    db.set_camera_owner('camera_4', 3, 'Outro Usuario')
    service = AuthService(rebano_api_url='http://127.0.0.1:5148',
                          jwt_secret='chave-de-testes-local-123456789012345',
                          integration_key='integration', admin_user='admin', admin_password='pass')
    cameras = {}
    for camera_id in ('camera_1', 'camera_2', 'camera_3', 'camera_4'):
        state = SharedState(camera_id, camera_id)
        state.update_metrics(sistema_rodando=True)
        frames = LiveFrameStore()
        frames.update_jpeg(b'fake-jpeg')
        cameras[camera_id] = {'state': state, 'frames': frames}
    app = create_app(cameras, db, lambda: {}, auth_service=service, integration_key='integration')
    return app, service


def resumo(grupos):
    return [(g['id'], g['nome'], [c['id'] for c in g['cameras']]) for g in grupos]


class AgruparPorFazendaTests(unittest.TestCase):
    CAMERAS = [{'id': 'camera_1'}, {'id': 'camera_2'}, {'id': 'camera_3'}]

    def test_groups_by_farm_and_sorts_by_name(self):
        mapa = {'camera_1': {'id': 7, 'nome': 'Santa Rita'},
                'camera_2': {'id': 5, 'nome': 'Boa Vista'},
                'camera_3': {'id': 7, 'nome': 'Santa Rita'}}
        self.assertEqual(resumo(agrupar_por_fazenda(self.CAMERAS, mapa)), [
            (5, 'Boa Vista', ['camera_2']),
            (7, 'Santa Rita', ['camera_1', 'camera_3']),
        ])

    def test_unmatched_cameras_go_to_outras(self):
        mapa = {'camera_1': {'id': 5, 'nome': 'Boa Vista'}, 'camera_9': {'id': 8, 'nome': 'Sem cameras aqui'}}
        self.assertEqual(resumo(agrupar_por_fazenda(self.CAMERAS, mapa)), [
            (5, 'Boa Vista', ['camera_1']),
            (None, OUTRAS_CAMERAS, ['camera_2', 'camera_3']),
        ])

    def test_without_mapping_everything_is_outras(self):
        self.assertEqual(resumo(agrupar_por_fazenda(self.CAMERAS, None)),
                         [(None, OUTRAS_CAMERAS, ['camera_1', 'camera_2', 'camera_3'])])
        self.assertEqual(agrupar_por_fazenda([], None), [])


class MinhasFazendasEndpointTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.app, self.service = build_app(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def login_and_get(self, rebano):
        with rebano.patch(), TestClient(self.app) as client:
            login = client.post('/api/auth/login', json={'cpf': '52998224725', 'senha': SENHA})
            self.assertEqual(login.status_code, 200)
            # O token do Rebano fica so no servidor.
            self.assertNotIn(REBANO_TOKEN, login.text)
            self.assertNotIn(REBANO_TOKEN, json.dumps(self.service.decode_token(login.json()['token'])))
            headers = {'Authorization': f"Bearer {login.json()['token']}"}
            response = client.get('/api/minhas-fazendas', headers=headers)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn(REBANO_TOKEN, response.text)
            return response.json()

    def test_groups_authorized_cameras_by_rebano_farm(self):
        rebano = FakeRebano(
            fazendas=[{'id': 1, 'nome': 'Fazenda Primavera'}, {'id': 2, 'nome': 'Fazenda Aurora'},
                      {'id': 3, 'nome': 'Fazenda Vazia'}],
            cameras_por_fazenda={
                1: [camera_rebano('camera_1', 1, 'Fazenda Primavera'),
                    camera_rebano('camera_4', 1, 'Fazenda Primavera')],   # de outro usuario
                2: [camera_rebano(' CAMERA_2 ', 2, 'Fazenda Aurora')],
            },
        )
        data = self.login_and_get(rebano)
        self.assertTrue(data['fazendas_sincronizadas'])
        self.assertEqual(resumo(data['grupos']), [
            (2, 'Fazenda Aurora', ['camera_2']),
            (1, 'Fazenda Primavera', ['camera_1']),
            (None, OUTRAS_CAMERAS, ['camera_3']),
        ])
        # Os dados de contagem acompanham cada camera.
        camera = data['grupos'][0]['cameras'][0]
        for campo in ('status', 'total_contado', 'retornos_esquerda_para_direita'):
            self.assertIn(campo, camera)
        # A consulta usa o token do Rebano do proprio usuario.
        fazenda_calls = [r for r in rebano.requests if r[1].startswith('/Fazenda/')]
        self.assertTrue(fazenda_calls)
        self.assertTrue(all(r[2] == f'Bearer {REBANO_TOKEN}' for r in fazenda_calls))

    def test_no_match_in_rebano_puts_all_in_outras(self):
        rebano = FakeRebano(fazendas=[{'id': 1, 'nome': 'Fazenda Primavera'}],
                            cameras_por_fazenda={1: [camera_rebano('portaria', 1, 'Fazenda Primavera')]})
        data = self.login_and_get(rebano)
        self.assertTrue(data['fazendas_sincronizadas'])
        self.assertEqual(resumo(data['grupos']),
                         [(None, OUTRAS_CAMERAS, ['camera_1', 'camera_2', 'camera_3'])])

    def test_rebano_farm_error_does_not_block_login(self):
        data = self.login_and_get(FakeRebano(fazendas_status=500))
        self.assertEqual(resumo(data['grupos']),
                         [(None, OUTRAS_CAMERAS, ['camera_1', 'camera_2', 'camera_3'])])

    def test_without_rebano_session_reports_not_synchronized(self):
        # Ex.: ContagemSys reiniciado com token ainda valido.
        headers = {'Authorization': f"Bearer {self.service._issue_token({'role': 'user', 'sub': '2'})}"}
        with TestClient(self.app) as client:
            data = client.get('/api/minhas-fazendas', headers=headers).json()
        self.assertFalse(data['fazendas_sincronizadas'])
        self.assertEqual(resumo(data['grupos']),
                         [(None, OUTRAS_CAMERAS, ['camera_1', 'camera_2', 'camera_3'])])

    def test_other_user_and_anonymous(self):
        headers = {'Authorization': f"Bearer {self.service._issue_token({'role': 'user', 'sub': '3'})}"}
        with TestClient(self.app) as client:
            data = client.get('/api/minhas-fazendas', params={'usuario_id': 2}, headers=headers).json()
            self.assertEqual(resumo(data['grupos']), [(None, OUTRAS_CAMERAS, ['camera_4'])])
            self.assertEqual(client.get('/api/minhas-fazendas').status_code, 401)


class InterfaceTests(unittest.TestCase):
    def test_pages_and_static_files_are_served_locally(self):
        with tempfile.TemporaryDirectory() as temp:
            app, _ = build_app(temp)
            with TestClient(app) as client:
                login = client.get('/').text
                painel = client.get('/painel').text
                for html in (login, painel):
                    self.assertIn('/static/app.css', html)
                    self.assertIn('/static/logo-rebano.svg', html)
                    self.assertNotIn('http://', html.replace('http://www.w3.org', ''))
                    self.assertNotIn('https://', html)
                for path, tipo in (('/static/app.css', 'text/css'), ('/static/login.js', 'javascript'),
                                   ('/static/painel.js', 'javascript'), ('/static/logo-rebano.svg', 'image/svg')):
                    with self.subTest(path=path):
                        response = client.get(path)
                        self.assertEqual(response.status_code, 200)
                        self.assertIn(tipo, response.headers['content-type'])
                self.assertEqual(client.get('/admin').status_code, 200)


if __name__ == '__main__':
    unittest.main()
