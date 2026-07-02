# -*- coding: utf-8 -*-
"""Extrai itens de uma Nota Fiscal (DANFE em PDF) do Boticario/BTMG."""
import re
import pdfplumber

# COD  DESC...  NCM(8)  [CST]  CFOP(4)  UN  QUANT  VUNIT  VTOTAL ...
_LINHA = re.compile(
    r'^(\d{4,6})\s+(.+?)\s+(\d{8})\b.*?(\d{4})\s+UN\s+([\d.,]+)\s+([\d.,]+)\s+([\d.,]+)'
)
_HEADER_KEYS = ('COD.', 'DESCRI', 'PROD.', 'TRIB', 'NCM')


def _num(s):
    return float(s.replace('.', '').replace(',', '.'))


def _limpa_continuacao(s):
    """Uma linha de continuacao de descricao: curta, sem cara de cabecalho/rodape."""
    if not s or len(s.split()) > 5:
        return False
    if any(k in s for k in _HEADER_KEYS):
        return False
    if re.match(r'^\d{6,}', s):        # chave de acesso, NCM solto, etc.
        return False
    # Aceita letras/numeros/unidades (ml, g), barras e pontuacao simples
    return bool(re.match(r'^[A-Za-z0-9/().,\-+ ]+$', s))


def parse_nf(path):
    """Retorna dict com metadados e lista de itens da NF."""
    paginas = []
    with pdfplumber.open(path) as pdf:
        for p in pdf.pages:
            paginas.append(p.extract_text() or '')
    texto = "\n".join(paginas)

    numero = None
    m = re.search(r'N[^\d]{0,3}(\d{3}\.\d{3}\.\d{3})', texto)
    if m:
        numero = m.group(1)
    total = None
    m = re.search(r'R\$\s*([\d.]+,\d{2})', texto)          # "VALOR NOTA NF-e R$ 882,20"
    if m:
        total = _num(m.group(1))
    data = None
    m = re.search(r'(\d{2}/\d{2}/\d{4})', texto)            # 1a data = emissao
    if m:
        data = m.group(1)

    # Parse item por item, restrito a banda "DADOS DO PRODUTO" -> "DADOS ADICIONAIS"
    itens = []
    dentro = False
    for ln in texto.split('\n'):
        s = ln.strip()
        # inicio da tabela: marcador OU a linha de cabecalho das colunas (repete por pagina)
        if 'DADOS DO PRODUTO' in s or ('COD.' in s and 'DESCRI' in s):
            dentro = True
            continue
        if 'DADOS ADICIONAIS' in s:
            dentro = False
            continue
        if not dentro:
            continue
        m = _LINHA.match(s)
        if m:
            cod, desc, ncm, cfop, q, vu, vt = m.groups()
            itens.append({
                'cod': cod, 'desc': desc.strip(), 'ncm': ncm, 'cfop': cfop,
                'qtd': _num(q), 'vunit': _num(vu), 'vtotal': _num(vt),
                'revenda': cfop == '5405',
            })
        elif itens and _limpa_continuacao(s):
            itens[-1]['desc'] += ' ' + s

    return {'numero': numero, 'data': data, 'total': total,
            'fornecedor': 'BTMG COSMETICOS LTDA. (O Boticario)', 'itens': itens}


if __name__ == '__main__':
    import sys, json
    r = parse_nf(sys.argv[1])
    print('NF', r['numero'], '| data', r['data'], '| total', r['total'])
    for i in r['itens']:
        flag = 'REVENDA' if i['revenda'] else 'material'
        print(f"  [{flag:8}] {i['cod']:>6}  x{i['qtd']:>3.0f}  R${i['vunit']:>8.2f}  {i['desc']}")
