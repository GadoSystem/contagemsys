# ContagemSys V5 — Monitoramento e contagem inteligente de rebanhos

O **ContagemSys** é um sistema de visão computacional que recebe imagens de câmeras, identifica e acompanha objetos em movimento e registra a passagem deles por uma região de contagem. Ele possui uma **API e um painel web** e foi integrado ao **Rebano**, sistema de gestão agropecuária, para que cada usuário visualize apenas as câmeras vinculadas à sua conta.

O desenvolvimento é direcionado à contagem de **bovinos**, mas a configuração de testes atual utiliza **pessoas**. O comportamento com bovinos deve ser validado em campo, com modelo e classes adequados.

> **Para instalar e executar os dois projetos, consulte [LEIA-ME.txt](LEIA-ME.txt).** Este README apresenta a arquitetura, tecnologias, funcionalidades e principais configurações.

## 1. Visão geral

O ContagemSys foi desenvolvido para auxiliar no acompanhamento de movimentações por câmeras, com contagem automática e consulta remota dos resultados.

Principais recursos:

- **Detecção por IA:** YOLO detecta objetos nas imagens capturadas.
- **Rastreamento:** ByteTrack acompanha as detecções entre frames, ajudando a evitar contagens repetidas.
- **Contagem direcional:** a passagem da direita para a esquerda incrementa a contagem; o trajeto contrário pode ser tratado como retorno.
- **Múltiplas fontes de vídeo:** webcams USB/integradas, dispositivos virtuais (como Iriun, quando disponíveis) e câmeras IP com streams compatíveis.
- **Descoberta de fontes:** verifica câmeras locais e pode procurar câmeras IP via ONVIF; atualiza a seção `video.cameras` do `config.yaml` antes de iniciar.
- **Exibição local e remota:** janelas OpenCV, painel web próprio e exibição via Rebano.
- **Informações por câmera:** total contado, detecções no frame, retornos, FPS e latência da IA, conforme disponibilidade.
- **Histórico:** registros de eventos e estatísticas no banco SQLite local do ContagemSys.
- **Controle de acesso:** o administrador associa câmeras ao `Usuario.Id` do Rebano e cada usuário visualiza apenas as autorizadas.

## 2. Arquitetura e integração

```text
Webcam USB / câmera integrada / Iriun / câmera IP
                       |
                       v
             ContagemSys (Python)
           OpenCV + YOLO + ByteTrack
                       |
          +------------+------------+
          |                         |
    Painel próprio                 FastAPI
 localhost:8000               localhost:8000
                                    |
                             API HTTP / MJPEG
                                    |
                           Backend do Rebano
                         ASP.NET Core / porta 5148
                                    |
                            Frontend do Rebano
                             React + Vite
```

**Como funciona a autorização:**

1. O Rebano cadastra e autentica os usuários.
2. O administrador do ContagemSys abre `/admin` e vincula cada câmera a um usuário do Rebano.
3. O ContagemSys autentica o usuário com **CPF e senha** da conta do Rebano: o CPF é validado (11 dígitos, com ou sem máscara) e enviado ao `POST /api/auth/login` do Rebano, que verifica a senha. O banco do Rebano não é acessado pelo ContagemSys.
4. No login, o ContagemSys guarda **somente em memória do servidor** o token do Rebano daquele usuário e consulta `GET /Fazenda/ObterTodos` e `GET /Fazenda/{id}/Cameras` para agrupar o painel por fazenda (detalhes na seção 8.1).
5. O backend do Rebano consulta as câmeras autorizadas e disponibiliza os dados e o vídeo ao usuário logado.
6. Cada câmera é consultada pelo identificador (`camera_1`, `camera_2`, etc.). Se a ordem física dos dispositivos mudar, confira os vínculos no painel administrativo.

**Importante:** nesta arquitetura, as webcams locais são capturadas pelo computador que executa o ContagemSys. Ter uma câmera USB conectada em outro computador não faz com que ela apareça automaticamente no servidor remoto; isso exigiria um agente de captura/encaminhamento naquele computador ou uma fonte de rede acessível.

## 3. Tecnologias utilizadas

### ContagemSys

| Tecnologia | Utilização |
| --- | --- |
| Python | Aplicação principal, processamento e integração |
| OpenCV | Abertura de câmeras, captura e renderização dos frames |
| Ultralytics YOLO | Detecção de objetos por inteligência artificial |
| ByteTrack | Rastreamento de objetos entre frames |
| PyTorch | Execução do modelo de IA |
| FastAPI + Uvicorn | API HTTP, autenticação e transmissão de vídeo |
| MJPEG / JPEG | Exibição remota de frames em tempo real |
| SQLite | Persistência local de eventos e contagens |
| PyYAML | Leitura e atualização de `config.yaml` |
| HTTPX + PyJWT | Comunicação com o Rebano e autenticação |
| ONVIF / RTSP | Localização e acesso a câmeras IP compatíveis |

