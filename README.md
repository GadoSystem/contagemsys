# Sistema de Contagem em Tempo Real — Versão 3

Sistema de visão computacional para **detecção, rastreamento e contagem direcional em tempo real** usando câmera/webcam, Ultralytics YOLO, trackers e FastAPI.

A V3 foi criada para reduzir os principais erros observados em testes com pessoas e preparar o projeto para a futura contagem de bovinos.

## O que mudou na V3

- contagem por **duas fronteiras / três zonas**, em vez de uma linha única;
- sequência obrigatória para contar: `RIGHT -> CENTER -> LEFT`;
- uso do **bottom-center** da bounding box como ponto de passagem;
- estabilidade mínima de zona antes de aceitar a transição;
- mesmo `track_id` não é contabilizado duas vezes;
- retorno `LEFT -> CENTER -> RIGHT` é registrado sem somar no total;
- ROI configurável para processar somente a região útil da câmera;
- configuração central em `config.yaml`;
- persistência dos eventos em SQLite;
- sessões de contagem;
- snapshot e clipe de evidência em cada passagem;
- buffer de câmera que mantém somente o frame mais recente;
- benchmark de trackers e precisão de contagem;
- suíte de vídeos com `ground_truth.json`;
- exportação para OpenVINO e ONNX;
- novos endpoints de sessões/eventos;
- 10 testes automatizados da lógica principal.

---

# Como funciona a nova contagem

A imagem é dividida horizontalmente em três zonas:

```text
LEFT              CENTER / GATE               RIGHT
 |                     |                         |
 |                     |                         |
 +---------------------+-------------------------+
```

Para uma entidade ser contabilizada ela precisa completar:

```text
RIGHT -> CENTER -> LEFT = +1
```

O sentido inverso:

```text
LEFT -> CENTER -> RIGHT = retorno, não soma
```

Se ocorrer:

```text
RIGHT -> CENTER -> RIGHT
```

não existe contagem.

Isso reduz falsos positivos causados por pequenas oscilações da bounding box perto de uma única linha.

## Ponto usado para medir a passagem

A V3 não usa o centro completo da bounding box. Ela usa:

```text
              bounding box
        +---------------------+
        |                     |
        |      entidade       |
        |                     |
        +----------●----------+
                   ^
              bottom-center
```

Cálculo:

```python
anchor_x = (x1 + x2) / 2
anchor_y = y2
```

Para bovinos em corredor/mangueira, esse ponto tende a representar melhor a posição do animal no chão.

---

# Estrutura

```text
contagemsys/
├── main.py
├── api.py
├── camera_stream.py
├── config.py
├── config.yaml
├── counting.py
├── evidence.py
├── persistence.py
├── state.py
├── benchmark.py
├── benchmark_suite.py
├── export_openvino.py
├── export_onnx.py
├── tracker_bytetrack.yaml
├── tracker_botsort_reid.yaml
├── requirements.txt
├── data/
├── eventos/
└── tests/
    ├── ground_truth.json
    ├── test_gate_counter.py
    ├── test_persistence.py
    ├── test_state.py
    └── videos/
```

---

# 1. Requisitos

Recomendado:

- Windows 10 ou Windows 11;
- VS Code;
- Python 3.12;
- webcam/câmera;
- internet na primeira instalação e para baixar o modelo YOLO.

Verifique:

```bash
python --version
```

---

# 2. Criar e ativar o ambiente virtual

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

# 3. Instalar dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

A V3 usa uma versão atual do Ultralytics para suportar os trackers modernos disponíveis na documentação atual.

Teste:

```bash
python -c "import cv2, ultralytics, fastapi, yaml; print('Dependencias OK')"
```

---

# 4. Configuração principal

Agora as configurações ficam em:

```text
config.yaml
```

Configuração padrão para testes com pessoas:

```yaml
video:
  source: 0

model:
  path: "yolo26n.pt"
  classes: [0]
  confidence: 0.35
  imgsz: 416
  tracker: "tracker_bytetrack.yaml"
```

Classe COCO usada nos testes:

```text
0 = person
19 = cow
```

