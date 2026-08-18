# Contador de Animais em Tempo Real — Guia Passo a Passo

Este projeto junta **Python + OpenCV + Ultralytics YOLO + ByteTrack/BoT-SORT + FastAPI**
para contar animais ao vivo pela câmera. Abre uma janela mostrando **data/hora** e a
**contagem em tempo real**, e também expõe esses dados numa API.

> **Atualização:** esta versão corrige o travamento/lag que acontecia com a câmera
> do celular. Veja a seção "Por que estava travando" mais abaixo para entender o quê
> mudou.

Arquivos do projeto:
```
cattle-counter/
├── main.py            <- roda tudo (câmera + IA + janela + API)
├── camera_stream.py    <- lê a câmera em tempo real, sem acumular atraso
├── api.py                <- os endpoints da API (FastAPI)
├── state.py                <- guarda o número da contagem de forma segura
├── requirements.txt         <- lista de dependências
└── README.md                  <- este guia
```

---

## Passo 1 — Instalar o Python

Você precisa do **Python 3.10, 3.11 ou 3.12** (o Ultralytics ainda não recomenda 3.13+).

1. Baixe em: https://www.python.org/downloads/
2. No instalador do Windows, **marque a caixa "Add Python to PATH"** antes de instalar.
3. Confirme a instalação abrindo o terminal e rodando:

```bash
python --version
```

---

## Passo 2 — Abrir a pasta do projeto no VS Code

1. Extraia o arquivo `.zip` do projeto em uma pasta, por exemplo `Documentos/cattle-counter`.
2. Abra o **VS Code** e vá em **File → Open Folder...**, selecione a pasta `cattle-counter`.
3. Abra o terminal integrado: **Terminal → New Terminal** (ou `Ctrl + '`).

---

## Passo 3 — Criar o ambiente virtual (venv)

**Windows (PowerShell/CMD):**
```bash
python -m venv venv
source venv/Scripts/activate
```

**Windows (Git Bash — é o que aparece se o terminal mostrar "MINGW64"):**
```bash
python -m venv venv
source venv/Scripts/activate
```

**Mac/Linux:**
```bash
python3 -m venv venv
source venv/bin/activate
```

Se funcionou, o nome `(venv)` aparece no início da linha do terminal.

---

## Passo 4 — Instalar as dependências

Com o `(venv)` ativado:

```bash
pip install -r requirements.txt
```

Teste se deu certo:
```bash
python -c "import cv2, ultralytics, fastapi; print('Tudo instalado com sucesso!')"
```

---

## Passo 5 — Testar SEM celular e SEM animal (validação rápida)

1. Abra `main.py` no VS Code e troque temporariamente:
   ```python
   CLASSES_ALVO = [0]  # 0 = pessoa, só para testar o pipeline
   ```
2. Confirme que `FONTE_VIDEO = 0` (webcam do notebook).
3. Rode:
   ```bash
   python main.py
   ```
4. Uma janela deve abrir com a webcam, a faixa preta com data/hora, a contagem
   e agora também o **FPS** (frames por segundo que o programa está processando).
5. Em outra aba do navegador (sem fechar a janela do vídeo!), acesse
   **http://localhost:8000/docs** e teste o endpoint `GET /contagem/atual`.
6. Para sair: clique na janela do vídeo e pressione **`q`**.

---

## Passo 6 — Conectar a câmera do celular

### Opção A (recomendada): app Iriun Webcam

