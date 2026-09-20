# Changelog

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
