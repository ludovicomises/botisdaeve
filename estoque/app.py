# -*- coding: utf-8 -*-
"""Botis da Eve - Controle de Estoque (ferramenta local)."""
import os
import json
import sqlite3
from functools import wraps
from datetime import datetime

from flask import (Flask, request, redirect, url_for, render_template,
                   flash, get_flashed_messages, send_from_directory, send_file,
                   session, abort)
from werkzeug.utils import secure_filename

import nf_parser
import catalog_parser

# Credenciais da area logada (troque aqui quando quiser)
ADMIN_USER = os.environ.get('ESTOQUE_USER', 'admin')
ADMIN_PASS = os.environ.get('ESTOQUE_PASS', 'admin')

# Marcas (slug -> nome exibido) para a area de catalogos
MARCAS = [
    ('boticario', 'O Boticário'),
    ('berenice', 'Quem Disse, Berenice?'),
    ('eudora', 'Eudora'),
    ('oui', 'OUI'),
    ('natura', 'Natura'),
    ('avon', 'Avon'),
]
MARCAS_DICT = dict(MARCAS)

BASE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.dirname(BASE)          # landing page (C:\botisdaeve)
# DATA_DIR: onde ficam banco/uploads. Em produção aponte para um disco PERSISTENTE
# (variavel de ambiente ESTOQUE_DATA). Localmente, usa a propria pasta.
DATA_DIR = os.environ.get('ESTOQUE_DATA', BASE)
os.makedirs(DATA_DIR, exist_ok=True)
DB = os.path.join(DATA_DIR, 'estoque.db')
CATALOG_JSON = os.path.join(DATA_DIR, 'catalog_precos.json')
UPLOAD = os.path.join(DATA_DIR, 'uploads')
os.makedirs(UPLOAD, exist_ok=True)
CATALOGOS_DIR = os.path.join(DATA_DIR, 'catalogos')   # PDFs publicos por marca
os.makedirs(CATALOGOS_DIR, exist_ok=True)

app = Flask(__name__)
# Chave de sessao: em producao defina SECRET_KEY (string aleatoria longa).
app.secret_key = os.environ.get('SECRET_KEY', 'botis-estoque-local-dev')
app.config['MAX_CONTENT_LENGTH'] = 120 * 1024 * 1024   # uploads ate 120MB (catalogos)


# ---------------- Banco ----------------
def db():
    con = sqlite3.connect(DB)
    con.row_factory = sqlite3.Row
    return con


