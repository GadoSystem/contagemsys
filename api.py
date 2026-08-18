"""
API FastAPI que expõe o resultado da contagem para fora do script
(dashboard, app, Postman, navegador, etc).

Roda em uma thread separada, disparada pelo main.py.
Teste no navegador: http://localhost:8000/docs
"""

from fastapi import FastAPI

from state import estado

app = FastAPI(
    title="API de Contagem de Animais",
    description="Contagem em tempo real via câmera + YOLO + tracking.",
    version="1.0.0",
)


@app.get("/")
def raiz():
    return {"mensagem": "API de contagem no ar. Acesse /docs para testar os endpoints."}


@app.get("/contagem/atual")
def contagem_atual():
    """Retorna o snapshot mais recente da contagem."""
    return estado.snapshot()


@app.post("/contagem/resetar")
def resetar_contagem():
    """Zera os contadores (útil para começar uma nova sessão de contagem)."""
    estado.resetar()
    return {"mensagem": "Contagem resetada.", "novo_estado": estado.snapshot()}
