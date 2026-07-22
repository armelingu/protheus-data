"""SD2010 — Itens de Notas Fiscais de Saída (nomes de campo originais Protheus)."""
import os
from .base import (
    DATA_INICIO, BATCH_SIZE, _s, _f,
    _lookback_dias,
    carga_inicial, sincronizar, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
    limpar_para_refresh,
)

# NFs são imutáveis após emissão; 30 dias captura entradas tardias.
# Configurável via SYNC_LOOKBACK_NF (fallback: SYNC_LOOKBACK_DAYS → 30).
LOOKBACK_DIAS = _lookback_dias('SYNC_LOOKBACK_NF', default=30)

TABELA     = 'nf_saida_itens'
SYNC_LOG   = 'nf_saida_sync_log'
CURSOR_KEY = 'nf_saida'
CAMPO_DATA = 'D2_EMISSAO'
TITULO_ABA = 'NF Saída'

COLUNAS_HEADER = [
    'D2_FILIAL', 'D2_DOC', 'D2_SERIE', 'D2_ITEM',
    'D2_CLIENTE', 'D2_LOJA', 'NomeCliente',
    'D2_EMISSAO', 'D2_DTDIGIT',
    'D2_COD', 'D2_DESC', 'D2_UM',
    'D2_QUANT', 'D2_PRUNIT', 'D2_PRCVEN',
    'D2_VALIPI', 'D2_IPI', 'D2_VALICM', 'D2_PICM',
    'D2_TP', 'D2_TES', 'D2_CF',
    'D2_GRUPO', 'D2_LOCAL',
    'D2_PEDIDO', 'D2_ITEMPV',
    'D2_DESCON', 'D2_TIPO',
]

COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

_CAMPOS = """
    RTRIM(SD2010.D2_FILIAL), RTRIM(D2_DOC),    RTRIM(D2_SERIE),  RTRIM(D2_ITEM),
    RTRIM(D2_CLIENTE),       RTRIM(D2_LOJA),   ISNULL(sa1.A1_NOME, ISNULL(sa2.A2_NOME, '')),
    RTRIM(D2_EMISSAO),       RTRIM(D2_DTDIGIT),
    RTRIM(D2_COD),           RTRIM(D2_DESC),   RTRIM(D2_UM),
    D2_QUANT,                D2_PRUNIT,         D2_PRCVEN,
    D2_VALIPI,               D2_IPI,
    D2_VALICM,               D2_PICM,
    RTRIM(D2_TP),            RTRIM(D2_TES),    RTRIM(D2_CF),
    RTRIM(D2_GRUPO),         RTRIM(D2_LOCAL),
    RTRIM(D2_PEDIDO),        RTRIM(D2_ITEMPV),
    D2_DESCON,               RTRIM(D2_TIPO)"""

# Busca NomeCliente em SA1010 (cadastro de clientes); se não existir (empresa
# registrada apenas como fornecedor), cai para SA2010 como fallback.
_JOIN_SA1 = """
OUTER APPLY (
    SELECT TOP 1 RTRIM(A1_NOME) AS A1_NOME
    FROM SA1010 WITH (NOLOCK)
    WHERE A1_COD = D2_CLIENTE AND SA1010.D_E_L_E_T_ = ' '
    ORDER BY A1_LOJA
) sa1
OUTER APPLY (
    SELECT TOP 1 RTRIM(A2_NOME) AS A2_NOME
    FROM SA2010 WITH (NOLOCK)
    WHERE A2_COD = D2_CLIENTE AND SA2010.D_E_L_E_T_ = ' '
    ORDER BY A2_LOJA
) sa2"""

QUERY_PAGINADA = f"""
SELECT TOP {BATCH_SIZE}
    SD2010.R_E_C_N_O_,{_CAMPOS}
FROM SD2010 WITH (NOLOCK)
{_JOIN_SA1}
WHERE SD2010.D_E_L_E_T_ = ' '
  AND D2_EMISSAO >= '{DATA_INICIO}'
  AND SD2010.R_E_C_N_O_ > ?
ORDER BY SD2010.R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    SD2010.R_E_C_N_O_,{_CAMPOS}
FROM SD2010 WITH (NOLOCK)
{_JOIN_SA1}
WHERE SD2010.D_E_L_E_T_ = ' '
  AND D2_EMISSAO >= ?
ORDER BY SD2010.R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [
        (
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),
            _s(r[5]),  _s(r[6]),  _s(r[7]),          # CLIENTE, LOJA, NomeCliente
            _s(r[8]),  _s(r[9]),                      # EMISSAO, DTDIGIT
            _s(r[10]), _s(r[11]), _s(r[12]),          # COD, DESC, UM
            _f(r[13]), _f(r[14]), _f(r[15]),          # QUANT, PRUNIT, PRCVEN
            _f(r[16]), _f(r[17]),                     # VALIPI, IPI
            _f(r[18]), _f(r[19]),                     # VALICM, PICM
            _s(r[20]), _s(r[21]), _s(r[22]),          # TP, TES, CF
            _s(r[23]), _s(r[24]),                     # GRUPO, LOCAL
            _s(r[25]), _s(r[26]),                     # PEDIDO, ITEMPV
            _f(r[27]), _s(r[28]),                     # DESCON, TIPO
        )
        for r in linhas
    ]
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_nf_saida():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def full_refresh_nf_saida() -> int:
    """Full refresh: limpa tabela + cursor e recarrega tudo do Protheus."""
    limpar_para_refresh(TABELA, CURSOR_KEY)
    return carga_inicial_nf_saida()


def sincronizar_nf_saida():
    return sincronizar(
        CURSOR_KEY, QUERY_PAGINADA, QUERY_SYNC_WINDOW,
        TABELA, SYNC_LOG, _upsert, CAMPO_DATA,
        lookback_dias=LOOKBACK_DIAS,
    )


def info_relatorio_nf_saida():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_nf_saida(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_nf_saida(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_nf_saida(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