def init_db():
    con = db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS produtos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        codigo TEXT UNIQUE,
        descricao TEXT,
        marca TEXT DEFAULT 'O Boticario',
        custo REAL DEFAULT 0,
        preco_venda REAL DEFAULT 0,
        qtd INTEGER DEFAULT 0,
        tipo TEXT DEFAULT 'venda',     -- 'venda' ou 'brinde'
        ultima_nf TEXT,                -- nº da última NF de entrada
        data_compra TEXT               -- data da última compra
    );
    CREATE TABLE IF NOT EXISTS movimentos(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        produto_id INTEGER,
        tipo TEXT,               -- entrada / saida
        qtd INTEGER,
        valor_unit REAL,
        data TEXT,
        origem TEXT,
        obs TEXT
    );
    CREATE TABLE IF NOT EXISTS nfs(
        numero TEXT PRIMARY KEY,
        data TEXT, total REAL, dt_import TEXT
    );
    CREATE TABLE IF NOT EXISTS clientes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT,
        telefone TEXT,
        endereco TEXT,
        sexo TEXT,
        obs TEXT
    );
    CREATE TABLE IF NOT EXISTS vendas(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER,
        data TEXT,
        total REAL,
        modo TEXT
    );
    CREATE TABLE IF NOT EXISTS venda_itens(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        venda_id INTEGER,
        produto_id INTEGER,
        descricao TEXT,
        qtd INTEGER,
        preco_unit REAL
    );
    CREATE TABLE IF NOT EXISTS catalogos(
        marca TEXT PRIMARY KEY,     -- slug da marca
        arquivo TEXT,               -- nome do PDF salvo (se upload)
        url TEXT,                   -- link externo (se preferir)
        atualizado TEXT
    );
    """)
    # Natura ja aponta para a loja oficial por padrao
    con.execute("INSERT OR IGNORE INTO catalogos(marca,url,atualizado) VALUES(?,?,?)",
                ('natura', 'https://www.minhaloja.natura.com/consultoria/evelinedavid',
                 datetime.now().strftime('%d/%m/%Y')))
    # migracao: adiciona colunas em bancos antigos
    for ddl in ["tipo TEXT DEFAULT 'venda'", 'ultima_nf TEXT',
                'data_compra TEXT', 'codigo_barras TEXT']:
        try:
            con.execute('ALTER TABLE produtos ADD COLUMN ' + ddl)
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()


def money(s):
    """Aceita '89,90' ou '89.90' ou vazio."""
    if s is None:
        return 0.0
    s = str(s).strip().replace('R$', '').replace(' ', '')
    if not s:
        return 0.0
    s = s.replace('.', '').replace(',', '.') if ',' in s else s
    try:
        return float(s)
    except ValueError:
        return 0.0


@app.template_filter('brl')
def brl(v):
    """Formata número no padrão brasileiro: 1234.5 -> '1.234,50'."""
    try:
        v = float(v or 0)
    except (TypeError, ValueError):
        v = 0.0
    s = '{:,.2f}'.format(v)                     # 1,234.56
    return s.replace(',', 'X').replace('.', ',').replace('X', '.')


def load_catalog():
    if os.path.exists(CATALOG_JSON):
        with open(CATALOG_JSON, encoding='utf-8') as f:
            return json.load(f)
    return {}


def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if not session.get('logado'):
            return redirect(url_for('login', next=request.path))
        return f(*a, **kw)
    return wrapper


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        u = (request.form.get('usuario') or '').strip()
        p = request.form.get('senha') or ''
        if u == ADMIN_USER and p == ADMIN_PASS:
            session['logado'] = True
            destino = request.form.get('next') or url_for('home')
            if not destino.startswith('/'):
                destino = url_for('home')
            return redirect(destino)
        flash('Usuário ou senha incorretos.', 'erro')
    return render_template('login.html', next=request.args.get('next', ''))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('landing'))


# ---------------- Rotas ----------------
@app.route('/')
def landing():
    """Serve a landing page (site publico) a partir de C:\\botisdaeve."""
    return send_from_directory(SITE, 'index.html')


@app.route('/img/<path:arquivo>')
def landing_img(arquivo):
    return send_from_directory(os.path.join(SITE, 'img'), arquivo)


@app.route('/estoque')
@login_required
def home():
    con = db()
    todos = con.execute('SELECT * FROM produtos ORDER BY descricao').fetchall()
    movs = con.execute(
        'SELECT m.*, p.descricao AS pdesc FROM movimentos m '
        'LEFT JOIN produtos p ON p.id=m.produto_id '
        'ORDER BY m.id DESC LIMIT 15').fetchall()
    con.close()

    produtos = [p for p in todos if (p['tipo'] or 'venda') == 'venda']
    brindes = [p for p in todos if (p['tipo'] or 'venda') == 'brinde']

    tot_invest = sum(p['qtd'] * p['custo'] for p in produtos)
    tot_venda = sum(p['qtd'] * p['preco_venda'] for p in produtos)
    unidades = sum(p['qtd'] for p in produtos)
    brindes_invest = sum(p['qtd'] * p['custo'] for p in brindes)
    return render_template('estoque.html', produtos=produtos, brindes=brindes,
                           movs=movs, tot_invest=tot_invest, tot_venda=tot_venda,
                           unidades=unidades, brindes_invest=brindes_invest,
                           tem_catalogo=bool(load_catalog()))


@app.route('/importar', methods=['POST'])
@login_required
def importar():
    f = request.files.get('nf')
    if not f or not f.filename:
        flash('Selecione o PDF da nota fiscal.', 'erro')
        return redirect(url_for('home'))
    caminho = os.path.join(UPLOAD, 'nf_' + (secure_filename(f.filename) or 'nota.pdf'))
    f.save(caminho)
    try:
        r = nf_parser.parse_nf(caminho)
    except Exception as e:
        flash('Nao consegui ler a NF: %s' % e, 'erro')
        return redirect(url_for('home'))

    con = db()
    ja = con.execute('SELECT 1 FROM nfs WHERE numero=?',
                     (r['numero'],)).fetchone()
    con.close()

    precos = load_catalog()
    for i in r['itens']:
        i['sugestao'] = precos.get(i['cod'], '')
    return render_template('nf_preview.html', nf=r,
                           revenda=[i for i in r['itens'] if i['revenda']],
                           material=[i for i in r['itens'] if not i['revenda']],
                           ja_importada=bool(ja))


@app.route('/confirmar', methods=['POST'])
@login_required
def confirmar():
    n = int(request.form.get('count', 0))
    numero = request.form.get('nf_numero') or ''
    data = request.form.get('nf_data') or datetime.now().strftime('%d/%m/%Y')
    total = money(request.form.get('nf_total'))
    con = db()
    add = 0
    for k in range(n):
        if request.form.get('incluir_%d' % k) != 'on':
            continue
        cod = request.form.get('cod_%d' % k)
        desc = request.form.get('desc_%d' % k)
        qtd = int(float(request.form.get('qtd_%d' % k) or 0))
        custo = money(request.form.get('custo_%d' % k))
        preco = money(request.form.get('preco_%d' % k))
        tipo = request.form.get('tipo_%d' % k) or 'venda'
        row = con.execute('SELECT * FROM produtos WHERE codigo=?',
                          (cod,)).fetchone()
        if row:
            novo_preco = preco if preco > 0 else row['preco_venda']
            con.execute('UPDATE produtos SET qtd=qtd+?, custo=?, preco_venda=?, '
                        'descricao=?, tipo=?, ultima_nf=?, data_compra=? WHERE codigo=?',
                        (qtd, custo, novo_preco, desc, tipo, numero, data, cod))
            pid = row['id']
        else:
            cur = con.execute(
                'INSERT INTO produtos(codigo,descricao,custo,preco_venda,qtd,tipo,'
                'ultima_nf,data_compra) VALUES(?,?,?,?,?,?,?,?)',
                (cod, desc, custo, preco, qtd, tipo, numero, data))
            pid = cur.lastrowid
        con.execute('INSERT INTO movimentos(produto_id,tipo,qtd,valor_unit,'
                    'data,origem,obs) VALUES(?,?,?,?,?,?,?)',
                    (pid, 'entrada', qtd, custo, data,
                     'NF %s' % numero, ''))
        add += 1
    if numero:
        con.execute('INSERT OR REPLACE INTO nfs(numero,data,total,dt_import) '
                    'VALUES(?,?,?,?)',
                    (numero, data, total, datetime.now().isoformat(timespec='seconds')))
    con.commit()
    con.close()
    flash('%d produto(s) importado(s) da NF %s.' % (add, numero), 'ok')
    return redirect(url_for('home'))


@app.route('/produto/novo', methods=['POST'])
@login_required
def produto_novo():
    cod = (request.form.get('codigo') or '').strip()
    desc = (request.form.get('descricao') or '').strip()
    if not desc:
        flash('Informe a descricao do produto.', 'erro')
        return redirect(url_for('home'))
    qtd = int(float(request.form.get('qtd') or 0))
    custo = money(request.form.get('custo'))
    preco = money(request.form.get('preco_venda'))
    marca = (request.form.get('marca') or 'O Boticario').strip()
    tipo = request.form.get('tipo') or 'venda'
    hoje = datetime.now().strftime('%d/%m/%Y')
    if not cod:
        cod = 'M' + datetime.now().strftime('%H%M%S')
    con = db()
    try:
        cur = con.execute(
            'INSERT INTO produtos(codigo,descricao,marca,custo,preco_venda,qtd,tipo,data_compra) '
            'VALUES(?,?,?,?,?,?,?,?)', (cod, desc, marca, custo, preco, qtd, tipo, hoje))
        pid = cur.lastrowid
        if qtd:
            con.execute('INSERT INTO movimentos(produto_id,tipo,qtd,valor_unit,'
                        'data,origem,obs) VALUES(?,?,?,?,?,?,?)',
                        (pid, 'entrada', qtd, custo, hoje, 'manual', ''))
        con.commit()
        flash('Produto adicionado.', 'ok')
    except sqlite3.IntegrityError:
        flash('Ja existe produto com esse codigo.', 'erro')
    con.close()
    return redirect(url_for('home'))


@app.route('/baixa', methods=['POST'])
@login_required
def baixa():
    pid = request.form.get('produto_id')
    qtd = int(float(request.form.get('qtd') or 0))
    con = db()
    row = con.execute('SELECT * FROM produtos WHERE id=?', (pid,)).fetchone()
    if not row:
        flash('Produto nao encontrado.', 'erro')
    elif qtd <= 0:
        flash('Quantidade invalida.', 'erro')
    elif qtd > row['qtd']:
        flash('Baixa maior que o estoque (%d) de "%s".' % (row['qtd'], row['descricao']), 'erro')
    else:
        con.execute('UPDATE produtos SET qtd=qtd-? WHERE id=?', (qtd, pid))
        con.execute('INSERT INTO movimentos(produto_id,tipo,qtd,valor_unit,'
                    'data,origem,obs) VALUES(?,?,?,?,?,?,?)',
                    (pid, 'saida', qtd, row['preco_venda'],
                     datetime.now().strftime('%d/%m/%Y'), 'venda', ''))
        con.commit()
        flash('Baixa de %d un. de "%s".' % (qtd, row['descricao']), 'ok')
    con.close()
    return redirect(url_for('home'))


@app.route('/produto/<int:pid>/preco', methods=['POST'])
@login_required
def atualiza_preco(pid):
    preco = money(request.form.get('preco_venda'))
    con = db()
    con.execute('UPDATE produtos SET preco_venda=? WHERE id=?', (preco, pid))
    con.commit()
    con.close()
    flash('Preco de venda atualizado.', 'ok')
    return redirect(url_for('home'))


@app.route('/produto/<int:pid>/remover', methods=['POST'])
@login_required
def remover(pid):
    con = db()
    con.execute('DELETE FROM produtos WHERE id=?', (pid,))
    con.execute('DELETE FROM movimentos WHERE produto_id=?', (pid,))
    con.commit()
    con.close()
    flash('Produto removido.', 'ok')
    return redirect(url_for('home'))


@app.route('/produto/<int:pid>/editar', methods=['GET', 'POST'])
@login_required
def editar_produto(pid):
    con = db()
    p = con.execute('SELECT * FROM produtos WHERE id=?', (pid,)).fetchone()
    if not p:
        con.close()
        flash('Produto não encontrado.', 'erro')
        return redirect(url_for('home'))
    if request.method == 'POST':
        cod = (request.form.get('codigo') or '').strip()
        barras = (request.form.get('codigo_barras') or '').strip()
        desc = (request.form.get('descricao') or '').strip()
        marca = (request.form.get('marca') or 'O Boticario').strip()
        tipo = request.form.get('tipo') or 'venda'
        custo = money(request.form.get('custo'))
        preco = money(request.form.get('preco_venda'))
        qtd = int(float(request.form.get('qtd') or 0))
        dif = qtd - p['qtd']
        try:
            con.execute('UPDATE produtos SET codigo=?, codigo_barras=?, descricao=?, '
                        'marca=?, tipo=?, custo=?, preco_venda=?, qtd=? WHERE id=?',
                        (cod or p['codigo'], barras, desc, marca, tipo, custo, preco, qtd, pid))
            if dif != 0:
                con.execute('INSERT INTO movimentos(produto_id,tipo,qtd,valor_unit,'
                            'data,origem,obs) VALUES(?,?,?,?,?,?,?)',
                            (pid, 'entrada' if dif > 0 else 'saida', abs(dif), custo,
                             datetime.now().strftime('%d/%m/%Y'), 'ajuste manual', ''))
            con.commit()
            flash('Produto atualizado.', 'ok')
        except sqlite3.IntegrityError:
            flash('Já existe outro produto com esse código.', 'erro')
        con.close()
        return redirect(url_for('home'))
    con.close()
    return render_template('produto_editar.html', p=p)


# ---------------- Clientes ----------------
@app.route('/clientes')
@login_required
def clientes():
    con = db()
    lista = con.execute('SELECT * FROM clientes ORDER BY nome').fetchall()
    con.close()
    return render_template('clientes.html', clientes=lista)


@app.route('/cliente/novo', methods=['POST'])
@login_required
def cliente_novo():
    nome = (request.form.get('nome') or '').strip()
    if not nome:
        flash('Informe o nome do cliente.', 'erro')
        return redirect(url_for('clientes'))
    con = db()
    con.execute('INSERT INTO clientes(nome,telefone,endereco,sexo,obs) VALUES(?,?,?,?,?)',
                (nome, request.form.get('telefone', ''), request.form.get('endereco', ''),
                 request.form.get('sexo', ''), request.form.get('obs', '')))
    con.commit()
    con.close()
    flash('Cliente cadastrado.', 'ok')
    return redirect(url_for('clientes'))


@app.route('/cliente/<int:cid>/editar', methods=['POST'])
@login_required
def cliente_editar(cid):
    con = db()
    con.execute('UPDATE clientes SET nome=?, telefone=?, endereco=?, sexo=?, obs=? WHERE id=?',
                ((request.form.get('nome') or '').strip(), request.form.get('telefone', ''),
                 request.form.get('endereco', ''), request.form.get('sexo', ''),
                 request.form.get('obs', ''), cid))
    con.commit()
    con.close()
    flash('Cliente atualizado.', 'ok')
    return redirect(url_for('clientes'))


@app.route('/cliente/<int:cid>/remover', methods=['POST'])
@login_required
def cliente_remover(cid):
    con = db()
    con.execute('DELETE FROM clientes WHERE id=?', (cid,))
    con.commit()
    con.close()
    flash('Cliente removido.', 'ok')
    return redirect(url_for('clientes'))


# ---------------- Vendas ----------------
@app.route('/vendas')
@login_required
def vendas():
    con = db()
    cli = con.execute('SELECT id,nome,telefone FROM clientes ORDER BY nome').fetchall()
    recentes = con.execute(
        'SELECT v.*, c.nome AS cliente, '
        '(SELECT COALESCE(SUM(qtd),0) FROM venda_itens WHERE venda_id=v.id) AS n_itens '
        'FROM vendas v LEFT JOIN clientes c ON c.id=v.cliente_id '
        'ORDER BY v.id DESC LIMIT 15').fetchall()
    ids = [v['id'] for v in recentes]
    itens_por_venda = {}
    if ids:
        marc = ','.join('?' * len(ids))
        for it in con.execute(
                'SELECT * FROM venda_itens WHERE venda_id IN (%s)' % marc, ids).fetchall():
            itens_por_venda.setdefault(it['venda_id'], []).append(it)
    con.close()
    return render_template('vendas.html', clientes=cli, recentes=recentes,
                           itens_por_venda=itens_por_venda)


@app.route('/api/produtos')
@login_required
def api_produtos():
    q = (request.args.get('q') or '').strip()
    con = db()
    like = '%' + q + '%'
    rows = con.execute(
        'SELECT id,codigo,codigo_barras,descricao,marca,preco_venda,qtd,tipo '
        'FROM produtos WHERE (descricao LIKE ? OR codigo LIKE ? OR codigo_barras LIKE ?) '
        'ORDER BY descricao LIMIT 30', (like, like, like)).fetchall()
    con.close()
    return {'produtos': [dict(r) for r in rows]}


@app.route('/api/produto')
@login_required
def api_produto():
    """Busca exata por codigo de barras ou codigo interno (modo scanner)."""
    cod = (request.args.get('codigo') or '').strip()
    con = db()
    row = con.execute(
        'SELECT id,codigo,codigo_barras,descricao,marca,preco_venda,qtd,tipo '
        'FROM produtos WHERE codigo_barras=? OR codigo=? LIMIT 1', (cod, cod)).fetchone()
    con.close()
    if row:
        return {'ok': True, 'produto': dict(row)}
    return {'ok': False}


@app.route('/api/associar-barras', methods=['POST'])
@login_required
def api_associar_barras():
    """Vincula um codigo de barras escaneado a um produto (por codigo interno)."""
    data = request.get_json(silent=True) or {}
    cod = (data.get('codigo') or '').strip()
    barras = (data.get('codigo_barras') or '').strip()
    con = db()
    row = con.execute('SELECT * FROM produtos WHERE codigo=?', (cod,)).fetchone()
    if not row:
        con.close()
        return {'ok': False, 'erro': 'produto não encontrado'}
    con.execute('UPDATE produtos SET codigo_barras=? WHERE id=?', (barras, row['id']))
    con.commit()
    prod = con.execute(
        'SELECT id,codigo,codigo_barras,descricao,marca,preco_venda,qtd,tipo '
        'FROM produtos WHERE id=?', (row['id'],)).fetchone()
    con.close()
    return {'ok': True, 'produto': dict(prod)}


@app.route('/vendas/finalizar', methods=['POST'])
@login_required
def vendas_finalizar():
    data = request.get_json(silent=True) or {}
    itens = data.get('itens') or []
    if not itens:
        return {'ok': False, 'erro': 'Carrinho vazio.'}
    cliente_id = data.get('cliente_id') or None
    modo = data.get('modo') or 'busca'
    con = db()
    # valida estoque
    for it in itens:
        row = con.execute('SELECT qtd,descricao FROM produtos WHERE id=?',
                          (it['produto_id'],)).fetchone()
        if not row:
            con.close()
            return {'ok': False, 'erro': 'Produto não encontrado no estoque.'}
        if int(it['qtd']) > row['qtd']:
            con.close()
            return {'ok': False, 'erro': 'Estoque insuficiente de "%s" (tem %d).'
                    % (row['descricao'], row['qtd'])}
    total = sum(float(it['preco']) * int(it['qtd']) for it in itens)
    dh = datetime.now().strftime('%d/%m/%Y %H:%M')
    cur = con.execute('INSERT INTO vendas(cliente_id,data,total,modo) VALUES(?,?,?,?)',
                      (cliente_id, dh, total, modo))
    vid = cur.lastrowid
    for it in itens:
        pid = it['produto_id']
        q = int(it['qtd'])
        preco = float(it['preco'])
        prod = con.execute('SELECT descricao,preco_venda FROM produtos WHERE id=?', (pid,)).fetchone()
        con.execute('INSERT INTO venda_itens(venda_id,produto_id,descricao,qtd,preco_unit) '
                    'VALUES(?,?,?,?,?)', (vid, pid, prod['descricao'], q, preco))
        con.execute('UPDATE produtos SET qtd=qtd-? WHERE id=?', (q, pid))
        # se o preco de venda estava vazio/0, grava o preco praticado
        if not prod['preco_venda']:
            con.execute('UPDATE produtos SET preco_venda=? WHERE id=?', (preco, pid))
        con.execute('INSERT INTO movimentos(produto_id,tipo,qtd,valor_unit,data,origem,obs) '
                    'VALUES(?,?,?,?,?,?,?)',
                    (pid, 'saida', q, preco, datetime.now().strftime('%d/%m/%Y'),
                     'venda #%d' % vid, ''))
    con.commit()
    con.close()
    return {'ok': True, 'venda_id': vid, 'total': total}


# ---------------- Catalogos por marca ----------------
@app.route('/catalogos')
@login_required
def catalogos_admin():
    con = db()
    rows = {r['marca']: r for r in con.execute('SELECT * FROM catalogos').fetchall()}
    con.close()
    lista = []
    for slug, nome in MARCAS:
        r = rows.get(slug)
        lista.append({'slug': slug, 'nome': nome,
                      'arquivo': r['arquivo'] if r else None,
                      'url': r['url'] if r else None,
                      'atualizado': r['atualizado'] if r else None})
    return render_template('catalogos.html', marcas=lista)


@app.route('/catalogos/<marca>', methods=['POST'])
@login_required
def catalogos_salvar(marca):
    if marca not in MARCAS_DICT:
        abort(404)
    f = request.files.get('arquivo')
    url = (request.form.get('url') or '').strip()
    hoje = datetime.now().strftime('%d/%m/%Y')
    con = db()
    if f and f.filename:
        nome = marca + '.pdf'
        f.save(os.path.join(CATALOGOS_DIR, nome))
        con.execute('INSERT INTO catalogos(marca,arquivo,url,atualizado) VALUES(?,?,?,?) '
                    'ON CONFLICT(marca) DO UPDATE SET arquivo=?, url=?, atualizado=?',
                    (marca, nome, '', hoje, nome, '', hoje))
        flash('Catálogo de %s enviado (PDF).' % MARCAS_DICT[marca], 'ok')
    elif url:
        con.execute('INSERT INTO catalogos(marca,arquivo,url,atualizado) VALUES(?,?,?,?) '
                    'ON CONFLICT(marca) DO UPDATE SET arquivo=?, url=?, atualizado=?',
                    (marca, '', url, hoje, '', url, hoje))
        flash('Catálogo de %s salvo (link).' % MARCAS_DICT[marca], 'ok')
    else:
        flash('Envie um PDF ou informe um link.', 'erro')
    con.commit()
    con.close()
    return redirect(url_for('catalogos_admin'))


@app.route('/catalogos/<marca>/remover', methods=['POST'])
@login_required
def catalogos_remover(marca):
    con = db()
    row = con.execute('SELECT arquivo FROM catalogos WHERE marca=?', (marca,)).fetchone()
    if row and row['arquivo']:
        try:
            os.remove(os.path.join(CATALOGOS_DIR, row['arquivo']))
        except OSError:
            pass
    con.execute('DELETE FROM catalogos WHERE marca=?', (marca,))
    con.commit()
    con.close()
    flash('Catálogo removido.', 'ok')
    return redirect(url_for('catalogos_admin'))


@app.route('/catalogo/<marca>')
def catalogo_publico(marca):
    """Rota PUBLICA: mostra o catalogo da marca (o site liga aqui)."""
    if marca not in MARCAS_DICT:
        abort(404)
    con = db()
    row = con.execute('SELECT * FROM catalogos WHERE marca=?', (marca,)).fetchone()
    con.close()
    if row and row['url']:
        return redirect(row['url'])
    if row and row['arquivo']:
        caminho = os.path.join(CATALOGOS_DIR, row['arquivo'])
        if os.path.exists(caminho):
            return send_file(caminho, mimetype='application/pdf')
    # sem catalogo ainda -> pagina amigavel
    return render_template('catalogo_indisponivel.html', nome=MARCAS_DICT[marca])


@app.route('/catalogo', methods=['POST'])
@login_required
def catalogo():
    f = request.files.get('catalogo')
    if not f or not f.filename:
        flash('Selecione o PDF do catalogo.', 'erro')
        return redirect(url_for('home'))
    caminho = os.path.join(UPLOAD, 'cat_' + (secure_filename(f.filename) or 'catalogo.pdf'))
    f.save(caminho)
    try:
        precos = catalog_parser.extrai_precos(caminho)
    except Exception as e:
        flash('Nao consegui ler o catalogo: %s' % e, 'erro')
        return redirect(url_for('home'))
    with open(CATALOG_JSON, 'w', encoding='utf-8') as out:
        json.dump(precos, out)
    flash('Catalogo processado: %d precos guardados para sugestao.' % len(precos), 'ok')
    return redirect(url_for('home'))


# inicializa o banco ao importar (funciona tambem sob gunicorn/WSGI em producao)
init_db()

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    # abre o navegador so no uso local (nao em servidor)
    if os.environ.get('ESTOQUE_DATA') is None:
        import webbrowser
        webbrowser.open('http://127.0.0.1:%d' % port)
    app.run(debug=False, host='0.0.0.0', port=port)
