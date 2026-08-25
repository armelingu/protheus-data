"""
Relatório: Pedidos de Compra Detalhado (Compras)

Idêntico ao relatório padrão de Pedidos de Compra, mas enriquecido com
quatro campos descritivos obtidos via JOIN direto no SQL:

  C7_CC       → CTT010.CTT_DESC01  (descrição do centro de custo)
  C7_ITEMCTA  → CTD010.CTD_DESC01  (descrição do item orçamentário)
  C7_CONTA    → CT1010.CT1_DESC01  (descrição da conta contábil)
  C7_COND     → SE4010.E4_DESCRI   (descrição da condição de pagamento)
"""
from __future__ import annotations

import csv
import io
import os
from datetime import timedelta

from dotenv import load_dotenv

from services.database import conectar_pedidos, agora
from services.protheus_readonly import executar_select
from services.time_utils import format_protheus_date, parse_protheus_date

load_dotenv()

# ── Lookback ──────────────────────────────────────────────────────────────────

def _lookback():
    for chave in ('SYNC_LOOKBACK_PEDIDOS', 'SYNC_LOOKBACK_DAYS'):
        val = os.getenv(chave)
        if val:
            try:
                return max(1, int(val))
            except (TypeError, ValueError):
                pass
    return 60


SYNC_LOOKBACK_DAYS = _lookback()

# ── Compradores (mesmo filtro do relatório padrão) ────────────────────────────

USUARIOS = "('000331', '000189', '000433', '000341', '000430', '000442', '000373', '000286', '000421', '000514', '000520', '000521')"

# ── Colunas ───────────────────────────────────────────────────────────────────

COLUNAS = [
    'USUARIO', 'FILIAL', 'PEDIDO_COMPRA', 'ITEM', 'PRODUTO',
    'UNIDADE', 'DESCRICAO_PRODUTO', 'QUANTIDADE', 'PRECO_UNITARIO',
    'PRECO_TOTAL', 'DATA_ENTREGA', 'NUMERO_SC', 'ITEM_SC',
    'OBSERVACOES', 'CLASSE_VALOR', 'QTD_ENTREGUE', 'NUM_COTACAO',
    'MOEDA', 'COD_FORNECEDOR', 'FORNECEDOR', 'DEPOSITO_ESTOQUE',
    'DATA_EMISSAO', 'REVISAO', 'NIVEL_APROVACAO', 'APROVADOR', 'DATA_APROVACAO',
    'STATUS_APROVACAO',
    # ── novas colunas ──
    'CENTRO_CUSTO', 'CENTRO_CUSTO_DESC',
    'ITEM_CONTA', 'ITEM_CONTA_DESC',
    'CONTA_CONTABIL', 'CONTA_CONTABIL_DESC',
    'COND_PAGAMENTO', 'COND_PAGAMENTO_DESC',
]

# ── Query SQL ──────────────────────────────────────────────────────────────────

