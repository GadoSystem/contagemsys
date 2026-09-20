# ContagemSys V5 — câmeras vinculadas ao usuário

O ContagemSys continua fazendo a detecção/contagem, mas agora funciona também como aplicação web.

## Como funciona

1. As câmeras são cadastradas em `config.yaml`.
2. O administrador abre `/admin` e vincula cada câmera a um usuário do **Rebano**.
3. O usuário entra no ContagemSys usando o **mesmo login e senha do Rebano**.
4. Ele vê somente as câmeras vinculadas ao `Usuario.Id` dele.
5. O backend do Rebano usa a mesma regra para mostrar apenas as câmeras do usuário logado.

Exemplo:

```text
Guilherme -> camera_1, camera_2, camera_3
Arthur    -> camera_4
```

Guilherme vê 3 câmeras. Arthur vê somente 1.

## Teste local rápido

### 1. Configure as câmeras

Em `config.yaml`:

```yaml
video:
  cameras:
    - id: "camera_1"
      name: "Webcam 1"
      source: 0
      enabled: true

    - id: "camera_2"
      name: "Webcam 2"
      source: 1
      enabled: true
```

Para descobrir os índices:

```bash
python listar_cameras.py
```

### 2. Instale e execute

```bash
python -m venv venv
```

PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
python main.py
```

O Rebano precisa estar rodando em `http://localhost:5148`.

### 3. Vincule as câmeras

Abra:

```text
http://localhost:8000/admin
```

Login de teste:

```text
Usuário: admin
Senha: admin123
```

Escolha o usuário do Rebano em cada câmera e clique em **Salvar**.

### 4. Teste como usuário

Abra:

```text
http://localhost:8000
```

Entre com o login normal do Rebano. O painel deve mostrar somente as câmeras vinculadas àquele usuário.

## Variáveis importantes

Arquivo `.env`:

```env
REBANO_API_URL=http://localhost:5148
CONTAGEM_INTEGRATION_KEY=REBANO_CONTAGEM_TEST_2026
CONTAGEM_ADMIN_USER=admin
CONTAGEM_ADMIN_PASSWORD=admin123
```

A `CONTAGEM_INTEGRATION_KEY` deve ser igual à `ContagemApi:IntegrationKey` do Rebano.

## Quando colocar na web

Para teste local, `source: 0` e `source: 1` usam webcams do computador onde o Python está rodando.

Em um servidor web/VPS, as câmeras precisam ser acessíveis pelo servidor, normalmente por URL RTSP/IP, por exemplo:

```yaml
source: "rtsp://usuario:senha@IP_DA_CAMERA:554/stream"
```

Hospedagem compartilhada comum não é indicada para YOLO/FastAPI e acesso a câmeras. Para produção, use um VPS/servidor com Python e recursos suficientes.

## Testes automatizados

```bash
python -m unittest discover -s tests -v
```
