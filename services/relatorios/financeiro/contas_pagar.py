"""SE2010 — Contas a Pagar (nomes de campo originais Protheus)."""
import os
from .base import (
    DATA_INICIO, BATCH_SIZE, _s, _f,
    _lookback_dias,
    carga_inicial, sincronizar, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
)

# Janela baseada em E2_VENCTO. Títulos em atraso têm vencimentos antigos mas
# podem ser baixados meses depois — 365 dias garante que pagamentos tardios
# (até ~1 ano de atraso) sejam capturados no resync horário.
# Configurável via SYNC_LOOKBACK_TITULOS (fallback: SYNC_LOOKBACK_DAYS → 365).
LOOKBACK_DIAS = _lookback_dias('SYNC_LOOKBACK_TITULOS', default=365)

TABELA     = 'contas_pagar'
SYNC_LOG   = 'contas_pagar_sync_log'
CURSOR_KEY = 'contas_pagar'
CAMPO_DATA = 'E2_VENCTO'
TITULO_ABA = 'Contas a Pagar'

COLUNAS_HEADER = [
    'E2_FILIAL', 'E2_PREFIXO', 'E2_NUM', 'E2_PARCELA', 'E2_TIPO',
    'E2_FORNECE', 'E2_LOJA', 'E2_NOMFOR',
    'E2_EMISSAO', 'E2_VENCTO', 'E2_VENCREA', 'E2_VENCORI',
    'E2_VALOR', 'E2_SALDO', 'E2_BAIXA',
    'E2_ISS', 'E2_IRRF', 'E2_DESCONT', 'E2_MULTA', 'E2_JUROS',
    'E2_CORREC', 'E2_ACRESC', 'E2_DECRESC', 'E2_VALLIQ', 'E2_VLCRUZ',
    'E2_TXMOEDA', 'E2_DATALIB',
    'E2_NATUREZ', 'E2_HIST',
    'E2_STATUS', 'E2_MOEDA',
    'E2_BCOPAG', 'E2_MOTIVO', 'E2_RATEIO',
]

COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

_CAMPOS = """
    RTRIM(E2_FILIAL),  RTRIM(E2_PREFIXO), RTRIM(E2_NUM),    RTRIM(E2_PARCELA), RTRIM(E2_TIPO),
    RTRIM(E2_FORNECE), RTRIM(E2_LOJA),    RTRIM(E2_NOMFOR),
    RTRIM(E2_EMISSAO), RTRIM(E2_VENCTO),  RTRIM(E2_VENCREA), RTRIM(E2_VENCORI),
    E2_VALOR,          E2_SALDO,          RTRIM(E2_BAIXA),
    E2_ISS,            E2_IRRF,           E2_DESCONT,        E2_MULTA,     E2_JUROS,
    E2_CORREC,         E2_ACRESC,         E2_DECRESC,        E2_VALLIQ,    E2_VLCRUZ,
    E2_TXMOEDA,        RTRIM(E2_DATALIB),
    RTRIM(E2_NATUREZ), RTRIM(E2_HIST),
    RTRIM(E2_STATUS),  RTRIM(E2_MOEDA),
    RTRIM(E2_BCOPAG),  RTRIM(E2_MOTIVO),  RTRIM(E2_RATEIO)"""

QUERY_PAGINADA = f"""
SELECT TOP {BATCH_SIZE}
    R_E_C_N_O_,{_CAMPOS}
FROM SE2010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND E2_VENCTO >= '{DATA_INICIO}'
  AND R_E_C_N_O_ > ?
ORDER BY R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
FROM SE2010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND E2_VENCTO >= ?
ORDER BY R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [
        (
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),  _s(r[5]),
            _s(r[6]),  _s(r[7]),  _s(r[8]),
            _s(r[9]),  _s(r[10]), _s(r[11]), _s(r[12]),          # +VENCORI
            _f(r[13]), _f(r[14]), _s(r[15]),                     # VALOR, SALDO, BAIXA
            _f(r[16]), _f(r[17]), _f(r[18]), _f(r[19]), _f(r[20]),  # ISS, IRRF, DESCONT, MULTA, JUROS
            _f(r[21]), _f(r[22]), _f(r[23]), _f(r[24]), _f(r[25]),  # CORREC, ACRESC, DECRESC, VALLIQ, VLCRUZ
            _f(r[26]), _s(r[27]),                                 # TXMOEDA, DATALIB
            _s(r[28]), _s(r[29]),                                 # NATUREZ, HIST
            _s(r[30]), _s(r[31]),                                 # STATUS, MOEDA
            _s(r[32]), _s(r[33]), _s(r[34]),                     # BCOPAG, MOTIVO, RATEIO
        )
        for r in linhas
    ]
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_contas_pagar():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def sincronizar_contas_pagar():
    return sincronizar(
        CURSOR_KEY, QUERY_PAGINADA, QUERY_SYNC_WINDOW,
        TABELA, SYNC_LOG, _upsert, CAMPO_DATA,
        lookback_dias=LOOKBACK_DIAS,
    )


def info_relatorio_contas_pagar():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_contas_pagar(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_contas_pagar(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_contas_pagar(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