QUERY_BASE = f"""
SELECT
    USR.USR_NOME      AS USUARIO,
    SC7.C7_FILIAL     AS FILIAL,
    SC7.C7_NUM        AS PEDIDO_COMPRA,
    SC7.C7_ITEM       AS ITEM,
    SC7.C7_PRODUTO    AS PRODUTO,
    SC7.C7_UM         AS UNIDADE,
    SC7.C7_DESCRI     AS DESCRICAO_PRODUTO,
    SC7.C7_QUANT      AS QUANTIDADE,
    SC7.C7_PRECO      AS PRECO_UNITARIO,
    SC7.C7_TOTAL      AS PRECO_TOTAL,
    SC7.C7_DATPRF     AS DATA_ENTREGA,
    SC7.C7_NUMSC      AS NUMERO_SC,
    SC7.C7_ITEMSC     AS ITEM_SC,
    SC7.C7_OBS        AS OBSERVACOES,
    SC7.C7_CLVL       AS CLASSE_VALOR,
    SC7.C7_QUJE       AS QTD_ENTREGUE,
    SC7.C7_NUMCOT     AS NUM_COTACAO,
    SC7.C7_MOEDA      AS MOEDA,
    SC7.C7_FORNECE    AS COD_FORNECEDOR,
    SA2.A2_NOME       AS FORNECEDOR,
    SC7.C7_LOCAL      AS DEPOSITO_ESTOQUE,
    SC7.C7_EMISSAO    AS DATA_EMISSAO,
    RTRIM(SC7.C7_XREVISA) AS REVISAO,
    APR.CR_NIVEL      AS NIVEL_APROVACAO,
    APRUSR.AK_NOME    AS APROVADOR,
    CONVERT(VARCHAR, APR.CR_DATALIB, 103) AS DATA_APROVACAO,
    CASE APR.CR_STATUS
        WHEN '01' THEN 'Aguardando Aprovacao'
        WHEN '02' THEN 'Aguardando Aprovacao'
        WHEN '03' THEN 'Aprovado'
        WHEN '04' THEN 'Reprovado'
        WHEN '06' THEN 'Reprovado'
        ELSE '-'
    END AS STATUS_APROVACAO,
    SC7.C7_CC         AS CENTRO_CUSTO,
    CTT.CTT_DESC01    AS CENTRO_CUSTO_DESC,
    SC7.C7_ITEMCTA    AS ITEM_CONTA,
    CTD.CTD_DESC01    AS ITEM_CONTA_DESC,
    SC7.C7_CONTA      AS CONTA_CONTABIL,
    CT1.CT1_DESC01    AS CONTA_CONTABIL_DESC,
    SC7.C7_COND       AS COND_PAGAMENTO,
    SE4.E4_DESCRI     AS COND_PAGAMENTO_DESC
FROM SC7010A SC7
INNER JOIN SYS_USR USR
    ON USR.USR_ID = SC7.C7_USER
    AND USR.D_E_L_E_T_ = ''
LEFT JOIN SA2010 SA2
    ON SA2.A2_COD = SC7.C7_FORNECE
    AND SA2.A2_LOJA = SC7.C7_LOJA
    AND SA2.D_E_L_E_T_ = ''
LEFT JOIN SCR010 APR
    ON APR.CR_NUM = SC7.C7_NUM
    AND APR.CR_FILIAL = SC7.C7_FILIAL
    AND APR.CR_TIPO = 'PC'
    AND APR.D_E_L_E_T_ = ''
LEFT JOIN SAK010 APRUSR
    ON APRUSR.AK_COD = APR.CR_APROV
    AND APRUSR.D_E_L_E_T_ = ''
OUTER APPLY (
    SELECT TOP 1 CTT_DESC01
    FROM CTT010
    WHERE CTT_CUSTO = SC7.C7_CC AND D_E_L_E_T_ = ''
) AS CTT
OUTER APPLY (
    SELECT TOP 1 CTD_DESC01
    FROM CTD010
    WHERE CTD_ITEM = SC7.C7_ITEMCTA AND D_E_L_E_T_ = ''
) AS CTD
OUTER APPLY (
    SELECT TOP 1 CT1_DESC01
    FROM CT1010
    WHERE CT1_CONTA = SC7.C7_CONTA AND D_E_L_E_T_ = ''
) AS CT1
OUTER APPLY (
    SELECT TOP 1 E4_DESCRI
    FROM SE4010
    WHERE E4_CODIGO = SC7.C7_COND AND D_E_L_E_T_ = ''
) AS SE4
WHERE SC7.D_E_L_E_T_ = ''
    AND SC7.C7_USER IN {USUARIOS}
"""

QUERY_NOVOS    = QUERY_BASE + "    AND SC7.C7_EMISSAO >= ?\nORDER BY SC7.C7_EMISSAO DESC"
QUERY_COMPLETA = QUERY_BASE + "ORDER BY SC7.C7_EMISSAO DESC"

# ── Consulta local (SQLite) ────────────────────────────────────────────────────

SELECT_DETALHADO = (
    'SELECT usuario, filial, pedido_compra, item, produto, unidade, '
    'descricao_produto, quantidade, preco_unitario, preco_total, '
    'data_entrega, numero_sc, item_sc, observacoes, classe_valor, '
    'qtd_entregue, num_cotacao, moeda, cod_fornecedor, fornecedor, '
    'deposito_estoque, data_emissao, revisao, nivel_aprovacao, aprovador, '
    'data_aprovacao, status_aprovacao, '
    'centro_custo, centro_custo_desc, '
    'item_conta, item_conta_desc, '
    'conta_contabil, conta_contabil_desc, '
    'cond_pagamento, cond_pagamento_desc '
    'FROM pedidos_detalhado'
)


def _construir_query_export(data_inicio=None, data_fim=None):
    sql    = SELECT_DETALHADO
    params = []
    conds  = []
    if data_inicio:
        conds.append('data_emissao >= ?')
        params.append(data_inicio)
    if data_fim:
        conds.append('data_emissao <= ?')
        params.append(data_fim)
    if conds:
        sql += ' WHERE ' + ' AND '.join(conds)
    sql += ' ORDER BY data_emissao DESC, pedido_compra, item, nivel_aprovacao'
    return sql, params


# ── INSERT / UPSERT ───────────────────────────────────────────────────────────

