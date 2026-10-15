# ContagemSys — descoberta automática de câmeras

Atualização para **Windows/VS Code/Git Bash**, mantendo FastAPI, YOLO e o fluxo com o Rebano.

## 1. Instalação (uma vez)

Com o ambiente virtual do ContagemSys ativado:

```bash
python -m pip install -r requirements.txt
```

O pacote `onvif-zeep` é usado para descobrir o stream RTSP de câmeras IP que anunciam ONVIF. Caso a instalação falhe, procure o erro no terminal. A captura de webcams locais não depende de ONVIF.

## 2. Executar normalmente

**Feche Teams, Zoom, OBS, aplicativo Câmera e qualquer outro processo que esteja usando as webcams.**

```bash
python main.py
```

O sistema, antes de iniciar o YOLO, faz:

1. Busca câmeras USB, internas e virtuais (Iriun, OBS, etc.) nos índices 0 até 5, pelo DirectShow e Media Foundation no Windows; escolhe o backend que entregar **mais câmeras válidas**, sem misturar índices de dois backends. Isso evita mapear duas vezes o mesmo dispositivo sob backends diferentes.
2. Testa frames recentes; uma webcam virtual desconectada com tela congelada pode ser desativada. Se a cena real for perfeitamente estática, ajuste `discovery.webcam.accept_static_frames: true`.
3. Envia uma consulta de descoberta ONVIF por multicast na **rede local** e tenta obter os fluxos RTSP (exige serviço ONVIF ativo e, em alguns modelos, usuário/senha).
4. Testa URLs adicionais RTSP/HTTP cadastradas em `discovery.ip_streams`.
5. Atualiza automaticamente **apenas a seção `video.cameras`** de `config.yaml`, mantendo os identificadores previamente cadastrados, `gate`, `model`, contagem, parâmetros globais e outras configurações.
6. Inicia a API e as janelas locais de visualização das câmeras ativas.

**Clique em qualquer janela de vídeo e pressione `Q` para encerrar a API e todas as câmeras.** `Ctrl+C` no terminal também encerra.

Para apenas buscar dispositivos e editar o YAML, sem iniciar o servidor:

```bash
python main.py --discover-only
```

Ou rode diretamente pelo scanner, sem iniciar o YOLO:

```bash
python listar_cameras.py --sync
```

Para usar a lista manual atual e pular a descoberta naquele início:

```bash
python main.py --no-discovery
```

## 3. Câmeras IP sem ONVIF

A detecção automática pela rede depende de ONVIF/WS-Discovery ativo, permissões da rede e acesso ao stream. O sistema **não pode descobrir universalmente todo dispositivo IP** (algumas câmeras não anunciam ONVIF ou usam protocolos proprietários).

Abra `config.yaml`, localize `discovery.ip_streams` e adicione o endereço **que sua câmera fornece**:

```yaml
  ip_streams:
    - name: "Portão da fazenda"
      url: "rtsp://192.168.1.50:554/stream1"
      username_env: "CAMERA_IP_USER"
      password_env: "CAMERA_IP_PASS"
```

Adicione credenciais ao `.env` (sem colocar senha na URL do YAML):

```env
CAMERA_IP_USER=usuario_da_camera
CAMERA_IP_PASS=senha_da_camera
ONVIF_USERNAME=usuario_onvif
ONVIF_PASSWORD=senha_onvif
```

Ative ONVIF no painel da câmera, se o modelo suportar. A descoberta multicast normalmente só funciona na mesma rede/sub-rede; VLAN, Wi-Fi isolado e firewall podem bloquear UDP 3702. Não é necessário adicionar URL de webcam USB ou Iriun que já esteja transmitindo.

## 4. Câmeras virtuais

- **Iriun instalado e transmitindo:** encontrado automaticamente como webcam do Windows, caso a captura esteja disponível.
- **Iriun não instalado:** nada do Iriun será adicionado.
- **Iriun instalado, mas sem telefone conectado:** o driver pode produzir uma imagem de aviso; a detecção pode ignorá-la como stream congelado. Se o aviso for animado, a validação automática não consegue ter certeza de que é uma imagem real. Confirme a origem no preview manual.
- **Dispositivo físico muito estático:** altere `accept_static_frames: true` para evitar falsos negativos.

Para diagnosticar visualmente índices (com o ContagemSys **desligado**):

```bash
python listar_cameras.py --backend dshow --max 6 --preview
```

## 5. IDs e o Rebano

A descoberta reutiliza `camera_1`, `camera_2` etc. quando a mesma fonte/índice é encontrada; fontes indisponíveis são mantidas no YAML com `enabled: false`, sem aparecer na API de câmeras ativas. Se um driver mudar a **ordem** dos dispositivos, os índices podem mudar de câmera física. Verifique os vínculos no `/admin` do ContagemSys após trocar equipamentos e reconectá-los.

## 6. Desempenho

- A thread de captura guarda somente o **frame mais recente**, sem fila crescente.
- O stream MJPEG e o processamento YOLO mantêm suas frequências separadas.
- `performance.max_concurrent_inferences: 1` evita múltiplas inferências pesadas simultâneas na CPU.
- Para uma máquina menos potente, experimente `video.width: 640`, `video.height: 480`, `api.stream_fps: 10`, `video.inference_fps: 2`.
- A descoberta completa acontece **na inicialização**, não durante cada frame, para não consumir CPU ou roubar dispositivos do processamento.

## 7. Diagnóstico

Se uma câmera não aparecer: pare o ContagemSys, verifique permissões da câmera no Windows e teste com o aplicativo Câmera. Se a fonte for IP, verifique URL, autenticação, rede, ONVIF e firewall. A descoberta de câmeras pode demorar alguns segundos conforme drivers e rede. Se nenhuma fonte passar na validação, a API continuará disponível sem câmeras, permitindo corrigir as conexões e reiniciar.
