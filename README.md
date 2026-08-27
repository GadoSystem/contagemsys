# Contagem de Rebanho em Tempo Real — versão 2

Este projeto foi reestruturado para resolver os dois problemas mais importantes da versão anterior:

1. **contagem duplicada por troca de ID do tracker**;
2. **vídeo lento/atrasado porque a IA não acompanha os FPS da câmera**.

A regra agora é: **um ID não é uma contagem**. O total só aumenta quando a trajetória cruza uma linha virtual no sentido **DIREITA → ESQUERDA**. Um cruzamento **ESQUERDA → DIREITA** é interpretado como retorno de algo já contado e não soma.

## Arquitetura

```text
webcam / RTSP
     │
     ├── thread de captura ──> mantém somente o frame mais novo
     │
     ├── thread da IA ───────> YOLO + tracker + trajetória + linha direcional
     │                             │
     │                             └── evento DIREITA -> ESQUERDA = +1
     │
     ├── janela OpenCV ──────> vídeo fluido + última detecção disponível
     │
     └── FastAPI ────────────> Swagger / contagem / eventos / reset
```

## Arquivos

```text
contagemsys/
├── main.py                    # câmera + IA + janela + API
├── camera_stream.py           # captura sem fila/lag
├── counting.py                # contador direcional e anti-duplicação
├── state.py                   # estado thread-safe e controle de sessão
├── api.py                     # endpoints FastAPI
├── tracker_bytetrack.yaml     # perfil rápido (padrão)
├── tracker_botsort_reid.yaml  # perfil mais robusto contra ID switch
├── export_openvino.py         # aceleração opcional para CPU Intel
├── requirements.txt
└── tests/
    └── test_directional_counter.py
```

## Instalação recomendada

Use **Python 3.12**.

### PowerShell / CMD

```bash
python -m venv venv
venv\Scripts\activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Git Bash

```bash
python -m venv venv
source venv/Scripts/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Teste:

```bash
python -c "import cv2, torch, ultralytics, fastapi; print('Dependencias OK')"
```

## Executar

```bash
python main.py
```

Acesse:

- Swagger: `http://localhost:8000/docs`
- contagem atual: `GET /contagem/atual`
- últimos cruzamentos: `GET /contagem/eventos`
- iniciar nova sessão: `POST /contagem/resetar`
- saúde da aplicação: `GET /health`

Na janela da câmera, pressione **Q** para encerrar.

---

# Como testar agora com pessoas

No topo de `main.py` deixe:

```python
FONTE_VIDEO = 0
MODELO = "yolo26n.pt"
CLASSES_ALVO = [0]  # person
```

A linha amarela fica no centro da imagem. Para somar 1:

```text
ESQUERDA       LINHA                    DIREITA
                                  pessoa começa aqui
                     <------------------
                        atravessa a linha
+1 somente nesse sentido
```

Se você andar **esquerda → direita**, o sistema registra um **retorno**, mas não soma. Se o mesmo ID voltar novamente da direita para a esquerda, ele continua bloqueado e não soma outra vez.

## Por que virar o corpo não deve mais aumentar o total

Na versão antiga havia algo parecido com:

```python
ids_unicos.add(track_id)
total = len(ids_unicos)
```

Se o tracker perdesse `ID 7` e recriasse você como `ID 12`, o total aumentava imediatamente.

Agora isso não existe. Um novo ID parado, girando ou andando do mesmo lado da linha não muda a contagem. Para gerar `+1`, a trajetória precisa:

1. existir por alguns frames;
2. ter deslocamento horizontal mínimo;
3. sair claramente do lado direito;
4. atravessar uma **zona morta** ao redor da linha;
5. chegar claramente ao lado esquerdo.

Essa histerese reduz contagem por tremedeira de bounding box.

---

# Trackers

## Padrão: ByteTrack ajustado

```python
TRACKER = str(BASE_DIR / "tracker_bytetrack.yaml")
```

É a primeira opção para CPU e para uma câmera fixa apontando para uma passagem. O arquivo foi ajustado para:

- manter tracks perdidos por mais tempo (`track_buffer`);
- permitir associação mais tolerante (`match_thresh`);
- aceitar detecções fracas para recuperar uma trajetória;
- exigir confiança maior para abrir um **novo** ID.

## Se continuar trocando muito o ID: BoT-SORT + ReID

Troque em `main.py`:

```python
TRACKER = str(BASE_DIR / "tracker_botsort_reid.yaml")
```

Esse perfil usa informação de aparência (ReID), por isso consegue recuperar melhor uma identidade depois de certas oclusões/mudanças. Em compensação, consome mais processamento.

Para começar, use ByteTrack. Só passe para ReID se a troca de ID estiver realmente causando falhas perto da linha.

