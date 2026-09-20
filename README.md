# ContagemSys V4.1 — Multi-câmera otimizada + API autenticada para o Rebano

Sistema de visão computacional para detecção, rastreamento e contagem direcional em tempo real. A V4 foi preparada para rodar em uma máquina dedicada às câmeras e ser consumida remotamente pelo backend ASP.NET Core do projeto **Rebano**.

## Principais mudanças da V4.1

- múltiplas fontes de vídeo simultâneas;
- suporte a duas ou mais webcams, arquivos de vídeo ou URLs RTSP compatíveis com OpenCV;
- um tracker, contador, sessão, estado e evidências independentes para cada câmera;
- API FastAPI acessível por outra máquina da rede;
- autenticação máquina-a-máquina usando o header `X-API-Key`;
- chave secreta carregada pelo arquivo `.env`, que não deve ir para o Git;
- endpoint para frame JPEG de cada câmera;
- endpoint MJPEG de vídeo em tempo real de cada câmera;
- endpoint agregado com a soma das contagens de todas as câmeras;
- eventos e sessões persistidos com `camera_id` no SQLite;
- migração automática de banco criado pela V3;
- utilitário `listar_cameras.py` para descobrir os índices das webcams;
- integração pronta para o backend do Rebano atuar como proxy, mantendo a API key fora do React.
- captura, renderização e inferência desacopladas: o vídeo não fica preso ao FPS da IA;
- inferências das câmeras coordenadas para evitar saturação da CPU;
- perfil padrão 640x480 + MJPG para reduzir largura de banda USB com duas webcams;
- PyTorch limitado automaticamente para deixar CPU livre para captura, API e interface;
- stream MJPEG contínuo para o Rebano, sem polling de uma imagem a cada 650 ms;
- JPEG da API sem a barra lateral por padrão, reduzindo CPU e tráfego de rede.

---

## Arquitetura

```text
MAQUINA A - CONTAGEM                         MAQUINA B - REBANO

Webcam 0 ----\                              React
              -> ContagemSys/FastAPI         |
Webcam 1 ----/       :8000                   v
                        ^               ASP.NET Core
                        | X-API-Key          |
                        +--------------------+
```

O navegador não acessa a FastAPI diretamente. O fluxo recomendado é:

```text
React -> JWT -> ASP.NET Core Rebano -> X-API-Key -> FastAPI ContagemSys
```

Isso evita colocar a chave secreta da FastAPI no JavaScript do frontend.

---

# 1. Requisitos

Recomendado:

- Windows 10/11;
- Python 3.12;
- duas webcams USB para o teste solicitado;
- VS Code;
- rede local entre as duas máquinas;
- modelo `yolo26n.pt` já incluído no projeto.

Verifique o Python:

```bash
python --version
```

---

# 2. Criar o ambiente virtual

Dentro da pasta do projeto:

```bash
python -m venv venv
```

Git Bash:

```bash
source venv/Scripts/activate
```

PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
```

CMD:

```cmd
venv\Scripts\activate
```

---

# 3. Instalar as dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Teste:

```bash
python -c "import cv2, ultralytics, fastapi, yaml, dotenv; print('Dependencias OK')"
```

---

# 4. Descobrir os índices das duas webcams

Antes de iniciar o programa principal, execute:

```bash
python listar_cameras.py
```

Exemplo de saída:

```text
[OK] source: 0 -> 1280x720
[OK] source: 1 -> 1280x720
```

Se aparecer `0` e `2`, por exemplo, use `0` e `2` no `config.yaml`. Os índices não são garantidos; o Windows pode mudá-los dependendo da porta USB e de outros dispositivos de vídeo instalados.

---

# 5. Configurar múltiplas câmeras

Abra `config.yaml`.

Exemplo para duas webcams:

```yaml
video:
  width: 640
  height: 480
  fps: 30
  backend: "auto"
  fourcc: "MJPG"
  inference_fps: 6

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

Para adicionar uma terceira câmera:

```yaml
    - id: "camera_3"
      name: "Entrada do curral"
      source: 2
      enabled: true
```

Os IDs devem ser únicos e usar apenas letras, números, `_` ou `-`.

Cada câmera também pode sobrescrever `width`, `height`, `fps`, `inference_fps`, `backend`, `fourcc`, `roi` e `gate` individualmente.

Exemplo:

```yaml
    - id: "camera_curral"
      name: "Curral principal"
      source: 1
      enabled: true
      inference_fps: 5
      roi:
        enabled: true
        x1: 0.10
        y1: 0.20
        x2: 0.90
        y2: 0.95
      gate:
        left_x: 0.40
        right_x: 0.60
```

---

# 6. Configurar a API key

A chave não deve ser escrita diretamente no `config.yaml`.

Copie:

```text
.env.example
```

para:

```text
.env
```

No Windows CMD:

