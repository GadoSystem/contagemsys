"""Janela desktop do ContagemSys (usada pelo ContagemSys.exe).

Abre o mesmo painel web em uma janela propria (pywebview: WebView2/Edge no
Windows, WebKitGTK ou Qt no Linux). A API continua escutando na rede para a
integracao com o Rebano; a janela e apenas a tela local do software.
"""
from __future__ import annotations

import html
import time
import urllib.request
from collections.abc import Callable

from config import BASE_DIR

_PAGINA = """<!doctype html><html lang="pt-BR"><meta charset="utf-8">
<body style="margin:0;height:100vh;display:grid;place-items:center;background:#0b0f14;
color:#e6edf3;font:16px system-ui,sans-serif;text-align:center">
<div><h2 style="margin:0 0 8px;font-weight:600">{titulo}</h2>
<p style="margin:0;color:#8b98a5">{texto}</p></div></body></html>"""


def _pagina(titulo: str, texto: str) -> str:
    return _PAGINA.format(titulo=html.escape(titulo), texto=html.escape(texto))


def _aguardar_api(url: str, api_viva: Callable[[], bool], timeout: float = 120.0) -> bool:
    limite = time.monotonic() + timeout
    while time.monotonic() < limite and api_viva():
        try:
            with urllib.request.urlopen(url + "health", timeout=2.0):
                return True
        except OSError:
            time.sleep(0.5)
    return False


def open_window(url: str, titulo: str, api_viva: Callable[[], bool]) -> None:
    """Mostra o painel e bloqueia ate a janela ser fechada."""
    import webview

    janela = webview.create_window(
        titulo,
        html=_pagina("Iniciando o ContagemSys…", "Abrindo as câmeras e o servidor local."),
        width=1366,
        height=820,
        min_size=(960, 600),
        background_color="#0b0f14",
    )

    def carregar() -> None:
        if _aguardar_api(url, api_viva):
            janela.load_url(url)
        else:
            janela.load_html(_pagina(
                "Não foi possível iniciar o servidor local",
                "Verifique se a porta configurada em config.yaml está livre e veja logs/contagem.log.",
            ))

    try:
        # Sem modo privado: o login (localStorage) continua salvo entre aberturas.
        webview.start(
            carregar,
            private_mode=False,
            storage_path=str(BASE_DIR / "data" / "webview"),
        )
    except Exception as exc:
        # Sem WebView2 (Windows) ou GTK/Qt (Linux): usa o navegador padrao e
        # mantem o ContagemSys rodando enquanto o servidor estiver ativo.
        print(f"[desktop] Janela propria indisponivel ({exc}). Abrindo no navegador.")
        import webbrowser

        if _aguardar_api(url, api_viva):
            webbrowser.open(url)
        while api_viva():
            time.sleep(1.0)
