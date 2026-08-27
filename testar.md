Sistema de Contagem em Tempo Real — Versão 2

Sistema de visão computacional para detecção, rastreamento e contagem direcional em tempo real usando webcam/câmera, YOLO, tracking e FastAPI.

Nesta etapa o sistema está configurado para detectar pessoas, facilitando os testes com uma webcam. Depois, a mesma estrutura poderá ser utilizada para bovinos.

Como a contagem funciona

O sistema não conta simplesmente cada ID criado pelo tracker.

Uma entidade só é contabilizada quando sua trajetória atravessa a linha central no sentido:

ESQUERDA  --------------------->  DIREITA   = NÃO CONTA

ESQUERDA  <--------- | ---------  DIREITA   = +1
                     LINHA

Sentido contado: DIREITA -> ESQUERDA

Na prática:

ESQUERDA                LINHA                 DIREITA
                           |
                           |                [PESSOA]
                           |       <-----------
                           |
                       +1 ao cruzar

Se a pessoa voltar no sentido esquerda -> direita, o sistema registra um retorno, mas não soma novamente.

1. Requisitos

Recomendado:

Windows 10 ou Windows 11

VS Code

Python 3.12

Webcam

Internet na primeira execução para baixar o modelo YOLO, caso ele ainda não exista no computador

Para verificar sua versão do Python, abra o terminal do VS Code e execute:

python --version

O esperado é algo semelhante a:

Python 3.12.x

2. Abrir o projeto no VS Code

No VS Code, abra a pasta que contém arquivos como:

main.py
api.py
camera_stream.py
counting.py
state.py
requirements.txt
tracker_bytetrack.yaml

Depois abra o terminal pelo menu:

Terminal > New Terminal

Confirme que está na pasta correta:

dir

No Git Bash também pode usar:

ls

Você deve conseguir ver main.py e requirements.txt.

3. Criar o ambiente virtual

É recomendado criar um ambiente virtual separado para o projeto.

Execute:

python -m venv venv

PowerShell

.\venv\Scripts\Activate.ps1

Se o PowerShell bloquear a ativação, execute somente para essa sessão:

Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass

E tente novamente:

.\venv\Scripts\Activate.ps1

CMD

venv\Scripts\activate

Git Bash

source venv/Scripts/activate

Quando estiver ativado, normalmente aparecerá algo parecido com:

(venv)

antes do caminho no terminal.

4. Atualizar o pip

Com o venv ativado:

python -m pip install --upgrade pip

5. Instalar as dependências

Execute:

pip install -r requirements.txt

O projeto utiliza principalmente:

Ultralytics / YOLO

OpenCV

PyTorch

FastAPI

Uvicorn

A instalação pode baixar vários pacotes.

6. Testar se as bibliotecas foram instaladas

Execute:

python -c "import cv2, torch, ultralytics, fastapi; print('Dependencias instaladas corretamente')"

Se aparecer:

Dependencias instaladas corretamente

as principais bibliotecas estão disponíveis.

7. Configuração para testar com pessoas

Abra o arquivo:

main.py

No início do arquivo confirme estas configurações:

FONTE_VIDEO = 0
MODELO = "yolo26n.pt"
CLASSES_ALVO = [0]

Onde:

FONTE_VIDEO = 0       -> webcam padrão
CLASSES_ALVO = [0]    -> classe person do modelo COCO

Não altere para bovino enquanto estiver realizando os testes com pessoas.

8. Executar o sistema

No terminal, com o ambiente virtual ativado, execute:

python main.py

Na primeira execução o Ultralytics poderá baixar automaticamente o modelo:

yolo26n.pt

Depois de carregar o modelo e abrir a câmera, o terminal deverá mostrar informações semelhantes a:

Swagger:              http://localhost:8000/docs
Contagem atual:       http://localhost:8000/contagem/atual
Eventos de passagem: http://localhost:8000/contagem/eventos

Também será aberta uma janela com a imagem da webcam.

9. Teste principal da contagem

