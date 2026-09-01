"""SA2010 — Cadastro de Fornecedores (nomes de campo originais Protheus)."""
from .base import (
    BATCH_SIZE, _s,
    carga_inicial, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
    limpar_para_refresh, sincronizar_cadastro,
)

TABELA     = 'fornecedores'
SYNC_LOG   = 'fornecedores_sync_log'
CURSOR_KEY = 'fornecedores'
CAMPO_ORDEM = 'A2_COD'
TITULO_ABA = 'Fornecedores'

COLUNAS_HEADER = [
    'A2_FILIAL', 'A2_COD', 'A2_LOJA',
    'A2_NOME', 'A2_NREDUZ',
    'A2_TIPO', 'A2_TPESSOA', 'A2_CGC', 'A2_PFISICA',
    'A2_INSCR', 'A2_INSCRM',
    'A2_END', 'A2_NR_END', 'A2_COMPLEM', 'A2_BAIRRO',
    'A2_MUN', 'A2_EST', 'A2_CEP', 'A2_PAIS', 'A2_COD_MUN',
    'A2_DDD', 'A2_TEL', 'A2_EMAIL', 'A2_CONTATO',
    'A2_NATUREZ', 'A2_COND', 'A2_CONTA',
    'A2_BANCO', 'A2_AGENCIA', 'A2_NUMCON', 'A2_PIX', 'A2_TPPIX', 'A2_FORMPAG',
    'A2_MSBLQL', 'A2_CODBLO', 'A2_DATBLO', 'A2_STATUS',
    'A2_XREST', 'A2_XTIPO',
    'A2_CNAE', 'A2_SIMPNAC',
    'A2_RECISS', 'A2_CALCIRF', 'A2_RECINSS', 'A2_RECPIS', 'A2_RECCOFI', 'A2_RECCSLL',
    'A2_PRICOM', 'A2_ULTCOM',
]

COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

_CAMPOS = """
    RTRIM(A2_FILIAL),  RTRIM(A2_COD),     RTRIM(A2_LOJA),
    RTRIM(A2_NOME),    RTRIM(A2_NREDUZ),
    RTRIM(A2_TIPO),    RTRIM(A2_TPESSOA), RTRIM(A2_CGC),    RTRIM(A2_PFISICA),
    RTRIM(A2_INSCR),   RTRIM(A2_INSCRM),
    RTRIM(A2_END),     RTRIM(A2_NR_END),  RTRIM(A2_COMPLEM), RTRIM(A2_BAIRRO),
    RTRIM(A2_MUN),     RTRIM(A2_EST),     RTRIM(A2_CEP),     RTRIM(A2_PAIS), RTRIM(A2_COD_MUN),
    RTRIM(A2_DDD),     RTRIM(A2_TEL),     RTRIM(A2_EMAIL),   RTRIM(A2_CONTATO),
    RTRIM(A2_NATUREZ), RTRIM(A2_COND),    RTRIM(A2_CONTA),
    RTRIM(A2_BANCO),   RTRIM(A2_AGENCIA), RTRIM(A2_NUMCON),  RTRIM(A2_PIX), RTRIM(A2_TPPIX), RTRIM(A2_FORMPAG),
    RTRIM(A2_MSBLQL),  RTRIM(A2_CODBLO),  RTRIM(A2_DATBLO),  RTRIM(A2_STATUS),
    RTRIM(A2_XREST),   RTRIM(A2_XTIPO),
    RTRIM(A2_CNAE),    RTRIM(A2_SIMPNAC),
    RTRIM(A2_RECISS),  RTRIM(A2_CALCIRF), RTRIM(A2_RECINSS), RTRIM(A2_RECPIS), RTRIM(A2_RECCOFI), RTRIM(A2_RECCSLL),
    RTRIM(A2_PRICOM),  RTRIM(A2_ULTCOM)"""

_FROM = "FROM SA2010 WITH (NOLOCK)\nWHERE D_E_L_E_T_ = ' '"

QUERY_PAGINADA = f"""
SELECT TOP {BATCH_SIZE}
    R_E_C_N_O_,{_CAMPOS}
{_FROM}
  AND R_E_C_N_O_ > ?
ORDER BY R_E_C_N_O_
"""

QUERY_COMPLETA = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
{_FROM}
ORDER BY R_E_C_N_O_
"""

QUERY_PREVIEW = QUERY_COMPLETA.strip()

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [(int(r[0]),) + tuple(_s(v) for v in r[1:]) for r in linhas]
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_fornecedores():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def full_refresh_fornecedores() -> int:
    limpar_para_refresh(TABELA, CURSOR_KEY)
    return carga_inicial_fornecedores()


def sincronizar_fornecedores():
    return sincronizar_cadastro(
        CURSOR_KEY, QUERY_COMPLETA, TABELA, SYNC_LOG, _upsert,
    )


def info_relatorio_fornecedores():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_fornecedores(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_fornecedores(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_ORDEM, data_inicio, data_fim)


def gerar_excel_fornecedores(data_inicio=None, data_fim=None):
    return gerar_excel(
        TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_ORDEM, TITULO_ABA,
        data_inicio, data_fim,
    )