Não mude para bovino antes de validar a contagem com pessoas.

---

# 5. Configurar as duas fronteiras

Em `config.yaml`:

```yaml
gate:
  left_x: 0.42
  right_x: 0.58
  stable_frames: 2
```

Esses valores são proporcionais à largura da ROI/imagem.

Exemplo:

```text
0.0          0.42        0.58          1.0
 |------------|-----------|-------------|
 LEFT            CENTER          RIGHT
```

Se o corredor estiver mais estreito, aproxime as duas linhas.

---

# 6. Ativar ROI

Se apenas uma parte da câmera interessa, habilite:

```yaml
roi:
  enabled: true
  x1: 0.10
  y1: 0.20
  x2: 0.90
  y2: 0.90
```

Os valores vão de `0.0` até `1.0`.

A ROI reduz cenário inútil e pode diminuir falsos positivos e custo de inferência.

---

# 7. Executar

```bash
python main.py
```

Abra:

```text
http://127.0.0.1:8000/docs
```

A janela da câmera também será aberta.

Para sair:

```text
Q
```

---

# 8. Teste principal

Faça a sequência:

```text
RIGHT -> CENTER -> LEFT
```

Esperado:

```text
CONTADOS: 1
```

Depois volte:

```text
LEFT -> CENTER -> RIGHT
```

Esperado:

```text
CONTADOS: 1
RETORNOS: 1
```

---

# 9. Casos que devem ser testados

- virar parado;
- mover braços;
- agachar;
- chegar perto do gate e voltar;
- atravessar lentamente;
- atravessar rapidamente;
- duas pessoas separadas;
- duas pessoas próximas;
- uma pessoa ocultando parcialmente outra;
- sair do enquadramento e voltar;
- caminhar no sentido inverso.

---

# 10. API / Swagger

## Health

```http
GET /health
```

## Contagem atual

```http
GET /contagem/atual
```

Exemplo:

```json
{
  "total_contado": 4,
  "animais_no_frame_agora": 1,
  "retornos_esquerda_para_direita": 1,
  "direcao_contada": "direita_para_esquerda",
  "fps_ia": 18.2,
  "fps_camera": 29.8,
  "latencia_ia_ms": 51.3,
  "sistema_rodando": true,
  "session_id": 3,
  "tracker": "tracker_bytetrack.yaml",
  "modelo": "yolo26n.pt"
}
```

## Eventos da sessão atual

```http
GET /contagem/eventos
```

## Sessões anteriores

```http
GET /contagem/sessoes
```

## Zerar/iniciar nova sessão

```http
POST /contagem/resetar
```

---

# 11. Banco SQLite

O banco padrão fica em:

```text
data/contagem.db
```

Cada evento guarda:

- sessão;
- `track_id`;
- timestamp;
- direção;
- se foi contabilizado;
- confiança;
- frame;
- path do snapshot;
- path do clipe.

---

# 12. Evidências de passagem

Por padrão:

```yaml
evidence:
  enabled: true
  save_snapshot: true
  save_clip: true
  pre_seconds: 3.0
  post_seconds: 3.0
```

Os arquivos são gravados em:

```text
eventos/YYYY-MM-DD/
```

O clipe usa um pequeno buffer em RAM com alguns segundos anteriores ao evento e termina alguns segundos depois.

A gravação ocorre fora do loop principal para reduzir impacto no FPS.

Se o computador for fraco, desligue clips:

```yaml
evidence:
  save_clip: false
```

---

# 13. Trocar tracker

Padrão:

```yaml
tracker: "tracker_bytetrack.yaml"
```

Para testar FastTrack:

```yaml
tracker: "fasttrack.yaml"
```

Para BoT-SORT padrão:

```yaml
tracker: "botsort.yaml"
```

Para o arquivo do projeto com ReID:

```yaml
tracker: "tracker_botsort_reid.yaml"
```

A documentação atual do Ultralytics lista ByteTrack, BoT-SORT, OC-SORT, Deep OC-SORT, FastTrack e TrackTrack como opções integradas de tracking.

---