1. Instale **"Iriun Webcam"** no celular (Play Store / App Store) **e** o programa
   Iriun no computador (https://iriun.com/).
2. Abra os dois ao mesmo tempo, na **mesma rede Wi-Fi** — eles se conectam sozinhos,
   sem precisar digitar nenhum IP.
3. No `main.py`, troque:
   ```python
   FONTE_VIDEO = 1   # webcam do notebook costuma ser 0; celular geralmente entra como 1
   ```
   Se não abrir a câmera certa, teste `2`, `3`...

### Opção B (Android, mais controle de resolução): app IP Webcam

1. Instale **"IP Webcam"** (Android), abra, toque em **"Start server"**.
2. Anote o endereço mostrado, ex: `http://192.168.0.15:8080`.
3. No `main.py`, troque (**repare nas aspas, são obrigatórias**):
   ```python
   FONTE_VIDEO = "http://192.168.0.15:8080/video"
   ```

---

## Passo 7 — Testar a detecção do animal de verdade

1. Volte `CLASSES_ALVO` para o animal desejado:
   ```python
   CLASSES_ALVO = [19]   # 19 = cow (gado)
   # outras opções: 17 = horse (cavalo), 18 = sheep (ovelha)
   ```
2. Aponte a câmera do celular para uma foto/vídeo de vaca em outra tela (você
   ainda não tem gado por perto — o YOLO não diferencia animal real de animal na tela).

> **Galinha não existe na lista padrão do YOLO** (dataset COCO). Gado, cavalo e
> ovelha funcionam de fábrica; para galinha é necessário fine-tuning com dataset
> próprio (ex: buscar "chicken detection dataset" no Roboflow Universe).

---

## Por que estava travando (e o que foi corrigido)

O problema **não era a câmera do celular em si**, era como o programa consumia
os frames dela. Três causas, já corrigidas nesta versão:

1. **Fila de frames se acumulando.** O programa antigo processava os frames um a
   um, na ordem exata em que chegavam. Como a IA é mais lenta que a taxa de
   frames da câmera, a fila só crescia — o vídeo ficava cada vez mais atrasado.
   **Correção:** criamos `camera_stream.py`, que lê a câmera numa thread própria
   e sempre entrega o **frame mais recente**, descartando os que ficaram para
   trás. Isso troca "processar tudo" por "estar sempre em tempo real".
2. **Resolução alta demais.** Celulares mandam vídeo em resolução bem maior do
   que o necessário para detectar um animal. **Correção:** os frames agora são
   redimensionados para `LARGURA_PROCESSAMENTO = 640` antes de entrar na IA, e o
   YOLO processa internamente em `IMGSZ = 480`.
3. **BoT-SORT como tracker padrão.** Ele é mais preciso em cenas com muita
   oclusão, mas bem mais pesado que o ByteTrack. **Correção:** o padrão agora é
   `TRACKER = "bytetrack.yaml"`. Se depois, com o gado de verdade, você notar
   muita troca de ID (animais se cruzando confundem o contador), aí sim vale
   testar `"botsort.yaml"` — mas só se o hardware aguentar.

### Ajustes finos se ainda estiver lento

No topo do `main.py`:
```python
LARGURA_PROCESSAMENTO = 480   # ainda menor = mais rápido, imagem menos nítida
IMGSZ = 320                   # idem
PULAR_FRAMES = 1              # processa 1 a cada 2 frames (2x mais rápido)
```
O contador de **FPS** que aparece na tela ajuda a saber se as mudanças
melhoraram: acima de ~10-15 FPS já fica bem fluido para contagem de animais
(eles não se movem tão rápido quanto pessoas correndo, por exemplo).

---

## Comandos de terminal usados neste projeto (resumo)

```bash
# 1. criar e ativar o ambiente virtual
python -m venv venv
venv\Scripts\activate            # Windows (PowerShell/CMD)
source venv/Scripts/activate     # Windows (Git Bash)
source venv/bin/activate         # Mac/Linux

# 2. instalar dependências
pip install -r requirements.txt

# 3. rodar o projeto
python main.py

# 4. (opcional) desativar o ambiente virtual quando terminar
deactivate
```

---

## Problemas comuns (troubleshooting)

| Problema | Causa provável | Solução |
|---|---|---|
| Vídeo travando/atrasado | Fila de frames acumulando, resolução alta, tracker pesado | Já corrigido nesta versão; se persistir, baixe `LARGURA_PROCESSAMENTO`, `IMGSZ` e use `PULAR_FRAMES = 1` ou `2` |
| `command not found: venvScriptsactivate` | Terminal é Git Bash, não PowerShell | Use `source venv/Scripts/activate` |
| `SyntaxError` na linha do `FONTE_VIDEO` | Esqueceu as aspas na URL | URLs de texto precisam de aspas: `FONTE_VIDEO = "http://..."` |
| Conexão recusada em `localhost:8000` | O `main.py` não está mais rodando (janela foi fechada ou 'q' foi pressionado) | Deixe a janela do vídeo aberta e acesse a API em outra aba, sem fechar o terminal |
| `Error: source not found` (Iriun/IP Webcam) | Celular e PC em redes Wi-Fi diferentes, ou app fechado | Confirme mesma rede Wi-Fi e os dois apps abertos |
| Detecta poucos animais / erra muito | Modelo genérico, ângulo difícil, pouca luz | Baixe `CONFIANCA_MINIMA` (ex: `0.25`) ou faça fine-tuning depois |
| Contagem "Total único" sobe rápido demais | Tracker perdendo o ID (ID switch) | Teste `TRACKER = "botsort.yaml"` (mais robusto, porém mais lento) |
| Porta 8000 já em uso | Outro programa usando a porta | Troque `port=8000` para `port=8001` dentro de `iniciar_api()` no `main.py` |

---

## Próximos passos (depois que isso estiver funcionando)

1. Trocar o modelo genérico por um **fine-tuned** com fotos reais da sua fazenda.
2. Trocar a fonte de vídeo do celular pela **câmera de segurança real** (RTSP) —
   o código não muda, só o valor de `FONTE_VIDEO`.
3. Adicionar uma **linha/zona de contagem** (contar só quem cruza o portão de
   entrada/saída), em vez de contar todo animal visível no quadro.
4. Guardar o histórico da contagem em um banco de dados (SQLite para começar)
   em vez de só manter em memória.
5. Se tiver uma placa de vídeo (GPU) disponível, o Ultralytics usa ela
   automaticamente quando encontra CUDA instalado — nesse caso dá pra usar
   `botsort.yaml` e resoluções maiores sem perder fluidez.
