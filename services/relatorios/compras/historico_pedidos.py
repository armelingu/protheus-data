import csv
import io
from datetime import timedelta

from database import conectar_pedidos, agora
from services.protheus_readonly import executar_select
from time_utils import format_protheus_date, parse_protheus_date

import os
from dotenv import load_dotenv

load_dotenv()

SYNC_LOOKBACK_DAYS = int(os.getenv('SYNC_LOOKBACK_DAYS', '30'))

HISTORICO_DATA_INICIO = '20240101'

COLUNAS = [
    'USUARIO', 'FILIAL', 'PEDIDO_COMPRA', 'ITEM', 'PRODUTO',
    'DESCRICAO_PRODUTO', 'QUANTIDADE', 'COD_FORNECEDOR', 'FORNECEDOR',
    'DEPOSITO_ESTOQUE', 'DATA_EMISSAO'
]

QUERY_HISTORICO_BASE = f"""
SELECT
    USR.USR_NOME      AS USUARIO,
    SC7.C7_FILIAL     AS FILIAL,
    SC7.C7_NUM        AS PEDIDO_COMPRA,
    SC7.C7_ITEM       AS ITEM,
    SC7.C7_PRODUTO    AS PRODUTO,
    SC7.C7_DESCRI     AS DESCRICAO_PRODUTO,
    SC7.C7_QUANT      AS QUANTIDADE,
    SC7.C7_FORNECE    AS COD_FORNECEDOR,
    SA2.A2_NOME       AS FORNECEDOR,
    SC7.C7_LOCAL      AS DEPOSITO_ESTOQUE,
    SC7.C7_EMISSAO    AS DATA_EMISSAO
FROM SC7010A SC7
INNER JOIN SYS_USR USR
    ON USR.USR_ID = SC7.C7_USER
    AND USR.D_E_L_E_T_ = ''
LEFT JOIN SA2010 SA2
    ON SA2.A2_COD = SC7.C7_FORNECE
    AND SA2.A2_LOJA = SC7.C7_LOJA
    AND SA2.D_E_L_E_T_ = ''
WHERE SC7.D_E_L_E_T_ = ''
    AND SC7.C7_EMISSAO >= '{HISTORICO_DATA_INICIO}'
"""

QUERY_HISTORICO_NOVOS = (
    QUERY_HISTORICO_BASE
    + "    AND SC7.C7_EMISSAO >= ?\nORDER BY SC7.C7_EMISSAO DESC"
)
QUERY_HISTORICO_COMPLETA = QUERY_HISTORICO_BASE + "ORDER BY SC7.C7_EMISSAO DESC"

SELECT_HISTORICO = (
    'SELECT usuario, filial, pedido_compra, item, produto, '
    'descricao_produto, quantidade, cod_fornecedor, fornecedor, '
    'deposito_estoque, data_emissao '
    'FROM pedidos_historico'
)


def _construir_query_export_historico(data_inicio=None, data_fim=None):
    """Monta SELECT com filtro de data opcional. Datas no formato YYYYMMDD (Protheus)."""
    sql = (
        'SELECT usuario, filial, pedido_compra, item, produto, '
        'descricao_produto, quantidade, cod_fornecedor, fornecedor, '
        'deposito_estoque, data_emissao FROM pedidos_historico'
    )
    params = []
    condicoes = []
    if data_inicio:
        condicoes.append('data_emissao >= ?')
        params.append(data_inicio)
    if data_fim:
        condicoes.append('data_emissao <= ?')
        params.append(data_fim)
    if condicoes:
        sql += ' WHERE ' + ' AND '.join(condicoes)
    sql += ' ORDER BY data_emissao DESC'
    return sql, params

INSERT_HISTORICO = '''
    INSERT INTO pedidos_historico
    (usuario, filial, pedido_compra, item, produto,
     descricao_produto, quantidade, cod_fornecedor,
     fornecedor, deposito_estoque, data_emissao)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(filial, pedido_compra, item) DO UPDATE SET
        usuario           = excluded.usuario,
        produto           = excluded.produto,
        descricao_produto = excluded.descricao_produto,
        quantidade        = excluded.quantidade,
        cod_fornecedor    = excluded.cod_fornecedor,
        fornecedor        = excluded.fornecedor,
        deposito_estoque  = excluded.deposito_estoque,
        data_emissao      = excluded.data_emissao
'''


def registrar_sync_event_historico(registros_novos, status, erro_resumo=None,
                                   total_protheus=None, total_local=None):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO historico_sync_log '
        '(executado_em, registros_novos, status, erro_resumo, total_protheus, total_local) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (agora(), registros_novos, status, erro_resumo, total_protheus, total_local)
    )
    conn.commit()
    conn.close()


def _detectar_e_remover_deletados_historico(chaves_protheus, data_corte, conn):
    """Remove registros do cache local que sumiram do Protheus na janela de lookback."""
    locais = conn.execute(
        'SELECT filial, pedido_compra, item FROM pedidos_historico WHERE data_emissao >= ?',
        (data_corte,)
    ).fetchall()

    para_deletar = [
        (r['filial'], r['pedido_compra'], r['item'])
        for r in locais
        if (r['filial'], r['pedido_compra'], r['item']) not in chaves_protheus
    ]

    if para_deletar:
        conn.executemany(
            'DELETE FROM pedidos_historico WHERE filial=? AND pedido_compra=? AND item=?',
            para_deletar
        )

    return len(para_deletar)


def _norm(v):
    """Normaliza valor para comparação consistente (mesma regra do upsert).

    NB: pedidos.py original usa `str(val).strip() if val else ''`, que
    converte 0/0.0 em '' (falsy). Mantemos essa semântica aqui para que o
    diff bata com o que será gravado pelo upsert.
    """
    return str(v).strip() if v else ''