Faça este teste antes de modificar qualquer configuração.

Teste 1 — entrar pelo lado direito

Fique no lado direito da linha.

Aguarde o sistema detectar você e mostrar um ID.

Atravesse completamente a linha indo da direita para a esquerda.

Exemplo:

ESQUERDA                LINHA                  DIREITA
                           |
                           |                  VOCÊ
                           |             <---------
                           |

O esperado é:

CONTADOS: 1

10. Teste de retorno

Agora volte da esquerda para a direita:

ESQUERDA                LINHA                  DIREITA
VOCÊ                       |
--------- >                |
                           |

O esperado é que CONTADOS continue igual:

CONTADOS: 1
RETORNOS: 1

Ou seja, o retorno não aumenta a contagem.

11. Teste de falso positivo

Faça também estes testes:

Girar parado

Fique do mesmo lado da linha e:

vire de costas;

vire de frente;

mova os braços;

agache;

dê pequenos passos.

O contador não deve aumentar.

Aproximar da linha sem atravessar

Chegue perto da linha, mas não atravesse completamente.

O contador não deve aumentar.

Oscilar perto da linha

Faça pequenos movimentos perto da linha.

A zona morta/histerese deve evitar múltiplas contagens por pequenas oscilações da bounding box.

12. Informações mostradas na câmera

A parte superior da janela mostra:

CONTADOS

Quantidade contabilizada no sentido correto.

NO FRAME

Quantidade de entidades detectadas no frame atual.

RETORNOS

Quantidade de cruzamentos detectados no sentido inverso.

FPS camera

Velocidade em que a webcam está fornecendo frames.

FPS IA

Quantidade de frames por segundo que o YOLO + tracker consegue processar.

latencia IA

Tempo aproximado entre a captura do frame e o término da inferência.

13. Abrir o Swagger

Com python main.py executando, abra no navegador:

http://localhost:8000/docs

O FastAPI abrirá a interface Swagger.

14. Testar os endpoints no Swagger

Verificar o sistema

GET /health

Clique em:

Try it out

Depois:

Execute

Ver a contagem atual

GET /contagem/atual

Exemplo de resposta:

{
  "total_contado": 1,
  "animais_no_frame_agora": 1,
  "retornos_esquerda_para_direita": 0,
  "direcao_contada": "direita_para_esquerda",
  "fps_ia": 10.5,
  "fps_camera": 30.0,
  "latencia_ia_ms": 75.2,
  "sistema_rodando": true
}

Ver os eventos

GET /contagem/eventos

O endpoint mostra os últimos cruzamentos detectados.

Exemplo de passagem contabilizada:

{
  "track_id": 4,
  "direcao": "direita_para_esquerda",
  "contabilizado": true
}

Exemplo de retorno:

{
  "track_id": 4,
  "direcao": "esquerda_para_direita",
  "contabilizado": false
}

Zerar a contagem

Use:

POST /contagem/resetar

Depois de executar, o contador começa uma nova sessão.

15. Executar os testes automáticos

O projeto possui testes da lógica de contagem.

Execute:

python -m unittest discover -s tests -v

O resultado esperado deve terminar com algo semelhante a:

Ran 7 tests

OK

Os testes verificam situações como:

direita -> esquerda conta;

esquerda -> direita não conta;

oscilação próxima da linha não conta;

mesmo ID não é contabilizado repetidamente;

novo ID aparecendo do lado esquerdo não é contado imediatamente;

reset não permite que uma inferência antiga restaure a contagem anterior.

16. Fechar o programa

Clique na janela da câmera e pressione:

Q

O programa fechará a câmera e encerrará o processamento.

Se necessário, também pode interromper pelo terminal com:

Ctrl + C

17. Se a webcam não abrir

Por padrão:

FONTE_VIDEO = 0

Se seu computador tiver mais de uma câmera, tente:

FONTE_VIDEO = 1

ou:

FONTE_VIDEO = 2

Execute novamente:

python main.py

