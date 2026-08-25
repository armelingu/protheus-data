"""
Energy — Contas a Receber.

Subset de SE1010 filtrado pelo negócio Energy (E1_ITEMC = '05.001').
Estrutura idêntica ao relatório financeiro/contas_receber, com a adição
do filtro de negócio e tabelas/cursores próprios para evitar colisão.
"""
from services.relatorios.financeiro.base import (
    DATA_INICIO, _s, _f,
    _lookback_dias,
    carga_inicial, sincronizar, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
    limpar_para_refresh,
)

# Títulos Energy em atraso podem ser recebidos meses depois — 365 dias
# garante captura de recebimentos tardios no resync horário.
LOOKBACK_DIAS = _lookback_dias('SYNC_LOOKBACK_TITULOS', default=365)

TABELA     = 'energy_contas_receber'
SYNC_LOG   = 'energy_contas_receber_sync_log'
CURSOR_KEY = 'energy_contas_receber'
CAMPO_DATA = 'E1_VENCTO'
TITULO_ABA = 'Contas a Receber Energy'

# Filtro de negócio Energy — campo E1_ITEMC (item contábil / item orçamentário)
ITEMC_ENERGY = '05.001'

COLUNAS_HEADER = [
    'E1_FILIAL', 'E1_PREFIXO', 'E1_NUM', 'E1_PARCELA', 'E1_TIPO',
    'E1_CLIENTE', 'E1_LOJA', 'E1_NOMCLI',
    'E1_EMISSAO', 'E1_VENCTO', 'E1_VENCREA',
    'E1_VALOR', 'E1_SALDO', 'E1_BAIXA',
    'E1_NATUREZ', 'E1_HIST',
    'E1_STATUS', 'E1_SITUACA', 'E1_MOEDA',
    'E1_PORTADO', 'E1_AGEDEP',
    'E1_NUMNOTA', 'E1_SERIE', 'E1_MOTIVO',
    'E1_ITEMC',
]

COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

_CAMPOS = """
    RTRIM(E1_FILIAL),  RTRIM(E1_PREFIXO), RTRIM(E1_NUM),     RTRIM(E1_PARCELA), RTRIM(E1_TIPO),
    RTRIM(E1_CLIENTE), RTRIM(E1_LOJA),    RTRIM(E1_NOMCLI),
    RTRIM(E1_EMISSAO), RTRIM(E1_VENCTO),  RTRIM(E1_VENCREA),
    E1_VALOR,          E1_SALDO,          RTRIM(E1_BAIXA),
    RTRIM(E1_NATUREZ), RTRIM(E1_HIST),
    RTRIM(E1_STATUS),  RTRIM(E1_SITUACA), RTRIM(E1_MOEDA),
    RTRIM(E1_PORTADO), RTRIM(E1_AGEDEP),
    RTRIM(E1_NUMNOTA), RTRIM(E1_SERIE),   RTRIM(E1_MOTIVO),
    RTRIM(E1_ITEMC)"""

_FILTRO_BASE = (
    "D_E_L_E_T_ = ' ' "
    f"AND RTRIM(E1_ITEMC) = '{ITEMC_ENERGY}' "
    f"AND E1_VENCTO >= '{DATA_INICIO}'"
)

QUERY_PREVIEW = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
FROM SE1010 WITH (NOLOCK)
WHERE {_FILTRO_BASE}
ORDER BY R_E_C_N_O_
"""

QUERY_PAGINADA = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
FROM SE1010 WITH (NOLOCK)
WHERE {_FILTRO_BASE}
  AND R_E_C_N_O_ > ?
ORDER BY R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
FROM SE1010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND RTRIM(E1_ITEMC) = '{ITEMC_ENERGY}'
  AND E1_VENCTO >= ?
ORDER BY R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [
        (
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),  _s(r[5]),
            _s(r[6]),  _s(r[7]),  _s(r[8]),
            _s(r[9]),  _s(r[10]), _s(r[11]),
            _f(r[12]), _f(r[13]), _s(r[14]),
            _s(r[15]), _s(r[16]),
            _s(r[17]), _s(r[18]), _s(r[19]),
            _s(r[20]), _s(r[21]),
            _s(r[22]), _s(r[23]), _s(r[24]),
            _s(r[25]),
        )
        for r in linhas
    ]
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_energy_nf_saida():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def full_refresh_energy_nf_saida() -> int:
    """Full refresh: limpa tabela + cursor e recarrega tudo do Protheus."""
    limpar_para_refresh(TABELA, CURSOR_KEY)
    return carga_inicial_energy_nf_saida()


def sincronizar_energy_nf_saida():
    return sincronizar(
        CURSOR_KEY, QUERY_PAGINADA, QUERY_SYNC_WINDOW,
        TABELA, SYNC_LOG, _upsert, CAMPO_DATA,
        lookback_dias=LOOKBACK_DIAS,
    )


def info_relatorio_energy_nf_saida():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_energy_nf_saida(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_energy_nf_saida(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_energy_nf_saida(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