# 14. Benchmark de um vídeo

Grave um vídeo cujo número real de passagens você conhece.

Exemplo:

```bash
python benchmark.py --video tests/videos/01_uma_pessoa.mp4 --expected 1
```

Por padrão são comparados:

```text
ByteTrack
FastTrack
BoT-SORT
```

Saída:

```text
benchmark_results.csv
```

Exemplo de resultado:

```text
tracker,esperado,contado,erro_absoluto,precisao_contagem_pct,fps
tracker_bytetrack.yaml,50,49,1,98.0,22.4
fasttrack.yaml,50,50,0,100.0,20.8
botsort.yaml,50,50,0,100.0,15.6
```

---

# 15. Benchmark automático de vários vídeos

Coloque os vídeos em:

```text
tests/videos/
```

Edite:

```text
tests/ground_truth.json
```

Exemplo:

```json
{
  "01_uma_pessoa.mp4": 1,
  "02_duas_pessoas.mp4": 2,
  "03_retorno.mp4": 1
}
```

Execute:

```bash
python benchmark_suite.py
```

Resultado:

```text
benchmark_suite_results.csv
```

Essa métrica é mais importante para o projeto do que olhar somente mAP, pois mede diretamente o erro final da contagem.

---

# 16. Testes automatizados

Execute:

```bash
python -m unittest discover -s tests -v
```

A V3 inclui testes para:

- passagem correta;
- retorno;
- desistência no centro;
- track nascendo no centro;
- bloqueio de contagem duplicada;
- bottom-center;
- limpeza de tracks antigos;
- estado compartilhado;
- reset;
- persistência SQLite.

---

# 17. Melhorar FPS

Primeiro teste `imgsz`:

```yaml
imgsz: 416
```

Depois:

```yaml
imgsz: 320
```

Compare `FPS IA` e a precisão da contagem.

Também é possível processar uma inferência a cada N frames:

```yaml
video:
  inference_stride: 2
```

Use com cuidado: valores muito altos podem fazer uma entidade atravessar a zona central entre duas inferências e a máquina de estados não aceitar a passagem.

Para produção, prefira primeiro otimizar modelo/backend/ROI antes de aumentar demais o stride.

---

# 18. OpenVINO

Para CPU Intel:

```bash
pip install openvino
python export_openvino.py
```

Depois altere `model.path` para a pasta exportada.

---

# 19. ONNX

```bash
python export_onnx.py
```

Use o arquivo exportado para comparar desempenho em runtimes compatíveis.

---

# 20. Migrar para bovinos

Primeiro teste rápido usando COCO:

```yaml
model:
  classes: [19]
```

Para produção, use modelo próprio treinado com bovinos reais e o ambiente final da câmera.

Exemplo:

```yaml
model:
  path: "best.pt"
  classes: [0]
```

O dataset deve conter variedade de:

- raças;
- frente/costas/lateral;
- bovinos juntos;
- oclusão;
- sol e sombra;
- poeira/lama;
- dia/fim de tarde;
- câmera parcialmente suja;
- animais cortados nas bordas;
- pessoas, cavalos, cães, tratores e estruturas como negativos.

---

# 21. Sequência recomendada antes de colocar em produção

1. Rode os testes automatizados.
2. Valide com uma pessoa.
3. Valide retorno.
4. Valide duas pessoas próximas.
5. Valide oclusão.
6. Grave vídeos de teste.
7. Preencha `ground_truth.json`.
8. Rode `benchmark_suite.py`.
9. Escolha o tracker baseado em erro de contagem e FPS.
10. Ative ROI na câmera final.
11. Migre para bovinos COCO apenas para protótipo.
12. Treine `best.pt` próprio.
13. Refaça o benchmark com vídeos reais de bovinos.
14. Só então integre a contagem definitiva ao sistema de rebanho.

---

# Comando rápido depois da instalação

Git Bash:

```bash
source venv/Scripts/activate
python main.py
```

PowerShell:

```powershell
.\venv\Scripts\Activate.ps1
python main.py
```

Swagger:

```text
http://127.0.0.1:8000/docs
```
