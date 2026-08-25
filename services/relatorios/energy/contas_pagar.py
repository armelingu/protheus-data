"""
Energy — Contas a Pagar.

Subset de SE2010 filtrado pelo negócio Energy (E2_ITEMD = '05.001'),
com exclusão das naturezas internas que não fazem parte do fluxo Energy.

As colunas são expostas com NOMES AMIGÁVEIS (Filial, Vencimento, ValorTitulo, ...)
para que usuários leigos consigam ler o relatório sem conhecimento de Protheus.
A query no Protheus já vem com aliases (SELECT E2_FILIAL AS Filial, ...) e a
tabela local em financeiro.db espelha esses nomes.
"""
from services.relatorios.financeiro.base import (
    DATA_INICIO, _s, _f,
    _lookback_dias,
    carga_inicial, sincronizar, info_relatorio, historico_sync,
    gerar_csv, gerar_excel, construir_upsert_sql,
    limpar_para_refresh,
)

# Janela baseada em E2_VENCTO (alias Vencimento). Títulos Energy em atraso podem
# ser baixados meses depois — 365 dias garante captura de pagamentos tardios.
# Configurável via SYNC_LOOKBACK_TITULOS (fallback: SYNC_LOOKBACK_DAYS → 365).
LOOKBACK_DIAS = _lookback_dias('SYNC_LOOKBACK_TITULOS', default=365)

TABELA     = 'energy_contas_pagar'
SYNC_LOG   = 'energy_contas_pagar_sync_log'
CURSOR_KEY = 'energy_contas_pagar'
CAMPO_DATA = 'Vencimento'
TITULO_ABA = 'Contas a Pagar Energy'

# Naturezas excluídas do escopo Energy (regra de negócio definida pela área).
# 10.0003 = títulos da UP recuperação CR (não devem aparecer no relatório).
NATUREZAS_EXCLUIDAS = ('08.0014', '08.0001', '08.0007', '08.0024', '08.0004', '08.0016', '10.0003')
ITEMD_ENERGY        = '05.001'

# Colunas (nomes amigáveis) — usadas tanto como header de CSV/Excel quanto como
# colunas reais da tabela local energy_contas_pagar.
COLUNAS_HEADER = [
    'Filial', 'Prefixo', 'NumeroTitulo', 'Parcela', 'Tipo',
    'Natureza', 'Negocio', 'Rastreamento', 'CentroCusto',
    'Fornecedor', 'Loja', 'NomeFornecedor',
    'DataEmissao', 'Vencimento', 'VencimentoReal',
    'ValorTitulo', 'ISS', 'IRRF', 'Databaixa',
    'BancoPagamento', 'DataContabil', 'Historico',
    'Saldo', 'Desconto', 'Multa', 'Juros', 'Correcao',
    'ValorLiquidoBaixado', 'VencimentoOriginal', 'Moeda', 'VlrEmReal',
    'Acrescimo', 'DataLiberacao', 'TaxaMoeda', 'Decrescimo', 'FilialOriginal',
]
COLUNAS_SELECT = ', '.join(COLUNAS_HEADER)

# SELECT no Protheus: aliases via AS para que o resultado já venha com os nomes
# amigáveis e o mapeamento posicional do _upsert continue trivial.
_CAMPOS = """
    RTRIM(E2_FILIAL)  AS Filial,
    RTRIM(E2_PREFIXO) AS Prefixo,
    RTRIM(E2_NUM)     AS NumeroTitulo,
    RTRIM(E2_PARCELA) AS Parcela,
    RTRIM(E2_TIPO)    AS Tipo,
    RTRIM(E2_NATUREZ) AS Natureza,
    RTRIM(E2_ITEMD)   AS Negocio,
    RTRIM(E2_CLVLDB)  AS Rastreamento,
    RTRIM(E2_CCD)     AS CentroCusto,
    RTRIM(E2_FORNECE) AS Fornecedor,
    RTRIM(E2_LOJA)    AS Loja,
    RTRIM(E2_NOMFOR)  AS NomeFornecedor,
    RTRIM(E2_EMISSAO) AS DataEmissao,
    RTRIM(E2_VENCTO)  AS Vencimento,
    RTRIM(E2_VENCREA) AS VencimentoReal,
    E2_VALOR          AS ValorTitulo,
    E2_ISS            AS ISS,
    E2_IRRF           AS IRRF,
    RTRIM(E2_BAIXA)   AS Databaixa,
    RTRIM(E2_BCOPAG)  AS BancoPagamento,
    RTRIM(E2_EMIS1)   AS DataContabil,
    RTRIM(E2_HIST)    AS Historico,
    E2_SALDO          AS Saldo,
    E2_DESCONT        AS Desconto,
    E2_MULTA          AS Multa,
    E2_JUROS          AS Juros,
    E2_CORREC         AS Correcao,
    E2_VALLIQ         AS ValorLiquidoBaixado,
    RTRIM(E2_VENCORI) AS VencimentoOriginal,
    RTRIM(E2_MOEDA)   AS Moeda,
    E2_VLCRUZ         AS VlrEmReal,
    E2_ACRESC         AS Acrescimo,
    RTRIM(E2_DATALIB) AS DataLiberacao,
    E2_TXMOEDA        AS TaxaMoeda,
    E2_DECRESC        AS Decrescimo,
    RTRIM(E2_FILORIG) AS FilialOriginal"""

