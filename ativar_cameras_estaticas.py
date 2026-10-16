"""Ajuste pontual do config.yaml para webcams virtuais / cenas paradas.

Preserva IDs de cameras, comentarios, tokens e demais configuracoes.
Uso: python ativar_cameras_estaticas.py [caminho_config.yaml]
"""
from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import sys

import yaml


def ativar_cameras_estaticas(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    cfg = yaml.safe_load(original) or {}
    webcam = (cfg.get("discovery") or {}).get("webcam") or {}
    if "accept_static_frames" not in webcam:
        raise ValueError("Nao existe discovery.webcam.accept_static_frames no arquivo. Adicione este campo manualmente.")
    # Troca somente o valor deste campo; nao regrava o YAML inteiro.
    pattern = r"(?m)^(\s*accept_static_frames\s*:\s*)(?:true|false)([ \t]*(?:\#.*)?)$"
    updated, changed = re.subn(pattern, lambda m: m.group(1) + "true" + m.group(2), original, count=1, flags=re.IGNORECASE)
    if changed != 1:
        raise ValueError("Nao foi possivel alterar accept_static_frames de maneira segura.")
    yaml.safe_load(updated)  # validacao antes de gravar
    if updated == original:
        return False
    backup = path.with_suffix(path.suffix + ".antes_iriun.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(updated, encoding="utf-8")
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    print(f"Config atualizada: {path}")
    print(f"Backup: {backup}")
    return True


if __name__ == "__main__":
    config = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "config.yaml"
    try:
        if not ativar_cameras_estaticas(config):
            print("Configuracao ja permite imagens estaticas; nenhuma alteracao necessaria.")
    except (OSError, ValueError, yaml.YAMLError) as exc:
        raise SystemExit(f"ERRO: {exc}")
