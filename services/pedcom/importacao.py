"""
Importação da planilha de Pedidos de Compra PJ (RH).

Layout esperado (confirmado em Layout_Pedido_Compra_PJ_v2_1.xlsx):
  - Linha 1: cabeçalho (nomes das colunas)
  - Linha 2: linha de descrição/instrução (ignorada)
  - Linha 3+: dados

Colunas (ordem exata):
  NOME_COLABORADOR, CODFORNECEDOR, LOJAFORNEC, CODIGOCOND,
  CODCC, CODCLVL, CODIGOPRODUTO, MESINICIAL, ANOREFERENCIA,
  QTDMESES, CODITEMCTA, VALORMENSAL

Regra de agrupamento:
  Cada linha = 1 rateio. Um colaborador com N negócios = N linhas com o
  mesmo par (CODFORNECEDOR, LOJAFORNEC). O agrupamento forma os RATEIOS
  do pedido enviado ao webservice.

A função principal retorna um dict com:
  - 'itens'   : list[dict] — pedidos agrupados, prontos para persistência
  - 'erros'   : list[str]  — erros estruturais (impedimentos críticos)
  - 'avisos'  : list[str]  — inconsistências não fatais (ex: linhas vazias puladas)
  - 'codcc'   : str | None — CC único encontrado (None se inconsistente)
  - 'codclvl' : str | None — CLVL único encontrado (None se inconsistente)
  - 'total_linhas_lidas': int
"""
from __future__ import annotations

import io

import openpyxl

COLUNAS_ESPERADAS = [
    'NOME_COLABORADOR',
    'CODFORNECEDOR',
    'LOJAFORNEC',
    'CODIGOCOND',
    'CODCC',
    'CODCLVL',
    'CODIGOPRODUTO',
    'MESINICIAL',
    'ANOREFERENCIA',
    'QTDMESES',
    'CODITEMCTA',
    'VALORMENSAL',
]

_N_COLUNAS = len(COLUNAS_ESPERADAS)


def _cel(valor) -> str:
    """Normaliza célula para string sem espaços em branco."""
    if valor is None:
        return ''
    return str(valor).strip()


def importar_xlsx(arquivo_bytes: bytes) -> dict:
    """Lê a planilha do RH e retorna os pedidos agrupados por colaborador.

    Parâmetros
    ----------
    arquivo_bytes : bytes
        Conteúdo binário do arquivo .xlsx

    Retorno
    -------
    dict com chaves: itens, erros, avisos, codcc, codclvl, total_linhas_lidas
    """
    erros: list[str] = []
    avisos: list[str] = []

    try:
        wb = openpyxl.load_workbook(io.BytesIO(arquivo_bytes), data_only=True)
    except Exception as e:
        return {
            'itens': [],
            'erros': [f'Não foi possível abrir o arquivo: {e}'],
            'avisos': [],
            'codcc': None,
            'codclvl': None,
            'total_linhas_lidas': 0,
        }

    ws = wb.active

    # ── Validação do cabeçalho ────────────────────────────────────────────────
    cabecalho = [_cel(ws.cell(1, c).value) for c in range(1, _N_COLUNAS + 1)]
    if cabecalho != COLUNAS_ESPERADAS:
        erros.append(
            f'Cabeçalho da planilha não corresponde ao layout esperado. '
            f'Esperado: {COLUNAS_ESPERADAS}. '
            f'Encontrado: {cabecalho}'
        )
        return {
            'itens': [],
            'erros': erros,
            'avisos': avisos,
            'codcc': None,
            'codclvl': None,
            'total_linhas_lidas': 0,
        }

    # ── Leitura das linhas de dados (a partir da linha 3) ────────────────────
    # Linha 1 = cabeçalho, linha 2 = descrição das colunas (ignorada)
    agrupados: dict[tuple[str, str], dict] = {}
    codccs: set[str] = set()
    codclvls: set[str] = set()
    total_linhas_lidas = 0

    for num_linha in range(3, ws.max_row + 1):
        valores = [_cel(ws.cell(num_linha, c).value) for c in range(1, _N_COLUNAS + 1)]

        # Ignora linhas completamente vazias
        if not any(valores):
            continue

        total_linhas_lidas += 1
        row = dict(zip(COLUNAS_ESPERADAS, valores))

        # Coleta CC e CLVL para verificação de consistência
        if row['CODCC']:
            codccs.add(row['CODCC'])
        if row['CODCLVL']:
            codclvls.add(row['CODCLVL'])

        chave = (row['CODFORNECEDOR'], row['LOJAFORNEC'])

        if chave not in agrupados:
            agrupados[chave] = {
                'nome_colaborador': row['NOME_COLABORADOR'],
                'CODFORNECEDOR':    row['CODFORNECEDOR'],
                'LOJAFORNEC':       row['LOJAFORNEC'],
                'CODIGOCOND':       row['CODIGOCOND'],
                'CODCC':            row['CODCC'],
                'CODCLVL':          row['CODCLVL'],
                'CODIGOPRODUTO':    row['CODIGOPRODUTO'],
                'MESINICIAL':       row['MESINICIAL'],
                'ANOREFERENCIA':    row['ANOREFERENCIA'],
                'QTDMESES':         row['QTDMESES'],
                'rateios':          [],
                '_linhas_planilha': [],
            }
        else:
            # Colaborador com múltiplos rateios: verifica consistência dos campos
            # de cabeçalho (deve ser idêntico nas linhas repetidas)
            existente = agrupados[chave]
            for campo in ('CODIGOCOND', 'CODCC', 'CODCLVL', 'CODIGOPRODUTO',
                          'MESINICIAL', 'ANOREFERENCIA', 'QTDMESES'):
                if row[campo] and row[campo] != existente[campo]:
                    avisos.append(
                        f'Linha {num_linha}: colaborador {row["CODFORNECEDOR"]}/'
                        f'{row["LOJAFORNEC"]} tem valor inconsistente em {campo} '
                        f'({row[campo]!r} vs {existente[campo]!r}). '
                        f'Usando o valor da primeira linha.'
                    )

        agrupados[chave]['rateios'].append({
            'CODITEMCTA':  row['CODITEMCTA'],
            'VALORMENSAL': row['VALORMENSAL'],
        })
        agrupados[chave]['_linhas_planilha'].append(num_linha)

    if total_linhas_lidas == 0:
        erros.append('A planilha não contém linhas de dados (a partir da linha 3).')

    # ── Verificação de consistência de CC / CLVL no lote ─────────────────────
    if len(codccs) > 1:
        erros.append(
            f'CODCC não é único no arquivo: {", ".join(sorted(codccs))}. '
            'Todos os pedidos do mesmo lote semestral devem usar o mesmo Centro de Custo.'
        )
    if len(codclvls) > 1:
        erros.append(
            f'CODCLVL não é único no arquivo: {", ".join(sorted(codclvls))}. '
            'Todos os pedidos do mesmo lote semestral devem usar a mesma Classe de Valor.'
        )

    return {
        'itens':              list(agrupados.values()),
        'erros':              erros,
        'avisos':             avisos,
        'codcc':              list(codccs)[0] if len(codccs) == 1 else None,
        'codclvl':            list(codclvls)[0] if len(codclvls) == 1 else None,
        'total_linhas_lidas': total_linhas_lidas,
    }
