"""Ponto de entrada do ContagemSys.exe (PyInstaller).

Equivale a `python main.py --desktop`. Sem console (exe janela), a saida que
iria para o terminal vai para logs/contagem.log ao lado do executavel.
"""
from __future__ import annotations

import multiprocessing
import sys


def _redirecionar_saida() -> None:
    if sys.stdout is not None and sys.stderr is not None:
        return
    from config import BASE_DIR

    pasta = BASE_DIR / "logs"
    pasta.mkdir(parents=True, exist_ok=True)
    log = open(pasta / "contagem.log", "a", encoding="utf-8", buffering=1)  # noqa: SIM115
    sys.stdout = sys.stdout or log
    sys.stderr = sys.stderr or log


if __name__ == "__main__":
    multiprocessing.freeze_support()
    _redirecionar_saida()
    if "--desktop" not in sys.argv:
        sys.argv.insert(1, "--desktop")
    from main import main

    raise SystemExit(main())
