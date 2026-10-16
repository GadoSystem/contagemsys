# ContagemSys — Correção de detecção do Iriun Webcam

## Problema corrigido

A descoberta da versão anterior podia rejeitar o Iriun mesmo depois de receber imagens do dispositivo. O motivo era a exigência de movimento visível em todos os testes, inclusive na verificação final. Os logs apresentados mostraram `8 frames, 5 atualizacoes visuais` usando MSMF, seguidos de `imagem sem mudancas` na última verificação.

Nesta correção:

- Uma webcam que **entrega frames válidos** pode ser aceita mesmo quando a imagem está estática; ausência ou falha de leitura continua sendo rejeitada.
- Com `backend: auto`, a seleção considera primeiro o número de fontes que funcionam juntas e, em empate, dá preferência ao backend que mostrou mais mudanças visuais (ex.: MSMF em vez de DSHOW).
- A descoberta continua preservando identificadores `camera_1`, `camera_2` etc., essenciais aos vínculos com os usuários do Rebano.
- Se uma câmera anteriormente chamada `(... sem sinal)` voltar a ficar ativa, essa observação desatualizada é removida do nome.
- A captura, o YOLO, o stream HTTP e os parâmetros de desempenho não foram alterados por este pacote.

**Atenção:** frames estáticos não comprovam que há vídeo real. Drivers de webcam virtual podem fornecer uma tela de espera quando o aplicativo está desconectado. Confira visualmente a imagem do Iriun.

## Atualizar (Windows + Git Bash / VS Code)

1. Pare o ContagemSys com `Q` na janela de vídeo ou `Ctrl+C` no terminal. Feche outros programas que possam ter aberto a câmera.
2. Faça uma cópia de segurança da pasta do projeto e especialmente de `config.yaml`.
3. Extraia os arquivos deste ZIP **na raiz do ContagemSys**, mantendo `tests/` na mesma posição.
4. Com o ambiente virtual ativo, execute:

   ```bash
   python ativar_cameras_estaticas.py
   ```

   O programa altera **somente** `discovery.webcam.accept_static_frames` de `false` para `true` e cria `config.yaml.antes_iriun.bak`. Os IDs, URLs IP, comentários e outras opções permanecem iguais.
5. Abra o Iriun Webcam no computador e no celular e confirme que a imagem está mudando na janela do próprio aplicativo.
6. Execute somente a descoberta para checar o resultado:

   ```bash
   python main.py --discover-only
   ```

   Confira no terminal se `source 0` é detectada e se foi escolhida `MSMF` ou `DSHOW`. O `config.yaml` será atualizado automaticamente.
7. Inicie o programa:

   ```bash
   python main.py
   ```

   A janela do ContagemSys deverá aparecer. Clique nela e pressione **Q** para encerrar a aplicação e a API.

## Se o Iriun continuar mostrando a tela de espera

Primeiro, confira se o celular está transmitindo para o aplicativo Iriun no PC. Depois, no `config.yaml`, teste:

```yaml
discovery:
  enabled: true
  webcam:
    enabled: true
    backend: "msmf"
    max_index: 6
    samples: 8
    accept_static_frames: true
    fallback_low_bandwidth: true
```

Use a mesma estrutura existente do arquivo — substitua **apenas** os campos correspondentes, sem criar outra seção `discovery`.

Para testar a fonte diretamente sem o scanner desativá-la, defina provisoriamente em `video.cameras` a câmera com `source: 0`, `backend: msmf` e `enabled: true`, e execute:

```bash
python main.py --no-discovery
```

Esse teste ajuda a separar uma falha do scanner de uma falha de entrega de vídeo pelo driver do Iriun. Se a imagem não se atualizar, verifique o Iriun, Windows > Configurações > Privacidade e segurança > Câmera, e se Teams/OBS/navegador estão prendendo o dispositivo. Teste também `python listar_cameras.py --backend msmf --max 3 --preview` (confirme no preview que o vídeo é realmente do celular).

## Testes automáticos

```bash
python -m unittest discover -s tests -v
```

**Limitação da validação:** os testes cobrem a lógica de software, inclusive frames estáticos, preferência de backend e conservação do YAML. A câmera Iriun real e os drivers do seu Windows não estão disponíveis neste ambiente, portanto a fluidez e o funcionamento físico ainda precisam ser conferidos no computador.
