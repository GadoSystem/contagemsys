"""Ajusta o perfil de deteccao/contagem sem alterar as cameras e vinculos.

Uso (Git Bash): python ajustar_contagem.py
Opcional: python ajustar_contagem.py caminho/do/config.yaml
Cria backup config.yaml.antes_contagem.bak antes da primeira alteracao.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import sys

import yaml

# Nao substitui a lista video.cameras nem URLs/senhas de cameras IP.
SETTINGS = {
    ("video", "inference_fps"): "5.0",  # alvo; taxa real depende da CPU
    ("model", "confidence"): "0.25",    # objetos menores/iluminacao fraca
    ("model", "imgsz"): "384",          # precisao x custo de CPU
    ("gate", "stable_frames"): "1",    # nao perde passagens rapidas
    ("display", "max_box_age_ms"): "2200",  # box permanece entre inferencias
}


def ajustar(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    before = yaml.safe_load(original) or {}
    if not isinstance(before, dict):
        raise ValueError("config.yaml nao e um objeto valido")
    lines = original.splitlines(keepends=True)
    current_section = None
    updated_keys: set[tuple[str, str]] = set()
    result = []
    for line in lines:
        indent = len(line) - len(line.lstrip(" "))
        stripped = line.strip()
        if indent == 0 and stripped and not stripped.startswith("#") and ":" in stripped:
            current_section = stripped.split(":", 1)[0]
        changed = False
        if indent == 2 and current_section is not None and ":" in stripped and not stripped.startswith("#"):
            key = stripped.split(":", 1)[0]
            setting = (current_section, key)
            if setting in SETTINGS:
                original_rest = line.split(":", 1)[1]
                suffix = "  #" + original_rest.split("#", 1)[1].rstrip("\r\n") if "#" in original_rest else ""
                newline = "\r\n" if line.endswith("\r\n") else "\n"
                result.append(f"  {key}: {SETTINGS[setting]}{suffix}{newline}")
                updated_keys.add(setting)
                changed = True
        if not changed:
            result.append(line)

    missing = set(SETTINGS) - updated_keys
    if missing:
        raise ValueError("Chaves ausentes em config.yaml: " + ", ".join(f"{s}.{k}" for s, k in sorted(missing)))
    content = "".join(result)
    after = yaml.safe_load(content) or {}
    # Garante que o scanner nao perdeu/mudou as fontes de video.
    assert after.get("video", {}).get("cameras") == before.get("video", {}).get("cameras"), "IDs de camera mudaram"
    if content == original:
        print("Perfil de contagem ja esta configurado.")
        return False
    backup = path.with_name(path.name + ".antes_contagem.bak")
    if not backup.exists():
        shutil.copy2(path, backup)
    temp = path.with_name(path.name + ".tmp")
    try:
        temp.write_text(content, encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    print(f"Perfil de contagem atualizado: {path}")
    print(f"Backup: {backup}")
    return True


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent / "config.yaml"
    try:
        ajustar(target)
    except (OSError, ValueError, AssertionError, yaml.YAMLError) as exc:
        raise SystemExit(f"ERRO: {exc}")
