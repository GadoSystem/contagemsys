# ContagemSys V5 — Teste com Rebano

Guia rápido para testar o **ContagemSys** integrado ao **Rebano** usando **Git Bash no VS Code**.

## 1. Abrir o projeto no VS Code

Abra a pasta do ContagemSys no VS Code e abra o terminal:

```text
Terminal > New Terminal
```

Confirme que o terminal selecionado é **Git Bash**.

---

## 2. Criar e ativar o ambiente virtual

No terminal, dentro da pasta do ContagemSys:

```bash
python -m venv venv
source venv/Scripts/activate
```

Quando estiver ativo, o terminal deve começar com:

```text
(venv)
```

---

## 3. Instalar as dependências

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Teste se o OpenCV foi instalado:

```bash
python -c "import cv2; print(cv2.__version__)"
```

---

## 4. Descobrir as câmeras

Execute:

```bash
python listar_cameras.py
```

Exemplo:

```text
Camera 0 encontrada
Camera 1 encontrada
```

---

## 5. Configurar as câmeras

No arquivo `config.yaml`:

```yaml
video:
  cameras:
    - id: "camera_1"
      name: "Webcam 1"
      source: 0
      enabled: true

    - id: "camera_2"
      name: "Webcam 2"
      source: 1
      enabled: true
```

---

## 6. Preparar o Rebano

Abra outro terminal Git Bash no VS Code e entre no backend:

```bash
cd /c/Users/Alunos/Desktop/rebano-system-main/BackEnd/Rebano
```

Instale o Entity Framework caso ainda não esteja instalado:

```bash
dotnet tool install --global dotnet-ef --version 10.0.9
```

Se já estiver instalado:

```bash
dotnet tool update --global dotnet-ef --version 10.0.9
```

Depois:

```bash
dotnet restore
dotnet ef database update
dotnet run
```

O backend deve ficar disponível em:

```text
http://localhost:5148
```

Swagger:

```text
http://localhost:5148/swagger
```

---

## 7. Se o banco estiver vazio

Se houver **0 fazendas e 0 usuários**, crie primeiro uma fazenda.

Temporariamente, no arquivo:

```text
BackEnd/Rebano/Controllers/FazendaController.cs
```

adicione `[AllowAnonymous]` no método `CriarFazenda`:

```csharp
[AllowAnonymous]
[HttpPost("Criar")]
public async Task<ActionResult<FazendaResponseDTO>> CriarFazenda(FazendaCreateDTO fazenda)
{
    var fazendaResponse = await _service.CriarFazenda(fazenda);
    return Ok(fazendaResponse);
}
```

Reinicie o backend:

```bash
dotnet run
```

No Swagger, use:

```text
POST /Fazenda/Criar
```

Depois confira o ID da fazenda no PostgreSQL:

```sql
SELECT "Id", "Nome" FROM "Fazendas";
```

Em seguida crie o usuário Guilherme usando esse `FazendaId`.

Depois do teste inicial, remova o `[AllowAnonymous]`.

---

## 8. Configurar o ContagemSys

Na raiz do ContagemSys, crie ou edite o arquivo `.env`:

```env
REBANO_API_URL=http://localhost:5148
CONTAGEM_INTEGRATION_KEY=REBANO_CONTAGEM_TEST_2026

CONTAGEM_ADMIN_USER=admin
CONTAGEM_ADMIN_PASSWORD=admin123
```

A `CONTAGEM_INTEGRATION_KEY` deve ser igual à chave configurada no Rebano.

---

## 9. Iniciar o ContagemSys

Volte ao terminal do ContagemSys, confirme que o ambiente virtual está ativo e execute:

```bash
python main.py
```

Abra:

```text
http://localhost:8000
```

---

## 10. Vincular câmera ao usuário

Abra:

```text
http://localhost:8000/admin
```

Login padrão de teste:

```text
Usuário: admin
Senha: admin123
```

Vincule manualmente as câmeras aos usuários.

Exemplo:

```text
Guilherme
- camera_1
- camera_2

Arthur
- camera_3
```

Salve.

---

## 11. Testar o login do usuário

Abra:

```text
http://localhost:8000
```

Entre com o **mesmo login e senha usados no Rebano**.

Se Guilherme tiver:

```text
camera_1
camera_2
```

ele deve visualizar somente essas duas câmeras.

---

## 12. Teste esperado

```text
30 câmeras cadastradas
        ↓
Admin vincula cada câmera a um usuário
        ↓
Guilherme faz login
        ↓
Sistema identifica o Usuario.Id do Guilherme
        ↓
Mostra somente as câmeras vinculadas a ele
```

Exemplo:

```text
Guilherme -> camera_1, camera_2, camera_7
Arthur    -> camera_3
Carlos    -> camera_4, camera_5
```

---

## Checklist rápido

- [ ] `venv` criado e ativado
- [ ] Dependências instaladas
- [ ] `cv2` funcionando
- [ ] Câmeras identificadas
- [ ] `config.yaml` configurado
- [ ] PostgreSQL rodando
- [ ] Rebano rodando em `localhost:5148`
- [ ] Fazenda criada
- [ ] Usuário criado
- [ ] `.env` configurado
- [ ] ContagemSys rodando em `localhost:8000`
- [ ] Câmera vinculada ao usuário pelo `/admin`
- [ ] Login do usuário mostra somente suas câmeras