# Filtro do negócio Energy (sempre aplicado)
_FILTRO_ENERGY = (
    "AND RTRIM(E2_ITEMD) = '" + ITEMD_ENERGY + "' "
    "AND E2_NATUREZ NOT IN (" + ", ".join("'" + n + "'" for n in NATUREZAS_EXCLUIDAS) + ")"
)

# Carga, preview e exportação usam vencimento — o mesmo campo do sync incremental.
_FILTRO_BASE = (
    "D_E_L_E_T_ = ' ' "
    f"{_FILTRO_ENERGY} "
    f"AND E2_VENCTO >= '{DATA_INICIO}'"
)

QUERY_PREVIEW = f"""
SELECT
    R_E_C_N_O_ AS recno,{_CAMPOS}
FROM SE2010 WITH (NOLOCK)
WHERE {_FILTRO_BASE}
ORDER BY R_E_C_N_O_
"""

QUERY_PAGINADA = f"""
SELECT
    R_E_C_N_O_ AS recno,{_CAMPOS}
FROM SE2010 WITH (NOLOCK)
WHERE {_FILTRO_BASE}
  AND R_E_C_N_O_ > ?
ORDER BY R_E_C_N_O_
"""

QUERY_SYNC_WINDOW = f"""
SELECT
    R_E_C_N_O_ AS recno,{_CAMPOS}
FROM SE2010 WITH (NOLOCK)
WHERE D_E_L_E_T_ = ' '
  AND E2_VENCTO >= ?
  {_FILTRO_ENERGY}
ORDER BY R_E_C_N_O_
"""

INSERT_SQL = construir_upsert_sql(TABELA, COLUNAS_HEADER)


def _upsert(conn, linhas):
    dados = [
        (
            int(r[0]),
            _s(r[1]),  _s(r[2]),  _s(r[3]),  _s(r[4]),  _s(r[5]),
            _s(r[6]),  _s(r[7]),  _s(r[8]),  _s(r[9]),
            _s(r[10]), _s(r[11]), _s(r[12]),
            _s(r[13]), _s(r[14]), _s(r[15]),
            _f(r[16]), _f(r[17]), _f(r[18]), _s(r[19]),
            _s(r[20]), _s(r[21]), _s(r[22]),
            _f(r[23]), _f(r[24]), _f(r[25]), _f(r[26]), _f(r[27]),
            _f(r[28]), _s(r[29]), _s(r[30]), _f(r[31]),
            _f(r[32]), _s(r[33]), _f(r[34]), _f(r[35]), _s(r[36]),
        )
        for r in linhas
    ]
    conn.executemany(INSERT_SQL, dados)


def carga_inicial_energy_contas_pagar():
    return carga_inicial(CURSOR_KEY, QUERY_PAGINADA, TABELA, SYNC_LOG, _upsert)


def full_refresh_energy_contas_pagar() -> int:
    """Full refresh: limpa tabela + cursor e recarrega tudo do Protheus."""
    limpar_para_refresh(TABELA, CURSOR_KEY)
    return carga_inicial_energy_contas_pagar()


def sincronizar_energy_contas_pagar():
    return sincronizar(
        CURSOR_KEY, QUERY_PAGINADA, QUERY_SYNC_WINDOW,
        TABELA, SYNC_LOG, _upsert, CAMPO_DATA,
        lookback_dias=LOOKBACK_DIAS,
    )


def info_relatorio_energy_contas_pagar():
    return info_relatorio(TABELA, SYNC_LOG)


def historico_sync_energy_contas_pagar(limit=10, offset=0):
    return historico_sync(SYNC_LOG, limit, offset)


def gerar_csv_energy_contas_pagar(data_inicio=None, data_fim=None):
    return gerar_csv(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, data_inicio, data_fim)


def gerar_excel_energy_contas_pagar(data_inicio=None, data_fim=None):
    return gerar_excel(TABELA, COLUNAS_HEADER, COLUNAS_SELECT, CAMPO_DATA, TITULO_ABA, data_inicio, data_fim)
