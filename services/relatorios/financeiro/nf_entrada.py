"""SD1010 — Itens de Notas Fiscais de Entrada (nomes de campo originais Protheus)."""
import os
from .base import (
    DATA_INICIO, BATCH_SIZE, _s, _f,
    _lookback_dias,
    carga_inicial, sincronizar, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
)

# NFs são imutáveis após emissão; 30 dias captura entradas tardias.
# Configurável via SYNC_LOOKBACK_NF (fallback: SYNC_LOOKBACK_DAYS → 30).
LOOKBACK_DIAS = _lookback_dias('SYNC_LOOKBACK_NF', default=30)

TABELA     = 'nf_entrada_itens'
SYNC_LOG   = 'nf_entrada_sync_log'
CURSOR_KEY = 'nf_entrada'
CAMPO_DATA = 'D1_EMISSAO'
TITULO_ABA = 'NF Entrada'

COLUNAS_HEADER = [
    'D1_FILIAL', 'D1_DOC', 'D1_SERIE', 'D1_ITEM',
    'D1_FORNECE', 'D1_LOJA',
    'D1_EMISSAO', 'D1_DTDIGIT',
    'D1_COD', 'D1_DESC', 'D1_UM',
    'D1_QUANT', 'D1_VUNIT', 'D1_TOTAL',
    'D1_VALIPI', 'D1_IPI', 'D1_VALICM', 'D1_PICM',
    'D1_TP', 'D1_TES', 'D1_CF',
    'D1_GRUPO', 'D1_LOCAL',
    'D1_PEDIDO', 'D1_ITEMPC',
    'D1_VALDESC', 'D1_PESO',
]

COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

# ─── Queries Protheus ─────────────────────────────────────────────────────────

_CAMPOS = """
    RTRIM(D1_FILIAL), RTRIM(D1_DOC),  RTRIM(D1_SERIE), RTRIM(D1_ITEM),
    RTRIM(D1_FORNECE),RTRIM(D1_LOJA),
    RTRIM(D1_EMISSAO),RTRIM(D1_DTDIGIT),
    RTRIM(D1_COD),    RTRIM(D1_DESC),  RTRIM(D1_UM),
    D1_QUANT,         D1_VUNIT,         D1_TOTAL,
    D1_VALIPI,        D1_IPI,
    D1_VALICM,        D1_PICM,
    RTRIM(D1_TP),     RTRIM(D1_TES),   RTRIM(D1_CF),
    RTRIM(D1_GRUPO),  RTRIM(D1_LOCAL),
    RTRIM(D1_PEDIDO), RTRIM(D1_ITEMPC),
    D1_VALDESC,       D1_PESO"""

QUERY_PAGINADA = f"""
SELECT TOP {BATCH_SIZE}
    R_E_C_N_O_,{_CAMPOS}
FROM SD1010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND D1_EMISSAO >= '{DATA_INICIO}'
  AND R_E_C_N_O_ > ?
ORDER BY R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
FROM SD1010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND D1_EMISSAO >= ?
ORDER BY R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [
        (
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),
            _s(r[5]),  _s(r[6]),
            _s(r[7]),  _s(r[8]),
            _s(r[9]),  _s(r[10]), _s(r[11]),
            _f(r[12]), _f(r[13]), _f(r[14]),
            _f(r[15]), _f(r[16]),
            _f(r[17]), _f(r[18]),
            _s(r[19]), _s(r[20]), _s(r[21]),
            _s(r[22]), _s(r[23]),
            _s(r[24]), _s(r[25]),
            _f(r[26]), _f(r[27]),
        )
        for r in linhas
    ]
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_nf_entrada():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def sincronizar_nf_entrada():
    return sincronizar(
        CURSOR_KEY, QUERY_PAGINADA, QUERY_SYNC_WINDOW,
        TABELA, SYNC_LOG, _upsert, CAMPO_DATA,
        lookback_dias=LOOKBACK_DIAS,
    )


def info_relatorio_nf_entrada():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_nf_entrada(limit=10):
    return historico_sync(SYNC_LOG, limit)


def gerar_csv_nf_entrada(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_nf_entrada(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