### Rebano (projeto integrado)

| Tecnologia | Utilização |
| --- | --- |
| C# + ASP.NET Core (.NET 10) | API backend e regras de negócio |
| Entity Framework Core | Persistência e migrações do banco |
| PostgreSQL | Banco de dados dos usuários e da gestão agropecuária |
| JWT | Autenticação e autorização do usuário |
| React + TypeScript | Interface web |
| Vite | Ambiente de desenvolvimento e compilação do frontend |
| Tailwind CSS | Estilização das páginas |
| Leaflet / Chart.js | Mapas e visualizações de dados |

O Rebano também gerencia informações como fazendas, animais, piquetes, movimentações, equipamentos, plantações e relatórios. A integração com o ContagemSys acrescenta o acompanhamento das câmeras autorizadas.

## 4. Organização dos arquivos principais

```text
contagemsys/
├── main.py                  # Inicialização, câmeras e processamento
├── api.py                   # Endpoints FastAPI
├── auth.py                  # Autenticação e integração
├── camera_discovery.py      # Descoberta/validação de fontes
├── camera_stream.py         # Captura e entrega dos frames
├── listar_cameras.py        # Diagnóstico das fontes de vídeo
├── counting.py              # Lógica de contagem
├── persistence.py           # Eventos e armazenamento SQLite
├── web_ui.py                # HTML das páginas de login, painel e admin
├── static/                  # CSS, JavaScript e logo do painel (sem CDN)
├── config.yaml              # Câmeras, IA, streaming e desempenho
├── .env                     # Endereços e segredos (não publicar)
├── .env.example             # Modelo de configuração
├── requirements.txt         # Dependências Python
├── data/contagem.db         # Banco local, após inicialização
├── README.md                # Documentação do sistema
└── LEIA-ME.txt              # Como executar os dois projetos
```

## 5. Câmeras e descoberta automática

Ao executar `python main.py`, com `discovery.enabled: true`, o sistema tenta:

1. Examinar as fontes de vídeo locais usando os backends compatíveis com o sistema operacional (no Windows, DirectShow/Media Foundation).
2. Validar se as fontes entregam imagens. A descoberta também avalia o funcionamento simultâneo para reduzir conflitos entre webcams.
3. Buscar dispositivos IP que anunciam **ONVIF** na rede local e testar streams acessíveis.
4. Testar endereços RTSP/HTTP informados em `discovery.ip_streams`.
5. Atualizar `video.cameras` no `config.yaml`, preservando, sempre que possível, os identificadores das câmeras já cadastradas.

**Limitações:** nem toda câmera IP anuncia ONVIF, algumas exigem credenciais e certas câmeras virtuais podem apresentar telas estáticas mesmo sem imagem real. Dispositivos USB podem compartilhar drivers/controladores e não funcionar simultaneamente. A descoberta automática não garante acesso a toda câmera existente.

Comandos úteis (na pasta do ContagemSys e com o ambiente virtual ativo):

```bash
python main.py                    # Descobre câmeras e inicia o sistema
python main.py --discover-only    # Apenas descobre e atualiza o YAML
python main.py --no-discovery     # Usa a lista de fontes já configurada
python listar_cameras.py --backend dshow --max 6 --preview
```

Para câmera IP sem descoberta ONVIF, informe a URL de stream fornecida pelo fabricante:

```yaml
discovery:
  ip_streams:
    - name: "Câmera do curral"
      url: "rtsp://192.168.1.50:554/stream1"
      username_env: "CAMERA_IP_USER"
      password_env: "CAMERA_IP_PASS"
```

As variáveis `CAMERA_IP_USER` e `CAMERA_IP_PASS` são definidas no `.env`; não publique senhas nos arquivos versionados. A URL acima é **um exemplo**, não um endereço universal.

## 6. Processamento e contagem

- **Modelo:** configurado em `model.path` (nesta versão, `yolo26n.pt`).
- **Classe de teste:** `model.classes: [0]` seleciona **pessoas** nos modelos baseados em COCO. A classe `19` corresponde a bovinos no conjunto COCO, mas sua adequação precisa ser validada com vídeos reais.
- **Sentido de contagem:** `gate.count_direction: right_to_left`.
- **Região e linhas:** configuradas em `roi` e `gate` dentro de `config.yaml`.
- **Fluidez:** a captura e o vídeo são separados das inferências YOLO; por isso, `api.stream_fps`, `display.preview_fps` e `video.inference_fps` podem ter valores diferentes.
- **Evidências:** gravações e snapshots dependem de `evidence.enabled` e das demais opções de evidência.

Na execução local, se `app.show_window: true`, as janelas do OpenCV são abertas. Com uma dessas janelas em foco, **Q** solicita o encerramento das câmeras e da API; **Ctrl+C** no terminal também encerra.

