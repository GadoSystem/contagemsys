# -*- mode: python ; coding: utf-8 -*-
# PyInstaller: gera dist/ContagemSys/ContagemSys.exe (pasta, nao arquivo unico:
# com PyTorch o arquivo unico teria de ser extraido a cada abertura).
#
#   pyinstaller --noconfirm --clean packaging/ContagemSys.spec
#
# contents_directory="." deixa config.yaml, .env, static/ e o modelo ao lado do
# exe, onde o ContagemSys os procura (config.BASE_DIR) e onde o usuario edita.
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules

ROOT = Path(SPECPATH).parent

arquivos = [
    ("static", "static"),
    ("config.yaml", "."),
    (".env.example", "."),
    ("tracker_bytetrack.yaml", "."),
    ("tracker_botsort_reid.yaml", "."),
    ("LEIA-ME.txt", "."),
    ("README.md", "."),
]
# .env (segredos e URL do Rebano) e o modelo entram se existirem na maquina do build.
for opcional in (".env", "yolo26n.pt"):
    if (ROOT / opcional).exists():
        arquivos.append((opcional, "."))
for pasta in ROOT.glob("*_openvino_model"):
    arquivos.append((pasta.name, pasta.name))

datas = [(str(ROOT / origem), destino) for origem, destino in arquivos]
datas += collect_data_files("ultralytics")   # cfg/*.yaml usados pelo YOLO
datas += collect_data_files("onvif")         # WSDL das cameras IP
datas += collect_data_files("openvino")      # cache.json dos plugins
# Plugins (CPU/GPU) e leitores de modelo (.xml) do OpenVINO sao carregados em
# tempo de execucao; sem isso o modelo *_openvino_model nao abre no exe.
binaries = collect_dynamic_libs("openvino")
# O torchvision novo registra o NMS do YOLO por _C_stable.(so|pyd), carregado
# via torch.ops.load_library; o hook padrao do PyInstaller nao o inclui.
import torchvision

_tv = Path(torchvision.__file__).parent
binaries += [
    (str(lib), "torchvision")
    for padrao in ("*.so", "*.pyd", "*.dll")
    for lib in _tv.glob(padrao)
]

hiddenimports = collect_submodules("uvicorn") + [
    "webview.platforms.edgechromium",
    "webview.platforms.winforms",
]

a = Analysis(
    [str(ROOT / "contagemsys_app.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    excludes=["tests", "tensorboard"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="ContagemSys",
    icon=str(ROOT / "packaging" / "contagemsys.ico"),
    console=False,
    contents_directory=".",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="ContagemSys",
)
