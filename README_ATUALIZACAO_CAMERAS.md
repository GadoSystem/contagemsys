# Atualização de câmeras — ContagemSys + Rebano

## O que foi ajustado

1. `listar_cameras.py` verifica índices pelo backend **DirectShow** (o mesmo do `config.yaml`) e permite confirmar cada webcam com imagem em movimento via `--preview`. O índice do scanner antigo usava outro backend e podia apontar para outra fonte, inclusive webcam virtual.
2. `camera_stream.py`, `main.py` e `state.py` detectam ausência de quadros recentes, limpam o JPEG antigo, marcam a câmera como indisponível e tentam reconectar. `main.py` também evita gerar janelas/sidebars no servidor sem necessidade.
3. O React usa uma requisição de JPEG por vez por câmera, com cancelamento, limite de tempo e descarte de imagens anteriores. Evita conexões MJPEG prolongadas que podem bloquear outras chamadas HTTP/1.1; a API MJPEG permanece para clientes que precisarem dela.
4. `persistence.py` fecha corretamente as conexões SQLite e fornece estatísticas por câmera, por dia local e histórico total.
5. O Rebano ganhou a rota protegida `/Cameras/:cameraId` e o botão **Detalhes da câmera** abaixo de cada transmissão. Mostra contados hoje, histórico, sessão, pessoas/bois no frame conforme o modelo ativo, retornos, FPS, latência, datas, últimos eventos.

## Como instalar sem apagar o banco

**IMPORTANTE:** os ZIPs contêm somente arquivos modificados e novos. Faça backup do projeto e extraia cada pacote na **raiz do projeto correspondente**, mantendo a estrutura de pastas. Substitua os arquivos quando solicitado. Não apague `.env`, `appsettings.json`, banco SQLite (`data/contagem.db`) ou PostgreSQL.

### ContagemSys

No Git Bash, dentro da pasta do projeto:

```bash
source venv/Scripts/activate
python listar_cameras.py --backend dshow --max 5 --preview
```

Para cada câmera candidata, **mova a mão em frente da lente**. Pressione **S** para confirmar que a imagem e o dispositivo físico são reais; **N** para ignorar; **ESC** para sair. Mantenha apenas os índices confirmados em `config.yaml` sob `video.cameras`, com `enabled: true`. O ZIP inclui um perfil inicial com índices 0 e 1; **não ative `camera_3` sem confirmar o índice 2 pelo DirectShow**. Índices podem mudar ao trocar as portas USB.

Para desempenho em CPU, o perfil utiliza 640×480, MJPG, 15 FPS solicitado, 4 FPS IA por câmera, 6 FPS JPEG, `show_window: false` e inferências YOLO sequenciais. Isso favorece estabilidade, não garante 15 FPS reais em hardware limitado.

Depois:

```bash
python main.py
```

Confira `http://localhost:8000/health` e `/admin`. O status só deve ficar online quando há um JPEG **recente**. Se alguma webcam perder sinal, o ContagemSys tentará recuperá-la e o Rebano deixará de mostrar quadros antigos.

### Backend Rebano

Copie os arquivos do pacote Rebano e reinicie a API a partir de `BackEnd/Rebano`:

```bash
dotnet restore
dotnet build
dotnet run --launch-profile http
```

Mantenha `ContagemApi:IntegrationKey` em `appsettings.json` idêntica a `CONTAGEM_INTEGRATION_KEY` no `.env` do ContagemSys. Nenhuma migração EF Core é necessária para as métricas: o histórico é consultado no SQLite do ContagemSys.

### Frontend Rebano

Em `FrontEnd`, use Node.js 24 LTS (ou versão compatível com Vite 8 e react-router 8):

```bash
npm ci
npm run build
npm run dev -- --port 5173
```

Entre no Rebano, vá a **Câmeras**, confira os feeds. Clique em **Detalhes da câmera** para consultar métricas e eventos. Um mesmo usuário só acessa dados das câmeras vinculadas a ele.

## Validação e limitações

- Python: `python -m unittest discover -s tests -v` — 16 testes passaram aqui, incluindo autorização dos detalhes, histórico e limpeza de frame antigo.
- Neste ambiente não havia SDK .NET nem dependências frontend completas, portanto não foi possível compilar o Rebano ou testar webcams físicas: execute `dotnet build` e `npm run build` no seu PC.
- Scanner detecta fontes que retornam quadros; **apenas o teste visual confirma qual webcam física é qual**, pois câmeras virtuais também podem emitir imagens válidas.
- O histórico antigo **não é convertido automaticamente em bovinos**. Com `model.classes: [0]` você ainda conta **pessoas**; para bovinos use classe COCO `19` após testes reais e ajuste de modelo.
- Não inclui o agente remoto `.exe` de instalação em fazendas. Continua sendo teste local/de rede do ContagemSys.
