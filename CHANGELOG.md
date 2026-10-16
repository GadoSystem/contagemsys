# Changelog

## V5.2.0 — nova interface de login e painel

- login e painel redesenhados (tema escuro "centro de monitoramento", identidade do Rebano), sem CDN, fontes externas ou etapa de build;
- estilos, scripts e logo em `static/` (servidos em `/static`); o logo do Rebano foi movido para `static/logo-rebano.svg`;
- painel com abas por fazenda (online/total), resumo (câmeras online, total contado, retornos), grade adaptável, relógio e tela cheia;
- grade usa `frame.jpg` periódico; MJPEG apenas na visão ampliada; bloco "Sem sinal — tentando reconectar" com reconexão automática;
- visão ampliada com métricas em cartões, histórico, eventos recentes e JSON bruto recolhível;
- novo `GET /api/minhas-fazendas`: agrupa as câmeras autorizadas pela fazenda do Rebano (`Camera.Identificacao` = id da câmera), consultada com o token do Rebano do próprio usuário mantido só em memória do servidor;
- testes de agrupamento por fazenda (com e sem correspondência) e de arquivos estáticos.

## V5.1.0 — login por CPF e painel com vídeo + JSON

- login web do ContagemSys passa a usar CPF + senha (CPF validado antes de consultar o Rebano);
- a senha continua verificada pelo `POST /api/auth/login` do Rebano, que já aceita CPF; nenhum acesso ao banco do Rebano;
- só é aceita a conta cujo CPF é o informado (o Rebano também tenta o número como telefone);
- mensagens distintas para campo vazio e CPF inválido; "CPF ou senha incorretos" sem indicar qual dos dois;
- `/painel`: lista das câmeras do usuário, vídeo MJPEG somente da câmera selecionada (uma conexão por vez), estados de carregamento/indisponível e JSON de `/detalhes`;
- testes de login por CPF e de acesso negado à câmera de outro usuário.

## V5.0.0 — login e vínculo câmera/usuário

- login web do ContagemSys validado pelo backend do Rebano;
- painel do usuário mostra somente as câmeras vinculadas ao seu `Usuario.Id`;
- tela `/admin` para vínculo manual câmera -> usuário;
- vínculos persistidos no SQLite;
- integração servidor-a-servidor protegida por `X-Integration-Key`;
- frontend web simples para teste de login, câmeras e contagem;
- endpoints próprios para o backend do Rebano consumir as câmeras do usuário logado.

## V4.0.0

- suporte a múltiplas câmeras simultâneas;
- tracker/contador/estado/sessão/evidência independentes por câmera;
- configuração `video.cameras` com overrides individuais de ROI/gate/stride;
- API autenticada por `X-API-Key` via variável `CONTAGEM_API_KEY`;
- host padrão `0.0.0.0` para consumo na rede local;
- endpoints `/cameras`, `/frame.jpg` e `/stream.mjpg`;
- contagem agregada entre câmeras;
- persistência com `camera_id` e migração automática do SQLite V3;
- `.env.example` e proteção do `.env` no `.gitignore`;
- utilitário `listar_cameras.py`;
- testes atualizados para multi-câmera.

## V4.1 - desempenho multi-camera

- separada captura/renderização da inferência YOLO;
- vídeo local não fica mais bloqueado pelo tempo de inferência;
- coordenador global limita inferências simultâneas e evita saturação de CPU;
- PyTorch usa quantidade controlada de threads em CPU;
- webcams usam 640x480, MJPG e backend otimizado por padrão;
- stream da API usa JPEG menor e sem sidebar por padrão;
- evidências reduzidas para 12 FPS e janela de 2s para diminuir cópias/escrita;
- métricas adicionais de fila de IA, resolução e FPS alvo;
- integração Rebano passa a usar MJPEG contínuo em vez de polling ~1,5 FPS.
