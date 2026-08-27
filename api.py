"""API HTTP para consultar e controlar a sessão de contagem."""

from fastapi import FastAPI

from state import estado

app = FastAPI(
    title="API de Contagem de Rebanho",
    description=(
        "Contagem direcional em tempo real por câmera + YOLO + tracking. "
        "O total aumenta somente em cruzamentos da direita para a esquerda."
    ),
    version="2.0.0",
)


@app.get("/")
def raiz():
    return {
        "mensagem": "API de contagem no ar.",
        "docs": "/docs",
        "contagem": "/contagem/atual",
    }


@app.get("/health")
def health():
    snapshot = estado.snapshot()
    return {
        "ok": bool(snapshot["sistema_rodando"]),
        "ultima_atualizacao": snapshot["ultima_atualizacao"],
    }


@app.get("/contagem/atual")
def contagem_atual():
    return estado.snapshot()


@app.get("/contagem/eventos")
def eventos_contagem():
    return {"eventos": estado.eventos()}


@app.post("/contagem/resetar")
def resetar_contagem():
    estado.resetar()
    return {"mensagem": "Nova sessão de contagem iniciada.", "novo_estado": estado.snapshot()}
