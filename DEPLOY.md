# Como colocar o Estoque online

O site público (landing) fica no **Netlify** (estático). O **Estoque** é um app
Python (Flask) e precisa de um host que rode Python **com armazenamento persistente**
(pra não perder os dados). Recomendado: **PythonAnywhere** (plano free "Beginner").

> ⚠️ Segurança: online, NUNCA use `admin/admin`. Defina usuário/senha fortes e uma
> `SECRET_KEY` aleatória — tudo por **variáveis de ambiente** (não fica no código).

## Variáveis de ambiente que você vai definir
- `SECRET_KEY` — string aleatória longa (peça uma ao assistente).
- `ESTOQUE_USER` — seu usuário de login (ex.: `eve`).
- `ESTOQUE_PASS` — senha forte.
- `ESTOQUE_DATA` — pasta persistente pros dados, ex.: `/home/SEU_USUARIO/botis-data`.

## Passo a passo (PythonAnywhere, grátis)

1. Crie uma conta **Beginner (free)** em https://www.pythonanywhere.com — isso dá o
   endereço `SEU_USUARIO.pythonanywhere.com`.

2. No painel, abra **Consoles → Bash** e rode (repo privado → use um token do GitHub
   no lugar de `TOKEN`, ou torne o repo público):
   ```bash
   git clone https://TOKEN@github.com/ludovicomises/botisdaeve.git
   python3.10 -m venv ~/venv
   ~/venv/bin/pip install -r botisdaeve/estoque/requirements.txt
   mkdir -p ~/botis-data
   ```

3. Aba **Web → Add a new web app → Manual configuration → Python 3.10**.

4. Em **Virtualenv**, informe: `/home/SEU_USUARIO/venv`

5. Clique no link do **WSGI configuration file** e substitua todo o conteúdo por:
   ```python
   import os, sys
   sys.path.insert(0, '/home/SEU_USUARIO/botisdaeve/estoque')
   os.environ['SECRET_KEY']  = 'COLE_A_CHAVE_AQUI'
   os.environ['ESTOQUE_USER'] = 'eve'
   os.environ['ESTOQUE_PASS'] = 'SUA_SENHA_FORTE'
   os.environ['ESTOQUE_DATA'] = '/home/SEU_USUARIO/botis-data'
   from app import app as application
   ```

6. Clique em **Reload** (botão verde). Acesse:
   `https://SEU_USUARIO.pythonanywhere.com/estoque`

7. No site do Netlify, o botão **"Entrar"** passa a apontar para esse endereço
   (o assistente atualiza o `index.html` com a URL final).

## Atualizações futuras
Quando o código mudar no GitHub, no console Bash rode:
```bash
cd botisdaeve && git pull
```
e clique em **Reload** na aba Web.

## Alternativa: Render (auto-deploy do GitHub)
Fácil de conectar ao GitHub (como o Netlify), mas o plano **free apaga o banco** a cada
reinício. Só vale a pena com um **disco pago** ou um **Postgres** — nesse caso o código
precisa de ajustes. Por isso o PythonAnywhere é preferível para começar.
