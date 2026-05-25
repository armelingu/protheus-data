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
    'D1_FORNECE', 'D1_LOJA', 'NomeFornecedor',
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
    RTRIM(SD1010.D1_FILIAL), RTRIM(D1_DOC),  RTRIM(D1_SERIE), RTRIM(D1_ITEM),
    RTRIM(D1_FORNECE),       RTRIM(D1_LOJA), ISNULL(sa2.NomeFornecedor,''),
    RTRIM(D1_EMISSAO),       RTRIM(D1_DTDIGIT),
    RTRIM(D1_COD),           RTRIM(D1_DESC),  RTRIM(D1_UM),
    D1_QUANT,                D1_VUNIT,         D1_TOTAL,
    D1_VALIPI,               D1_IPI,
    D1_VALICM,               D1_PICM,
    RTRIM(D1_TP),            RTRIM(D1_TES),   RTRIM(D1_CF),
    RTRIM(D1_GRUPO),         RTRIM(D1_LOCAL),
    RTRIM(D1_PEDIDO),        RTRIM(D1_ITEMPC),
    D1_VALDESC,              D1_PESO"""

# OUTER APPLY busca o nome pelo código do fornecedor (A2_COD) sem exigir loja idêntica.
_JOIN_SA2 = """
OUTER APPLY (
    SELECT TOP 1 RTRIM(A2_NOME) AS NomeFornecedor
    FROM SA2010 WITH (NOLOCK)
    WHERE A2_COD = D1_FORNECE AND SA2010.D_E_L_E_T_ = ' '
    ORDER BY A2_LOJA
) sa2"""

QUERY_PAGINADA = f"""
SELECT TOP {BATCH_SIZE}
    SD1010.R_E_C_N_O_,{_CAMPOS}
FROM SD1010 WITH (NOLOCK)
{_JOIN_SA2}
WHERE SD1010.D_E_L_E_T_ = ' '
  AND D1_EMISSAO >= '{DATA_INICIO}'
  AND SD1010.R_E_C_N_O_ > ?
ORDER BY SD1010.R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    SD1010.R_E_C_N_O_,{_CAMPOS}
FROM SD1010 WITH (NOLOCK)
{_JOIN_SA2}
WHERE SD1010.D_E_L_E_T_ = ' '
  AND D1_EMISSAO >= ?
ORDER BY SD1010.R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [
        (
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),
            _s(r[5]),  _s(r[6]),  _s(r[7]),          # FORNECE, LOJA, NomeFornecedor
            _s(r[8]),  _s(r[9]),                      # EMISSAO, DTDIGIT
            _s(r[10]), _s(r[11]), _s(r[12]),          # COD, DESC, UM
            _f(r[13]), _f(r[14]), _f(r[15]),          # QUANT, VUNIT, TOTAL
            _f(r[16]), _f(r[17]),                     # VALIPI, IPI
            _f(r[18]), _f(r[19]),                     # VALICM, PICM
            _s(r[20]), _s(r[21]), _s(r[22]),          # TP, TES, CF
            _s(r[23]), _s(r[24]),                     # GRUPO, LOCAL
            _s(r[25]), _s(r[26]),                     # PEDIDO, ITEMPC
            _f(r[27]), _f(r[28]),                     # VALDESC, PESO
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


def historico_sync_nf_entrada(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_nf_entrada(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_nf_entrada(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