## 7. Configuração da integração com o Rebano

O ContagemSys lê o arquivo `.env` (use `.env.example` como modelo):

```env
REBANO_API_URL=http://localhost:5148
CONTAGEM_JWT_SECRET=GERE_UM_SEGREDO_ALEATORIO
CONTAGEM_INTEGRATION_KEY=USE_A_MESMA_CHAVE_NOS_DOIS_SISTEMAS
CONTAGEM_ADMIN_USER=admin
CONTAGEM_ADMIN_PASSWORD=DEFINA_UMA_SENHA_FORTE
```

No backend do Rebano, em `BackEnd/Rebano/appsettings.json`, configure:

```json
"ContagemApi": {
  "BaseUrl": "http://localhost:8000",
  "IntegrationKey": "USE_A_MESMA_CHAVE_NOS_DOIS_SISTEMAS"
}
```

Esse trecho é parte de um JSON maior: **não substitua o arquivo inteiro**. A chave `IntegrationKey` do Rebano deve ser exatamente igual à `CONTAGEM_INTEGRATION_KEY` do ContagemSys. Use segredos reais e fortes, mantidos fora do controle de versão. Em máquinas diferentes, substitua `localhost` pelos endereços acessíveis de cada servidor.

## 8. Interfaces e endereços locais

| Serviço | Endereço padrão |
| --- | --- |
| Login ContagemSys | `http://localhost:8000/` |
| Painel do usuário ContagemSys (câmeras por fazenda, grade ao vivo, visão ampliada com métricas) | `http://localhost:8000/painel` |
| Administração ContagemSys | `http://localhost:8000/admin` |
| Swagger ContagemSys | `http://localhost:8000/docs` |
| Saúde ContagemSys | `http://localhost:8000/health` |
| API do Rebano | `http://localhost:5148` |
| Swagger Rebano | `http://localhost:5148/swagger` |
| Frontend Rebano (teste recomendado) | `http://localhost:5173` |
| Câmeras no Rebano | `http://localhost:5173/Cameras` |

A porta do frontend é **5173 quando iniciado conforme o LEIA-ME.txt**. O comando `npm run dev` sem parâmetro usa a porta **80** definida no `package.json` atual.

### 8.1. Painel do usuário e agrupamento por fazenda

- **Arquivos:** o HTML fica em `web_ui.py`; estilos, scripts e logo ficam em `static/` (`app.css`, `login.js`, `painel.js`, `logo-rebano.svg`), servidos pelo FastAPI em `/static`. Nada é carregado da internet (sem CDN nem fontes externas).
- **Grade:** cada bloco atualiza a imagem a partir do `frame.jpg` já produzido pelo worker (cerca de 1 quadro/s). O MJPEG completo só é aberto na visão ampliada, uma conexão por vez. Nenhuma captura extra é criada no servidor.
- **Tela cheia:** botão no cabeçalho (Fullscreen API). Na visão ampliada, **Esc** volta à grade e **← / →** trocam de câmera.
- **Fazendas:** uma câmera do ContagemSys aparece na fazenda cujo cadastro de câmera no Rebano tem **Identificação igual ao id da câmera** (`camera_1`, `camera_2`... — sem diferenciar maiúsculas/minúsculas). Câmeras autorizadas sem correspondência vão para **"Outras câmeras"**; fazendas sem câmeras não aparecem. A autorização continua sendo o vínculo do `/admin`: o Rebano só define o agrupamento.
- **Como cadastrar no Rebano:** no frontend do Rebano, abra a fazenda e cadastre a câmera (ou use `POST /Camera/Criar`) com `identificacao` igual ao id mostrado em `/admin` (ex.: `camera_1`) e `fazendaId` da fazenda desejada. A fazenda precisa estar vinculada ao usuário que fará login.
- Se o ContagemSys for reiniciado, o token do Rebano em memória se perde: o painel continua funcionando, mostra todas as câmeras em "Outras câmeras" e avisa para sair e entrar novamente.

## 9. Testes, limitações e segurança

Execute os testes automatizados do ContagemSys:

```bash
python -m unittest discover -s tests -v
```

Valide também as câmeras reais, os vínculos de usuário e a exibição no Rebano. Os testes automatizados **não comprovam a estabilidade** de todas as webcams, câmeras IP ou redes.

**Para produção:** substitua todas as credenciais de teste, use HTTPS e uma configuração de CORS/rede restrita, não exponha streams nem chaves de integração publicamente, e dimensione CPU/GPU, memória e armazenamento para o número de câmeras. Uma hospedagem compartilhada convencional não é adequada ao processamento contínuo por YOLO.

---

**Próxima etapa:** [LEIA-ME.txt](LEIA-ME.txt) — instalação e execução detalhadas de PostgreSQL, backend/frontend do Rebano e ContagemSys no Windows com VS Code e Git Bash.