```cmd
copy .env.example .env
```

PowerShell:

```powershell
Copy-Item .env.example .env
```

Gere uma chave forte:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Coloque o valor no `.env`:

```env
CONTAGEM_API_KEY=SUA_CHAVE_LONGA_AQUI
```

O `.env` já está no `.gitignore`.

A mesma chave deverá ser configurada no backend ASP.NET Core do Rebano.

---

# 7. Permitir acesso pela outra máquina

A configuração já vem com:

```yaml
app:
  host: "0.0.0.0"
  port: 8000
```

`0.0.0.0` é importante. Se usar `127.0.0.1`, somente a própria máquina poderá acessar a FastAPI.

Descubra o IPv4 da máquina da contagem:

```cmd
ipconfig
```

Procure algo parecido com:

```text
Endereço IPv4 . . . . . . . . . . . : 192.168.1.50
```

Neste exemplo, a URL da API para a outra máquina será:

```text
http://192.168.1.50:8000
```

---

# 8. Liberar a porta 8000 no Firewall do Windows

Abra PowerShell como Administrador na máquina da contagem:

```powershell
New-NetFirewallRule -DisplayName "ContagemSys FastAPI 8000" -Direction Inbound -Protocol TCP -LocalPort 8000 -Action Allow
```

Alternativa pelo CMD como Administrador:

```cmd
netsh advfirewall firewall add rule name="ContagemSys FastAPI 8000" dir=in action=allow protocol=TCP localport=8000
```

Faça isso apenas na máquina que executa o `contagemsys`.

---

# 9. Executar o ContagemSys

```bash
python main.py
```

Com duas webcams ativas, serão criadas duas janelas independentes.

Para encerrar todas:

```text
Q
```

Swagger local:

```text
http://127.0.0.1:8000/docs
```

Swagger a partir da máquina do Rebano:

```text
http://IP_DA_MAQUINA_CONTAGEM:8000/docs
```

No Swagger clique em **Authorize** e informe a API key no campo `X-API-Key`.

---

# 10. Testar a API pela própria máquina

PowerShell:

```powershell
$headers = @{ "X-API-Key" = "SUA_CHAVE" }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Headers $headers
```

Câmeras:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/cameras" -Headers $headers
```

Contagem da primeira câmera:

```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/cameras/camera_1/contagem/atual" -Headers $headers
```

---

# 11. Testar a partir da máquina do Rebano

Na máquina B, troque o IP abaixo pelo IPv4 da máquina A:

```powershell
$headers = @{ "X-API-Key" = "SUA_CHAVE" }
Invoke-RestMethod -Uri "http://192.168.1.50:8000/health" -Headers $headers
```

Se isso funcionar, a comunicação de rede está pronta.

Se falhar, verifique:

1. as duas máquinas estão na mesma rede;
2. `python main.py` está em execução;
3. `app.host` está como `0.0.0.0`;
4. porta `8000` foi liberada no firewall;
5. o IP usado é o IPv4 da máquina da contagem;
6. a API key é exatamente a mesma;
7. teste `ping 192.168.1.50` entre as máquinas, se ICMP estiver permitido.

---

# 12. Endpoints principais

Todos os endpoints abaixo exigem `X-API-Key`.

```text
GET  /health
GET  /cameras
GET  /contagem/atual
GET  /contagem/eventos
GET  /contagem/sessoes
POST /contagem/resetar

GET  /cameras/{camera_id}/contagem/atual
GET  /cameras/{camera_id}/contagem/eventos
GET  /cameras/{camera_id}/contagem/sessoes
POST /cameras/{camera_id}/contagem/resetar
GET  /cameras/{camera_id}/frame.jpg
GET  /cameras/{camera_id}/stream.mjpg

GET  /contagem/eventos/{event_id}
GET  /contagem/eventos/{event_id}/snapshot
GET  /contagem/eventos/{event_id}/clip
```

### `GET /cameras`

Retorna uma lista como:

```json
[
  {
    "id": "camera_1",
    "name": "Webcam 1",
    "status": "online",
    "total_contado": 4,
    "animais_no_frame_agora": 1,
    "retornos_esquerda_para_direita": 2,
    "fps_camera": 29.8,
    "fps_ia": 17.2,
    "latencia_ia_ms": 51.3,
    "session_id": 8,
    "ultimo_erro": null,
    "frame_url": "/cameras/camera_1/frame.jpg",
    "stream_url": "/cameras/camera_1/stream.mjpg"
  }
]
```

### `GET /contagem/atual`

Soma as métricas das câmeras e também devolve os estados individuais.

### `GET /cameras/{id}/frame.jpg`

Retorna o último frame anotado em JPEG. É útil para diagnóstico, snapshot e fallback.

### `GET /cameras/{id}/stream.mjpg`

Retorna stream MJPEG contínuo. Na integração V4.1, o backend ASP.NET Core do Rebano mantém a conexão com esse endpoint usando `X-API-Key` e repassa o stream ao frontend autenticado por JWT. Isso elimina o limite de aproximadamente 1,5 FPS causado pelo polling antigo de frames.

---

# 13. Como a contagem é separada por câmera

Cada câmera possui seu próprio:

- `YOLO`;
- tracker persistente;
- `GateCounter`;
- estado de IDs visuais;
- `SharedState`;
- sessão do SQLite;
- `EvidenceRecorder`;
- buffer de frames.

Isso é obrigatório porque o tracker da Ultralytics mantém estado entre frames. Compartilhar o mesmo tracker entre duas câmeras faria IDs de cenas independentes interferirem uns nos outros.

As evidências ficam separadas, por exemplo:

```text
eventos/
├── camera_1/
│   └── 2026-09-15/
└── camera_2/
    └── 2026-09-15/
