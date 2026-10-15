# Atualização 2 — Stream fluido, webcams e visualização local

Este pacote é incremental às correções anteriores (aquelas que já incluíram o botão **Detalhes da câmera**). **Faça backup** antes de substituir. Ele contém somente os arquivos modificados; **não apague** os demais componentes dos projetos, e não substitua `.env`, `appsettings.json` nem banco SQLite.

## 1. Entenda a origem do problema

- A fonte `source: 0` do print entrega a tela "Please start Iriun Webcam". Isso é **Iriun Webcam**, uma câmera virtual sem sinal de câmera real. O software não consegue fabricar imagens de um dispositivo sem vídeo. **Abra o Iriun e conecte o celular** se quiser usá-lo como segunda câmera; se não quiser, desative essa fonte e use apenas a câmera física verificada.
- A fonte `source: 1` estava entregando vídeo. `source: 2` e superiores retornaram erro no DirectShow — não são câmeras disponíveis com esse backend.
- O painel antigo do ContagemSys fazia uma requisição a cada ~700 ms; o Rebano fazia muitas requisições JPEG. A nova versão usa MJPEG persistente sem acumular snapshots individuais.
- `show_window` estava `false`; foi restaurado para `true`.

## 2. Arquivos atualizados

**ContagemSys (extrair na raiz `contagemsys-main`):**

- `config.yaml` — **camera_1 (Iriun virtual) começa desativada por segurança**, camera_2 mantida ativa; janelas locais ativadas, stream alvo 15 FPS, preview alvo 20 FPS, IA alvo 2,5 FPS por câmera, captura solicitada 20 FPS, 2 threads Torch. Captura de evidências temporariamente desativada para testes de desempenho.
- `listar_cameras.py` — mantém cada webcam aberta durante o teste e o preview; exibe nomes de dispositivos do Windows apenas como referência (a ordem não indica necessariamente o índice OpenCV).
- `main.py` — não preenche buffer de evidências quando desativadas.
- `web_ui.py` — painel local usa MJPEG contínuo, e as métricas atualizam a cada 2,5 segundos.
- `api.py` — stream MJPEG sem buffer no proxy, fecha ao perder frames e ao perder o vínculo do usuário; ticket de stream no painel local.
- `auth.py` — ticket temporário de stream no ContagemSys.
- `tests/test_stream_ticket.py`, `tests/test_camera_discovery.py` — testes de autorização e descoberta.

**Rebano (extrair na raiz `rebano-system-main`):**

- `BackEnd/Rebano/Program.cs` — Data Protection para tickets temporários, sem aceitar JWT principal em URL de vídeo.
- `BackEnd/Rebano/Controllers/ContagemController.cs` — cria ticket de stream somente para câmeras vinculadas ao usuário e repassa o MJPEG sem buffer.
- `FrontEnd/src/api/contagem.ts` — consulta o ticket para criar URL MJPEG.
- `FrontEnd/src/Screens/cameras/pages/CameraAoVivo.tsx` — player MJPEG nativo, reconexão, descarte quando sai da tela ou aba fica oculta.

## 3. Atualização

1. Encerre `python main.py` (`Ctrl+C`) e `dotnet run` (`Ctrl+C`). Pare `npm run dev`.
2. Faça cópias das pastas de ambos os projetos.
3. Extraia **cada ZIP na pasta raiz correta** e aceite substituir arquivos. O ZIP do Rebano começa por `BackEnd/` e `FrontEnd/`; o ZIP ContagemSys começa pelos arquivos `.py`.
4. Preserve as chaves de integração no `.env` e `appsettings.json`.
5. Feche Teams, Zoom, aplicativos de câmera, e desligue o Iriun se não o for utilizar.

## 4. Descoberta: pare o ContagemSys ANTES do scanner

Dentro da pasta do ContagemSys, com o `(venv)` ativo:

```bash
python listar_cameras.py --backend dshow --max 5 --preview
```

**Mova a mão diante de cada webcam.** Pressione `S` para confirmar apenas quando a câmera mostrar vídeo real; pressione `N` para ignorar a tela de espera do Iriun, câmeras virtuais ou feeds incorretos.

