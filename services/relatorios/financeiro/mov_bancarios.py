"""SE5010 — Movimentos Bancários (nomes de campo originais Protheus)."""
import os
from .base import (
    DATA_INICIO, BATCH_SIZE, _s, _f,
    _lookback_dias,
    carga_inicial, sincronizar, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
)

# Movimentos bancários raramente são alterados retroativamente; 30 dias suficiente.
# Configurável via SYNC_LOOKBACK_MOV_BANCARIOS (fallback: SYNC_LOOKBACK_DAYS → 30).
LOOKBACK_DIAS = _lookback_dias('SYNC_LOOKBACK_MOV_BANCARIOS', default=30)

TABELA     = 'mov_bancarios'
SYNC_LOG   = 'mov_bancarios_sync_log'
CURSOR_KEY = 'mov_bancarios'
CAMPO_DATA = 'E5_DATA'
TITULO_ABA = 'Movimentos Bancários'

COLUNAS_HEADER = [
    'E5_FILIAL', 'E5_BANCO', 'E5_AGENCIA', 'E5_CONTA',
    'E5_DATA', 'E5_VALOR', 'E5_RECPAG',
    'E5_NATUREZ', 'E5_HISTOR', 'E5_DOCUMEN',
    'E5_TIPO', 'E5_TIPOLAN', 'E5_NUMCHEQ',
    'E5_VENCTO', 'E5_BENEF',
    'E5_PREFIXO', 'E5_NUMERO', 'E5_PARCELA',
    'E5_CLIFOR', 'E5_LOJA',
    'E5_MOTBX', 'E5_TIPODOC', 'E5_DTDIGIT',
]

COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

_CAMPOS = """
    RTRIM(E5_FILIAL),  RTRIM(E5_BANCO),   RTRIM(E5_AGENCIA), RTRIM(E5_CONTA),
    RTRIM(E5_DATA),    E5_VALOR,           RTRIM(E5_RECPAG),
    RTRIM(E5_NATUREZ), RTRIM(E5_HISTOR),   RTRIM(E5_DOCUMEN),
    RTRIM(E5_TIPO),    RTRIM(E5_TIPOLAN),  RTRIM(E5_NUMCHEQ),
    RTRIM(E5_VENCTO),  RTRIM(E5_BENEF),
    RTRIM(E5_PREFIXO), RTRIM(E5_NUMERO),   RTRIM(E5_PARCELA),
    RTRIM(E5_CLIFOR),  RTRIM(E5_LOJA),
    RTRIM(E5_MOTBX),   RTRIM(E5_TIPODOC),  RTRIM(E5_DTDIGIT)"""

QUERY_PAGINADA = f"""
SELECT TOP {BATCH_SIZE}
    R_E_C_N_O_,{_CAMPOS}
FROM SE5010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND E5_DATA >= '{DATA_INICIO}'
  AND R_E_C_N_O_ > ?
ORDER BY R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    R_E_C_N_O_,{_CAMPOS}
FROM SE5010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND E5_DATA >= ?
ORDER BY R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = []
    for r in linhas:
        # E5_VALOR é sempre positivo no Protheus; E5_RECPAG='P' indica pagamento
        # (saída de caixa) — deve ser armazenado com sinal negativo para uso analítico.
        recpag = _s(r[7])
        valor  = _f(r[6])
        if recpag == 'P':
            valor = -abs(valor)
        dados.append((
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),
            _s(r[5]),  valor,     recpag,
            _s(r[8]),  _s(r[9]),  _s(r[10]),
            _s(r[11]), _s(r[12]), _s(r[13]),
            _s(r[14]), _s(r[15]),
            _s(r[16]), _s(r[17]), _s(r[18]),
            _s(r[19]), _s(r[20]),
            _s(r[21]), _s(r[22]), _s(r[23]),
        ))
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_mov_bancarios():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def sincronizar_mov_bancarios():
    return sincronizar(
        CURSOR_KEY, QUERY_PAGINADA, QUERY_SYNC_WINDOW,
        TABELA, SYNC_LOG, _upsert, CAMPO_DATA,
        lookback_dias=LOOKBACK_DIAS,
    )


def info_relatorio_mov_bancarios():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_mov_bancarios(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_mov_bancarios(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_mov_bancarios(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