```

---

# 14. Testar a lógica de contagem

Para testes com pessoas, mantenha:

```yaml
model:
  classes: [0]
```

Fluxo contado:

```text
RIGHT -> CENTER -> LEFT = +1
```

Retorno:

```text
LEFT -> CENTER -> RIGHT = registra retorno, mas não soma
```

Quando for migrar para bovinos usando o modelo COCO:

```yaml
model:
  classes: [19]
```

Antes de usar em ambiente real, valide o modelo com imagens reais de bovinos e considere treinar um modelo específico para o corredor/curral utilizado.

---

# 15. Rodar testes automatizados

```bash
python -m unittest discover -s tests -v
```

A versão entregue foi validada com 12 testes automatizados.

---

# 16. Desempenho com duas câmeras

A V4.1 foi alterada especificamente para o cenário de duas webcams em CPU. Antes, cada câmera executava `model.track()` ao mesmo tempo e a própria janela só recebia um frame novo depois da inferência. Isso podia derrubar o sistema para cerca de 1 FPS.

Agora existem três ritmos independentes:

```text
Webcam (captura) -> ~30 FPS
Janela local     -> até 20 FPS
YOLO/ByteTrack   -> alvo de 6 FPS por câmera
Stream Rebano    -> até 10 FPS
```

O vídeo continua fluido mesmo se a IA estiver processando a 4-6 FPS. As boxes são atualizadas no ritmo da IA, enquanto o frame da câmera continua sendo renovado.

Configuração recomendada para duas webcams em CPU:

```yaml
performance:
  max_concurrent_inferences: 1
  torch_threads: 0
  opencv_threads: 1

video:
  width: 640
  height: 480
  fps: 30
  backend: "auto"
  fourcc: "MJPG"
  inference_fps: 6

model:
  imgsz: 320

api:
  jpeg_quality: 72
  stream_fps: 10
  include_sidebar: false
```

`max_concurrent_inferences: 1` é intencional em CPU: as duas câmeras se alternam no YOLO, em vez de duas inferências tentarem ocupar todos os núcleos simultaneamente. Se futuramente a máquina tiver uma GPU dedicada forte, teste `2` e compare o `fps_ia` e a `latencia_ia_ms`.

Se ainda estiver pesado, reduza primeiro:

```yaml
video:
  inference_fps: 4

model:
  imgsz: 256
```

Se a captura da webcam estiver baixa mesmo com a IA desligada, mantenha `640x480`, `fourcc: "MJPG"` e conecte as duas webcams em portas/controladores USB diferentes quando possível. Duas webcams em resolução alta podem disputar largura de banda do mesmo controlador USB.

Para priorizar precisão em uma máquina mais forte:

```yaml
video:
  inference_fps: 8

model:
  imgsz: 416
```

A métrica `fps_camera` mostra a captura da webcam; `fps_ia` mostra quantas inferências por segundo aquela câmera está conseguindo processar. Elas não precisam ter o mesmo valor.

---

# 17. Segurança

`X-API-Key` autentica o consumidor, mas HTTP puro não criptografa o tráfego. Para testes entre duas máquinas na mesma rede isolada, isso costuma ser suficiente.

Para produção, internet pública ou Wi-Fi não confiável, use HTTPS por reverse proxy (Nginx/Caddy/IIS), VPN privada ou solução equivalente. Não exponha a porta 8000 diretamente para a internet.

Nunca envie para o Git:

```text
.env
```

E nunca coloque a `CONTAGEM_API_KEY` no React.

---

# 18. Integração com o Rebano

Nesta entrega existe um segundo ZIP chamado `rebano-integracao-contagem.zip` com somente os arquivos que o projeto Rebano precisa criar ou modificar, organizados em:

```text
CRIAR/
MODIFICAR/
GUIA_INTEGRACAO_REBANO.md
```

Siga primeiro este README na máquina da contagem e depois o guia do ZIP do Rebano na outra máquina.