O pacote já deixa a `camera_1` (fonte Iriun sem sinal) desativada e somente `camera_2` ativa, preservando o ID desta última e o vínculo do banco. Se seu hardware mudar, confirme novamente os índices no scanner:

```yaml
video:
  cameras:
    - id: "camera_1"
      name: "Webcam 1"
      source: 0
      enabled: false
    - id: "camera_2"
      name: "Webcam 2"
      source: 1
      enabled: true
```

**Atenção:** não substitua toda a seção `video` pelo exemplo acima: altere apenas os campos das câmeras no `config.yaml` original. Para ter duas imagens verdadeiras, ligue uma segunda webcam real ou conecte o Iriun com seu celular e confirme visualmente a fonte.

## 5. Iniciar os projetos

ContagemSys:

```bash
source venv/Scripts/activate
python main.py
```

Ao executar localmente, as janelas OpenCV devem voltar a abrir (`app.show_window: true`). Para fechar, pressione Q na janela, ou Ctrl+C no terminal. Não execute o scanner enquanto a API estiver capturando as webcams: dois processos podem disputar o dispositivo.

Backend Rebano (outro terminal):

```bash
cd BackEnd/Rebano
dotnet build
dotnet run --launch-profile http
```

Frontend Rebano (outro terminal; recomenda-se Node 24 LTS):

```bash
cd FrontEnd
npm ci
npm run dev -- --port 5173
```

Acesse:

- ContagemSys: `http://localhost:8000/painel`
- Status ContagemSys: `http://localhost:8000/health`
- Rebano: `http://localhost:5173/Cameras`

Após atualização **os dois processos precisam ser reiniciados**, sobretudo o backend Rebano (nova rota `/stream-ticket`).

## 6. Validar a fluidez

1. Deixe uma webcam física funcionando no ContagemSys por 3 minutos e movimente a câmera.
2. Confira se a imagem é atualizada no painel ContagemSys, na janela local e no Rebano.
3. Habilite uma segunda webcam real e repita por 5 minutos; observe CPU, `fps_camera` e `fps_ia`.
4. Faça login com outro usuário sem vínculo e confira que a câmera não é exibida para ele.
5. Teste os detalhes de contagem para garantir que a funcionalidade anterior foi preservada.

**Meta, não garantia:** até 15 FPS de transmissão por câmera com hardware compatível. O FPS real fica limitado ao da webcam, capacidade USB, CPU, rede e navegador. A IA foi reduzida intencionalmente para ~2,5 inferências/s por câmera e deve ser ajustada para cima quando houver folga de processamento.

## 7. Se ainda houver travamento

- Teste somente a webcam física, desligando a segunda. Se melhorar, é possível haver disputa de barramento USB ou limitação de CPU.
- Em `config.yaml`, reduza `api.stream_fps` para `10`, `display.preview_fps` para `15`, `video.width` para `480`, `video.height` para `360` **apenas se a webcam aceitar esses valores**.
- Desative a janela local com `app.show_window: false` quando rodar somente no servidor, liberando CPU (para teste no desktop, mantenha `true`).
- Confirme que `video.backend: dshow` e os índices sejam os mesmos do scanner.
- Se o Iriun continuar mostrando tela de espera, ele não está transmitindo vídeo. Ative o aplicativo e conecte o celular ou desative a câmera virtual.
- Para verificar a causa de uma interrupção, use o DevTools (F12) > Network: procure `stream-ticket` e `stream.mjpg` (não compartilhe URLs com tickets, nem tokens).
- Para subir em produção, configure persistência das chaves Data Protection do ASP.NET Core quando executar múltiplas instâncias do Rebano, senão tickets temporários podem não funcionar entre instâncias.

## 8. Validação executada

- 18 testes de unidade/integração do ContagemSys passaram, incluindo descoberta sem duplo open e isolamento por tickets.
- Código Python compilado sem erros de sintaxe.
- Frontend TypeScript alterado analisado sem erros de sintaxe.
- **Não foi possível executar webcams físicas Windows nem `dotnet build` neste ambiente**; a fluidez final e a compilação do backend precisam ser verificadas na sua máquina.
