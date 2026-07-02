# -*- coding: utf-8 -*-
"""Extrai pares (codigo -> preco de venda) de um catalogo Boticario (PDF).

ATENCAO: catalogo e layout de marketing; a associacao codigo<->preco e
heuristica (melhor-esforco) e deve ser CONFERIDA pelo usuario.
"""
import re
import pdfplumber

_COD = re.compile(r'\b(\d{5})\b')
_PRECO = re.compile(r'R\$\s*([\d.]+,\d{2})')


def _num(s):
    return float(s.replace('.', '').replace(',', '.'))


def extrai_precos(path, progress=None):
    """Retorna {codigo: preco}. Heuristica: associa cada codigo ao preco
    mais proximo na mesma pagina (janela de texto)."""
    precos = {}
    with pdfplumber.open(path) as pdf:
        n = len(pdf.pages)
        for idx, page in enumerate(pdf.pages):
            if progress and idx % 20 == 0:
                progress(idx, n)
            t = page.extract_text() or ''
            # posicoes de codigos e precos no texto da pagina
            cods = [(m.start(), m.group(1)) for m in _COD.finditer(t)]
            prcs = [(m.start(), _num(m.group(1))) for m in _PRECO.finditer(t)]
            if not cods or not prcs:
                continue
            for pos, cod in cods:
                # preco mais proximo (por distancia no texto)
                melhor = min(prcs, key=lambda pp: abs(pp[0] - pos))
                dist = abs(melhor[0] - pos)
                if dist > 400:      # muito longe -> ignora
                    continue
                # mantem a ocorrencia mais PROXIMA (menor distancia) entre paginas
                if cod not in precos or dist < precos[cod][0]:
                    precos[cod] = (dist, melhor[1])
    return {c: v for c, (d, v) in precos.items()}


if __name__ == '__main__':
    import sys
    def prog(i, n):
        print(f'  ...pagina {i}/{n}')
    p = extrai_precos(sys.argv[1], progress=prog)
    print(f'{len(p)} codigos com preco extraidos (amostra):')
    for c, v in list(p.items())[:20]:
        print(f'  {c}  R$ {v:.2f}')
