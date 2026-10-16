# Atualização do ContagemSys — Detecção, IDs e contagem direcional

Atualização incremental sobre o ContagemSys V5 (com descoberta automática de câmeras/Iriun).
**O Rebano não precisa de alterações** para receber vídeo e contagens desta versão.

## Correções

- O detector agora usa `YOLO.predict` e processa **todas as caixas detectadas**, sem depender de `boxes.id` do ByteTrack. Isso evita ficar com 0 entidades quando o detector vê pessoas, mas o rastreador externo ainda não conseguiu fornecer IDs.
- O novo `tracking.py` mantém IDs locais independentes por câmera, incluindo várias entidades e travessias opostas simultâneas. A associação considera sobreposição, velocidade, classe e distância. Não faz reconhecimento biométrico e **não garante** continuidade do mesmo ID após desaparecimento prolongado ou oclusão longa.
- Caixa **azul/laranja** durante rastreamento; **verde** para entidade contada (direita → esquerda) e **vermelha** para retorno (esquerda → direita). Cada ID conta uma única vez na sessão.
- A contagem aceita a travessia completa mesmo quando o YOLO pulou o frame da zona central.
- As caixas permanecem visíveis entre inferências (por pelo menos 1,5 segundo), com captura e API MJPEG em threads independentes da IA.
- O terminal agora informa a cada ~8 segundos quantas detecções/IDs, FPS de captura, FPS de IA e latência existem para cada câmera. Isso facilita identificar se a falha está no detector ou no processamento.

## Como instalar (Windows, VS Code / Git Bash)

1. Encerre o `main.py` com **Q** na janela OpenCV ou **Ctrl+C** no terminal.
2. Faça backup da pasta ContagemSys.
3. Extraia o ZIP na **raiz da pasta do ContagemSys**. O ZIP não contém `config.yaml` nem `.env`, portanto preserva suas câmeras, vínculos, endereços e chaves.
4. No terminal Git Bash da pasta do ContagemSys:

```bash
source venv/Scripts/activate
python -m pip install -r requirements.txt
python ajustar_contagem.py
python -m unittest discover -s tests -v
python main.py
```

`ajustar_contagem.py` cria automaticamente `config.yaml.antes_contagem.bak` e altera SOMENTE `video.inference_fps`, `model.confidence`, `model.imgsz`, `gate.stable_frames` e `display.max_box_age_ms`. Preserva os índices, URLs, IDs e vínculos das câmeras. A descoberta continuará funcionando no início do programa. Não é necessário refazer os vínculos no Rebano.

## Perfil sugerido de contagem

```yaml
video:
  inference_fps: 5.0
model:
  classes: [0] # pessoa, teste; para vaca/bovino no modelo COCO: [19]
  confidence: 0.25
  imgsz: 384
gate:
  left_x: 0.42
  right_x: 0.58
  stable_frames: 1
  count_direction: "right_to_left"
display:
  max_box_age_ms: 2200
```

**Atenção:** os blocos acima são TRECHOS de referência, não substitua todo o `config.yaml` por eles. O comando já aplica os cinco ajustes relevantes. `5.0` FPS de IA é um **alvo**, não uma garantia. Com duas webcams e CPU fraca, a taxa efetiva pode ficar menor. Deixe `max_concurrent_inferences: 1` e `torch_threads: 2` para começar.

## Como validar

- Ilumine a cena e posicione a câmera fixa, sem a mover durante a contagem.
- Entre pelo lado **direito da imagem**, fora da faixa entre as linhas. Atravesse completamente as duas linhas até a esquerda. O mesmo ID deve ficar verde, e o total aumentar **1**.
- Faça o caminho inverso: esse ID deve ficar vermelho e o número de retornos aumentar, sem somar um novo contado.
- Coloque duas pessoas separadas na tela: cada uma deverá ter ID próprio, inclusive ao cruzarem uma pela outra em testes simples.
- Abra simultaneamente o stream no ContagemSys e no Rebano, e observe no terminal o FPS de captura e o FPS da IA.
- A classe `0` detecta **pessoas**, não gado. Ao testar bovinos, troque para `classes: [19]` e valide em gravações reais da fazenda. Pode ser necessário usar um modelo treinado especificamente para imagens do curral, ajustar ângulo de câmera, iluminação, ROI e limites do gate.

## Caso a IA não detecte ninguém

1. Confirme no terminal `deteccoes=...`. Se ficar **0**, o problema é detecção (classe, iluminação, modelo, resolução ou cenário), não contagem nem API.
2. Confirme `fps_ia` e `inferencia=...ms`. Se a inferência estiver muito lenta, tente `model.imgsz: 320` e `video.inference_fps: 3`.
3. Se houver IDs mas não houver contagens, confira a direção no vídeo, a posição das linhas e comece fora da região central.
4. Se a webcam congelar, confira `fps_captura` e se o Iriun está transmitindo sinal real. Uma falha de driver/USB não é corrigida aumentando FPS de IA.

## Testes automatizados

```bash
python -m unittest discover -s tests -v
```

Os testes verificam múltiplas entidades, associação de IDs, cruzamento em sentidos opostos, retorno sem contagem duplicada, travessia sem frame central e preservação do `config.yaml`. A validação final com webcams/YOLO reais deve ser realizada no Windows.
