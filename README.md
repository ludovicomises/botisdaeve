# Botis da Eve

Projeto da **Botis da Eve** — beleza & presentes (revenda multimarcas), Juiz de Fora / MG.

## Conteúdo

### 1. Landing page (`index.html` + `img/`)
Site institucional (hub → WhatsApp): presentes personalizados, revenda multimarcas
(O Boticário, Quem Disse Berenice, Eudora, OUI, Natura, Avon), prova social e
"como funciona". Página estática, self-contained.

### 2. Estoque (`estoque/`)
Ferramenta local (Flask + SQLite) de controle de estoque e vendas — **uso privado**,
roda no PC. Inclui:

- **Importar Nota Fiscal (PDF/DANFE)** → separa produtos de revenda de brindes/catálogos
  (por CFOP), com custo, quantidade, nº da NF e data.
- **Sugestão de preço de venda** a partir do catálogo (upload opcional).
- **Estoque de venda** e **estoque de brindes** separados.
- **Editar produtos**, **cadastro de clientes** e **controle de vendas** (carrinho por
  busca ou leitor de código de barras), com baixa automática no estoque.
- Área protegida por login.

#### Como rodar
```
cd estoque
pip install -r requirements.txt
python app.py        # ou dê 2 cliques em iniciar-estoque.bat
```
Abre em `http://127.0.0.1:5000`. O site fica em `/` e o estoque em `/estoque`.

Login padrão: `admin` / `admin` (troque em `app.py` ou via variáveis de ambiente
`ESTOQUE_USER` / `ESTOQUE_PASS`).

> Observação: `estoque.db`, `uploads/` e `catalog_precos.json` são gerados em uso e
> ficam fora do controle de versão (ver `.gitignore`).