Feche outros programas que possam estar usando a câmera, por exemplo:

Microsoft Teams;

Discord;

Zoom;

aplicativo Câmera do Windows;

navegador usando webcam.

18. Se aparecer No module named cv2

Confirme que o venv está ativado e execute:

pip install opencv-python

Depois teste:

python -c "import cv2; print(cv2.__version__)"

19. Se aparecer No module named ultralytics

Execute:

pip install ultralytics

Ou reinstale todas as dependências:

pip install -r requirements.txt

20. Se o FPS da IA estiver baixo

Abra main.py e localize:

IMGSZ = 416

Teste:

IMGSZ = 320

Depois execute novamente:

python main.py

Compare o valor de:

FPS IA

antes e depois.

Quanto menor o IMGSZ, normalmente maior será o FPS, porém também pode haver perda de precisão para objetos pequenos ou distantes.

21. Testar outro tracker

O padrão é o ByteTrack:

TRACKER = str(BASE_DIR / "tracker_bytetrack.yaml")

Se o ID estiver sendo perdido ou trocado com muita frequência, teste o BoT-SORT com ReID:

TRACKER = str(BASE_DIR / "tracker_botsort_reid.yaml")

O BoT-SORT + ReID pode melhorar a persistência dos IDs, mas tende a consumir mais processamento.

Para webcam e computador sem GPU, teste primeiro o ByteTrack.

22. Testar OpenVINO em CPU Intel — opcional

Se o computador utilizar processador Intel e não possuir GPU NVIDIA, você pode comparar o desempenho com OpenVINO.

Instale:

pip install openvino

Execute:

python export_openvino.py

Depois da exportação deverá ser criada uma pasta semelhante a:

yolo26n_openvino_model

No main.py, altere:

MODELO = "yolo26n.pt"

para:

MODELO = "yolo26n_openvino_model"

Execute novamente e compare o FPS IA.

23. Futuramente: testar bovinos

Quando os testes com pessoas estiverem funcionando corretamente, um teste inicial com a classe cow do COCO pode ser feito alterando:

CLASSES_ALVO = [0]

para:

CLASSES_ALVO = [19]

Onde:

0  = person
19 = cow

Para produção, o recomendado é utilizar um modelo próprio treinado com imagens reais dos bovinos e do ambiente da câmera.

Exemplo futuro:

MODELO = "best.pt"
CLASSES_ALVO = [0]

Nesse caso 0 poderá representar a classe bovino do seu próprio dataset.

24. Sequência recomendada de validação

Antes de passar para bovinos, valide nesta ordem:

O programa inicia sem erros.

A webcam abre corretamente.

Uma pessoa recebe um ID.

Direita -> esquerda gera exatamente +1.

Esquerda -> direita não aumenta o total.

Girar parado não aumenta o total.

Aproximar da linha sem cruzar não aumenta o total.

Os endpoints aparecem no Swagger.

POST /contagem/resetar realmente zera a sessão.

Os testes automáticos terminam com OK.

Verifique o FPS IA.

Teste duas pessoas passando separadamente.

Teste duas pessoas passando próximas.

Teste o comportamento quando uma pessoa esconde parcialmente a outra.

Somente depois comece os testes com bovinos.

Estrutura do projeto

contagemsys/
├── main.py
├── api.py
├── camera_stream.py
├── counting.py
├── state.py
├── tracker_bytetrack.yaml
├── tracker_botsort_reid.yaml
├── export_openvino.py
├── requirements.txt
├── README.md
└── tests/
    ├── test_directional_counter.py
    └── test_state.py

Comando rápido para iniciar depois da primeira instalação

Sempre que fechar o VS Code e abrir novamente:

Git Bash

source venv/Scripts/activate
python main.py

PowerShell

.\venv\Scripts\Activate.ps1
python main.py

CMD

venv\Scripts\activate
python main.py

Depois abra:

http://localhost:8000/docs

E faça o teste caminhando da direita para a esquerda na frente da webcam.