---

# FPS e latência

O painel mostra três métricas diferentes:

- **FPS câmera**: quantos frames a webcam entrega;
- **FPS IA**: quantos frames por segundo o YOLO + tracker consegue analisar;
- **latência IA**: idade aproximada do frame quando a inferência terminou.

A janela não precisa ficar limitada ao FPS da IA. A captura continua lendo o frame mais novo e a inferência descarta frames intermediários se estiver atrasada.

## Ajustes para CPU fraca

Primeiro tente:

```python
IMGSZ = 320
LARGURA_CAMERA = 640
ALTURA_CAMERA = 480
```

Se o animal ocupar uma parte grande da imagem, `320` costuma ser suficiente para validar o sistema. Para animais muito distantes, aumente novamente para `416`, `512` ou treine um modelo especializado.

Evite usar 1080p para a inferência se a câmera estiver em uma porteira onde o animal aparece grande no quadro.

## GPU NVIDIA

Se PyTorch detectar CUDA, o projeto seleciona automaticamente a GPU e ativa FP16.

Confira no terminal ao iniciar:

```text
GPU detectada: ... -> CUDA + FP16 habilitado
```

## OpenVINO para CPU Intel (opcional)

Instale:

```bash
pip install openvino
python export_openvino.py
```

Depois use a pasta exportada como modelo em `main.py`, normalmente:

```python
MODELO = "yolo26n_openvino_model"
```

Compare `FPS IA` antes e depois no mesmo computador/câmera.

---

# Passar de humanos para bovinos

Para um teste inicial usando o modelo COCO:

```python
CLASSES_ALVO = [19]  # cow
```

Isso serve para validar a infraestrutura, mas **não deve ser considerado o modelo final de produção**.

Para uma contagem confiável de bovinos, o passo correto é treinar/fazer fine-tuning com imagens reais ou muito parecidas com:

- a câmera que ficará instalada;
- a altura e o ângulo reais;
- dia/noite e diferentes iluminações;
- raças e cores presentes no rebanho;
- animais parcialmente escondidos;
- dois ou mais bovinos lado a lado;
- poeira, sombra, barro e grades/cercas do local.

Depois basta trocar:

```python
MODELO = "best.pt"
CLASSES_ALVO = [0]  # se seu dataset próprio tiver apenas a classe bovino
```

O contador e a API continuam iguais.

---

# Posicionamento da câmera — muito importante

Para uma aplicação real de porteira/corredor:

1. **câmera fixa**; não deixe a câmera balançando;
2. faça os animais passarem por um corredor relativamente estreito;
3. coloque a linha virtual perpendicular ao fluxo;
4. deixe espaço visível antes e depois da linha, para o tracker construir trajetória;
5. evite a linha exatamente numa região onde animais ficam parados ou se agrupam;
6. se possível, use um ângulo em que um bovino não esconda totalmente o outro.

Um bom posicionamento da câmera normalmente melhora mais a contagem do que simplesmente usar um modelo YOLO maior.

---

# Parâmetros da linha

Em `main.py`:

```python
LINHA_X_RELATIVA = 0.50
MARGEM_LINHA_RELATIVA = 0.025
DESLOCAMENTO_MIN_RELATIVO = 0.07
MIN_FRAMES_TRACK = 3
```

- `LINHA_X_RELATIVA`: posição da linha (`0.50` = meio da tela).
- `MARGEM_LINHA_RELATIVA`: zona morta anti-tremedeira.
- `DESLOCAMENTO_MIN_RELATIVO`: distância mínima para considerar movimento real.
- `MIN_FRAMES_TRACK`: evita aceitar um ID que apareceu por apenas 1–2 inferências.

Se estiver perdendo cruzamentos muito rápidos, diminua `MIN_FRAMES_TRACK` para `2`. Se houver muito ruído perto da linha, aumente a margem.

---

# Testes automáticos

Execute:

```bash
python -m unittest discover -s tests -v
```

Os testes cobrem:

- direita → esquerda soma uma vez;
- esquerda → direita não soma;
- tremedeira perto da linha não soma;
- o mesmo ID não é recontado;
- retorno primeiro bloqueia uma futura recontagem;
- um ID que aparece já no lado esquerdo não é contado automaticamente.

---

# Limitação que ainda existe

Nenhum tracker é perfeito. Se um bovino desaparecer completamente, receber outro ID e depois fizer um caminho complexo, pode haver casos extremos de identidade duplicada. A linha direcional elimina grande parte desse problema porque um ID novo **não é contado automaticamente**, mas a versão de produção ainda deve ser validada com vídeos reais do local.

Se a troca de ID acontecer justamente durante uma oclusão na linha, use o perfil ReID e, principalmente, treine o detector com dados da câmera real.