def _contar_mutacoes_historico(conn, dados, data_corte):
    """Compara o lote do Protheus com o estado local na janela e retorna
    (novos, atualizados). Sem isso, registros_novos seria sempre 0 quando
    houvesse apenas updates (UPSERT não muda COUNT(*))."""
    if not dados:
        return 0, 0

    where = 'data_emissao >= ?' if data_corte else '1=1'
    params = (data_corte,) if data_corte else ()
    locais_rows = conn.execute(
        SELECT_HISTORICO + f' WHERE {where}', params
    ).fetchall()

    # SELECT_HISTORICO segue a ordem de COLUNAS. Chave: filial(1), pedido(2), item(3).
    KEY_IDX = (1, 2, 3)
    locais_by_key = {}
    for row in locais_rows:
        key = tuple(_norm(row[i]) for i in KEY_IDX)
        locais_by_key[key] = tuple(_norm(v) for v in row)

    novos = atualizados = 0
    for d in dados:
        key = (d[1], d[2], d[3])
        if key not in locais_by_key:
            novos += 1
        elif locais_by_key[key] != tuple(_norm(v) for v in d):
            atualizados += 1
    return novos, atualizados


def _upsert_historico_no_sqlite(linhas, data_corte=None):
    total_protheus = len(linhas)

    conn = conectar_pedidos()
    try:
        if not linhas:
            total_local = conn.execute(
                'SELECT COUNT(*) FROM pedidos_historico WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0] if data_corte else conn.execute(
                'SELECT COUNT(*) FROM pedidos_historico'
            ).fetchone()[0]
            registrar_sync_event_historico(0, 'sem_novos', total_protheus=0, total_local=total_local)
            return 0

        dados = [
            tuple(_norm(val) for val in linha)
            for linha in linhas
        ]
        chaves_protheus = {(d[1], d[2], d[3]) for d in dados}

        try:
            novos, atualizados = _contar_mutacoes_historico(conn, dados, data_corte)
        except Exception as exc_diff:
            print(f'[HISTORICO] diff falhou ({exc_diff}); aplicando upsert cego.')
            novos, atualizados = total_protheus, 0

        if (novos + atualizados) > 0:
            conn.executemany(INSERT_HISTORICO, dados)

        removidos = 0
        if data_corte:
            removidos = _detectar_e_remover_deletados_historico(chaves_protheus, data_corte, conn)

        conn.commit()

        if data_corte:
            total_local = conn.execute(
                'SELECT COUNT(*) FROM pedidos_historico WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0]
        else:
            total_local = conn.execute('SELECT COUNT(*) FROM pedidos_historico').fetchone()[0]
    finally:
        conn.close()

    mutacoes = novos + atualizados + removidos
    divergencia = abs(total_protheus - total_local) / max(total_protheus, 1)
    if divergencia > 0.05:
        status = 'alerta'
    elif mutacoes > 0:
        status = 'sucesso'
    else:
        status = 'sem_novos'

    registrar_sync_event_historico(
        mutacoes, status,
        total_protheus=total_protheus,
        total_local=total_local,
    )
    return mutacoes


def _calcular_data_corte_historico(data_emissao_maxima):
    if not data_emissao_maxima:
        return None
    data_base = parse_protheus_date(data_emissao_maxima)
    data_corte = data_base - timedelta(days=SYNC_LOOKBACK_DAYS)
    return format_protheus_date(data_corte)


def carga_inicial_historico():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pedidos_historico').fetchone()[0]
    conn.close()

    if total > 0:
        return 0

    linhas = executar_select(QUERY_HISTORICO_COMPLETA)
    return _upsert_historico_no_sqlite(linhas)


def sincronizar_historico():
    conn = conectar_pedidos()
    resultado = conn.execute('SELECT MAX(data_emissao) FROM pedidos_historico').fetchone()[0]
    conn.close()

    if resultado:
        data_corte = _calcular_data_corte_historico(resultado)
        linhas = executar_select(QUERY_HISTORICO_NOVOS, (data_corte,))
    else:
        data_corte = None
        linhas = executar_select(QUERY_HISTORICO_COMPLETA)

    return _upsert_historico_no_sqlite(linhas, data_corte=data_corte)


def info_relatorio_historico():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pedidos_historico').fetchone()[0]
    sync = conn.execute(
        'SELECT executado_em, registros_novos, '
        "COALESCE(status, CASE WHEN registros_novos > 0 THEN 'sucesso' ELSE 'sem_novos' END) AS status, "
        'erro_resumo '
        'FROM historico_sync_log ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    if not sync:
        return total, None, 'nunca', None
    return total, sync['executado_em'], sync['status'], sync['erro_resumo']


def historico_sync_historico(limit=10):
    conn = conectar_pedidos()
    linhas = conn.execute(
        'SELECT executado_em, registros_novos FROM historico_sync_log '
        'WHERE registros_novos > 0 '
        'ORDER BY id DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    return linhas


def gerar_csv_historico(data_inicio=None, data_fim=None):
    sql, params = _construir_query_export_historico(data_inicio, data_fim)
    conn = conectar_pedidos()
    linhas = conn.execute(sql, params).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(COLUNAS)
    for linha in linhas:
        writer.writerow([str(val).strip() if val else '' for val in linha])
    output.seek(0)
    return output.getvalue(), len(linhas)


def gerar_excel_historico(data_inicio=None, data_fim=None):
    from openpyxl import Workbook

    sql, params = _construir_query_export_historico(data_inicio, data_fim)
    conn = conectar_pedidos()
    linhas = conn.execute(sql, params).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = 'Histórico de Pedidos'
    ws.append(COLUNAS)

    for linha in linhas:
        ws.append([str(val).strip() if val else '' for val in linha])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue(), len(linhas)