INSERT_DETALHADO = '''
    INSERT INTO pedidos_detalhado
    (usuario, filial, pedido_compra, item, produto, unidade,
     descricao_produto, quantidade, preco_unitario, preco_total,
     data_entrega, numero_sc, item_sc, observacoes, classe_valor,
     qtd_entregue, num_cotacao, moeda, cod_fornecedor, fornecedor,
     deposito_estoque, data_emissao, revisao, nivel_aprovacao, aprovador,
     data_aprovacao, status_aprovacao,
     centro_custo, centro_custo_desc,
     item_conta, item_conta_desc,
     conta_contabil, conta_contabil_desc,
     cond_pagamento, cond_pagamento_desc)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(filial, pedido_compra, item, nivel_aprovacao) DO UPDATE SET
        usuario           = excluded.usuario,
        produto           = excluded.produto,
        unidade           = excluded.unidade,
        descricao_produto = excluded.descricao_produto,
        quantidade        = excluded.quantidade,
        preco_unitario    = excluded.preco_unitario,
        preco_total       = excluded.preco_total,
        data_entrega      = excluded.data_entrega,
        numero_sc         = excluded.numero_sc,
        item_sc           = excluded.item_sc,
        observacoes       = excluded.observacoes,
        classe_valor      = excluded.classe_valor,
        qtd_entregue      = excluded.qtd_entregue,
        num_cotacao       = excluded.num_cotacao,
        moeda             = excluded.moeda,
        cod_fornecedor    = excluded.cod_fornecedor,
        fornecedor        = excluded.fornecedor,
        deposito_estoque  = excluded.deposito_estoque,
        data_emissao      = excluded.data_emissao,
        revisao           = excluded.revisao,
        aprovador         = excluded.aprovador,
        data_aprovacao    = excluded.data_aprovacao,
        status_aprovacao  = excluded.status_aprovacao,
        centro_custo      = excluded.centro_custo,
        centro_custo_desc = excluded.centro_custo_desc,
        item_conta        = excluded.item_conta,
        item_conta_desc   = excluded.item_conta_desc,
        conta_contabil    = excluded.conta_contabil,
        conta_contabil_desc = excluded.conta_contabil_desc,
        cond_pagamento    = excluded.cond_pagamento,
        cond_pagamento_desc = excluded.cond_pagamento_desc
'''

# ── Sync log ──────────────────────────────────────────────────────────────────

def registrar_sync_event(registros_novos, status, erro_resumo=None,
                         total_protheus=None, total_local=None):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO pedidos_detalhado_sync_log '
        '(executado_em, registros_novos, status, erro_resumo, total_protheus, total_local) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (agora(), registros_novos, status, erro_resumo, total_protheus, total_local),
    )
    conn.commit()
    conn.close()


def info_relatorio():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pedidos_detalhado').fetchone()[0]
    sync = conn.execute(
        'SELECT executado_em, registros_novos, '
        "COALESCE(status, CASE WHEN registros_novos > 0 THEN 'sucesso' ELSE 'sem_novos' END) AS status, "
        'erro_resumo '
        'FROM pedidos_detalhado_sync_log ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    if not sync:
        return total, None, 'nunca', None
    return total, sync['executado_em'], sync['status'], sync['erro_resumo']


def historico_sync(limit=10, offset=0):
    conn = conectar_pedidos()
    linhas = conn.execute(
        'SELECT executado_em, registros_novos FROM pedidos_detalhado_sync_log '
        'WHERE registros_novos > 0 '
        'ORDER BY id DESC LIMIT ? OFFSET ?',
        (limit, offset),
    ).fetchall()
    conn.close()
    return linhas

# ── Upsert helpers ────────────────────────────────────────────────────────────

def _norm(v):
    return str(v).strip() if v is not None else ''


KEY_IDX = (1, 2, 3, 23)  # FILIAL, PEDIDO_COMPRA, ITEM, NIVEL_APROVACAO


def _contar_mutacoes(conn, dados, data_corte):
    if not dados:
        return 0, 0
    where  = 'data_emissao >= ?' if data_corte else '1=1'
    params = (data_corte,) if data_corte else ()
    locais = conn.execute(SELECT_DETALHADO + f' WHERE {where}', params).fetchall()
    locais_by_key = {
        tuple(_norm(row[i]) for i in KEY_IDX): tuple(_norm(v) for v in row)
        for row in locais
    }
    novos = atualizados = 0
    for d in dados:
        key = (d[1], d[2], d[3], d[23])
        if key not in locais_by_key:
            novos += 1
        elif locais_by_key[key] != tuple(_norm(v) for v in d):
            atualizados += 1
    return novos, atualizados


def _detectar_e_remover_deletados(chaves_protheus, data_corte, conn):
    locais = conn.execute(
        'SELECT DISTINCT filial, pedido_compra, item FROM pedidos_detalhado WHERE data_emissao >= ?',
        (data_corte,),
    ).fetchall()
    para_deletar = [
        (r['filial'], r['pedido_compra'], r['item'])
        for r in locais
        if (r['filial'], r['pedido_compra'], r['item']) not in chaves_protheus
    ]
    if para_deletar:
        from services.sync_engine import remover_hashes_de_itens
        conn.executemany(
            'DELETE FROM pedidos_detalhado WHERE filial=? AND pedido_compra=? AND item=?',
            para_deletar,
        )
        remover_hashes_de_itens(conn, 'pedidos_detalhado', para_deletar)
    return len(para_deletar)


def _upsert_no_sqlite(linhas, data_corte=None):
    total_protheus = len(linhas)
    conn = conectar_pedidos()
    try:
        if not linhas:
            total_local = conn.execute(
                'SELECT COUNT(*) FROM pedidos_detalhado WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0] if data_corte else conn.execute(
                'SELECT COUNT(*) FROM pedidos_detalhado'
            ).fetchone()[0]
            registrar_sync_event(0, 'sem_novos', total_protheus=0, total_local=total_local)
            return 0

        dados = [tuple(_norm(val) for val in linha) for linha in linhas]
        chaves_protheus = {(d[1], d[2], d[3]) for d in dados}

        try:
            novos, atualizados = _contar_mutacoes(conn, dados, data_corte)
        except Exception as exc:
            print(f'[PEDIDOS_DET] diff falhou ({exc}); upsert cego.')
            novos, atualizados = total_protheus, 0

        if (novos + atualizados) > 0:
            conn.executemany(INSERT_DETALHADO, dados)

        removidos = 0
        if data_corte:
            removidos = _detectar_e_remover_deletados(chaves_protheus, data_corte, conn)

        conn.commit()

        if data_corte:
            total_local = conn.execute(
                'SELECT COUNT(*) FROM pedidos_detalhado WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0]
        else:
            total_local = conn.execute('SELECT COUNT(*) FROM pedidos_detalhado').fetchone()[0]
    finally:
        conn.close()

    mutacoes  = novos + atualizados + removidos
    divergencia = abs(total_protheus - total_local) / max(total_protheus, 1)
    status = 'alerta' if divergencia > 0.05 else ('sucesso' if mutacoes > 0 else 'sem_novos')
    registrar_sync_event(mutacoes, status, total_protheus=total_protheus, total_local=total_local)
    return mutacoes


def _calcular_data_corte(data_emissao_maxima):
    if not data_emissao_maxima:
        return None
    data_base  = parse_protheus_date(data_emissao_maxima)
    data_corte = data_base - timedelta(days=SYNC_LOOKBACK_DAYS)
    return format_protheus_date(data_corte)

# ── Carga e sincronização ──────────────────────────────────────────────────────

def carga_completa() -> int:
    """Full refresh baseado em hash: detecta e aplica apenas as mudanças reais."""
    from services.sync_engine import full_refresh_com_hash
    return full_refresh_com_hash(
        tabela         = 'pedidos_detalhado',
        chave_colunas  = ['filial', 'pedido_compra', 'item', 'nivel_aprovacao'],
        chave_idx      = (1, 2, 3, 23),
        conn_fn        = conectar_pedidos,
        query_completa = QUERY_COMPLETA,
        insert_sql     = INSERT_DETALHADO,
        norm_row       = lambda l: tuple(_norm(v) for v in l),
        registrar_sync_fn = registrar_sync_event,
    )


def carga_inicial():
    conn  = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pedidos_detalhado').fetchone()[0]
    conn.close()
    if total > 0:
        return 0
    linhas = executar_select(QUERY_COMPLETA)
    return _upsert_no_sqlite(linhas)


def sincronizar():
    conn      = conectar_pedidos()
    resultado = conn.execute('SELECT MAX(data_emissao) FROM pedidos_detalhado').fetchone()[0]
    conn.close()

    if resultado:
        data_corte = _calcular_data_corte(resultado)
        linhas     = executar_select(QUERY_NOVOS, (data_corte,))
    else:
        data_corte = None
        linhas     = executar_select(QUERY_COMPLETA)

    return _upsert_no_sqlite(linhas, data_corte=data_corte)

# ── Exportação ────────────────────────────────────────────────────────────────

def gerar_csv(data_inicio=None, data_fim=None):
    sql, params = _construir_query_export(data_inicio, data_fim)
    conn   = conectar_pedidos()
    linhas = conn.execute(sql, params).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(COLUNAS)
    for linha in linhas:
        writer.writerow([str(val).strip() if val else '' for val in linha])
    output.seek(0)
    return output.getvalue(), len(linhas)


def gerar_excel(data_inicio=None, data_fim=None):
    from openpyxl import Workbook

    sql, params = _construir_query_export(data_inicio, data_fim)
    conn   = conectar_pedidos()
    linhas = conn.execute(sql, params).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = 'Pedidos de Compra Detalhado'
    ws.append(COLUNAS)

    for linha in linhas:
        ws.append([str(val).strip() if val else '' for val in linha])

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 50)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue(), len(linhas)
