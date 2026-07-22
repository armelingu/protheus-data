import io
import os
from datetime import timedelta

from dotenv import load_dotenv

from services.database import conectar_pedidos, agora
from services.protheus_readonly import executar_select
from services.time_utils import format_protheus_date, parse_protheus_date

load_dotenv()


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

COLUNAS = [
    'USUARIO', 'FILIAL', 'PEDIDO_COMPRA', 'VALOR_TOTAL',
    'DATA_EMISSAO', 'COD_FORNECEDOR', 'FORNECEDOR',
    'NIVEL_APROVACAO', 'APROVADOR', 'DATA_APROVACAO', 'STATUS_APROVACAO',
]

# Query sem filtro de comprador — retorna um registro por pedido × nível de aprovação.
# C7_TOTAL é somado para compor o valor total do pedido independente dos itens.
# _WHERE termina antes do GROUP BY para permitir injeção do filtro incremental de data.
_QUERY_SELECT = """
SELECT
    USR.USR_NOME                                AS USUARIO,
    SC7.C7_FILIAL                               AS FILIAL,
    SC7.C7_NUM                                  AS PEDIDO_COMPRA,
    SUM(SC7.C7_TOTAL)                           AS VALOR_TOTAL,
    SC7.C7_EMISSAO                              AS DATA_EMISSAO,
    SC7.C7_FORNECE                              AS COD_FORNECEDOR,
    MAX(SA2.A2_NOME)                            AS FORNECEDOR,
    APR.CR_NIVEL                                AS NIVEL_APROVACAO,
    MAX(APRUSR.AK_NOME)                         AS APROVADOR,
    CONVERT(VARCHAR, MAX(APR.CR_DATALIB), 103)  AS DATA_APROVACAO,
    CASE MAX(APR.CR_STATUS)
        WHEN '01' THEN 'Aguardando Aprovacao'
        WHEN '02' THEN 'Aguardando Aprovacao'
        WHEN '03' THEN 'Aprovado'
        WHEN '04' THEN 'Reprovado'
        WHEN '06' THEN 'Reprovado'
        ELSE '-'
    END                                         AS STATUS_APROVACAO
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
WHERE SC7.D_E_L_E_T_ = ''
"""

_QUERY_GROUP = """GROUP BY
    USR.USR_NOME, SC7.C7_FILIAL, SC7.C7_NUM,
    SC7.C7_EMISSAO, SC7.C7_FORNECE, APR.CR_NIVEL
"""

# QUERY_BASE é exposta para o preview de query no app.py
QUERY_BASE     = _QUERY_SELECT + _QUERY_GROUP + "ORDER BY SC7.C7_EMISSAO DESC"
QUERY_NOVOS    = _QUERY_SELECT + "    AND SC7.C7_EMISSAO >= ?\n" + _QUERY_GROUP + "ORDER BY SC7.C7_EMISSAO DESC"
QUERY_COMPLETA = QUERY_BASE

SELECT_LOCAL = (
    'SELECT usuario, filial, pedido_compra, valor_total, data_emissao, '
    'cod_fornecedor, fornecedor, nivel_aprovacao, aprovador, '
    'data_aprovacao, status_aprovacao FROM pendencia_aprovacao'
)

INSERT_PENDENCIA = '''
    INSERT INTO pendencia_aprovacao
    (usuario, filial, pedido_compra, valor_total, data_emissao,
     cod_fornecedor, fornecedor, nivel_aprovacao, aprovador,
     data_aprovacao, status_aprovacao)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(filial, pedido_compra, nivel_aprovacao) DO UPDATE SET
        usuario          = excluded.usuario,
        valor_total      = excluded.valor_total,
        data_emissao     = excluded.data_emissao,
        cod_fornecedor   = excluded.cod_fornecedor,
        fornecedor       = excluded.fornecedor,
        aprovador        = excluded.aprovador,
        data_aprovacao   = excluded.data_aprovacao,
        status_aprovacao = excluded.status_aprovacao
'''


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _norm(v):
    return str(v).strip() if v is not None else ''


def _registrar_sync(registros_novos, status, erro_resumo=None,
                    total_protheus=None, total_local=None):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO pendencia_aprovacao_sync_log '
        '(executado_em, registros_novos, status, erro_resumo, total_protheus, total_local) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (agora(), registros_novos, status, erro_resumo, total_protheus, total_local)
    )
    conn.commit()
    conn.close()


def _detectar_deletados(chaves_protheus, data_corte, conn):
    locais = conn.execute(
        'SELECT filial, pedido_compra FROM pendencia_aprovacao WHERE data_emissao >= ?',
        (data_corte,)
    ).fetchall()
    para_deletar = [
        (r['filial'], r['pedido_compra'])
        for r in locais
        if (r['filial'], r['pedido_compra']) not in chaves_protheus
    ]
    if para_deletar:
        conn.executemany(
            'DELETE FROM pendencia_aprovacao WHERE filial=? AND pedido_compra=?',
            para_deletar
        )
    return len(para_deletar)


def _contar_mutacoes(conn, dados, data_corte):
    if not dados:
        return 0, 0
    where = 'data_emissao >= ?' if data_corte else '1=1'
    params = (data_corte,) if data_corte else ()
    locais_rows = conn.execute(SELECT_LOCAL + f' WHERE {where}', params).fetchall()

    # Chave: filial(1), pedido_compra(2), nivel_aprovacao(7)
    KEY_IDX = (1, 2, 7)
    locais_by_key = {
        tuple(_norm(row[i]) for i in KEY_IDX): tuple(_norm(v) for v in row)
        for row in locais_rows
    }
    novos = atualizados = 0
    for d in dados:
        key = (_norm(d[1]), _norm(d[2]), _norm(d[7]))
        if key not in locais_by_key:
            novos += 1
        elif locais_by_key[key] != tuple(_norm(v) for v in d):
            atualizados += 1
    return novos, atualizados


def _upsert(linhas, data_corte=None):
    total_protheus = len(linhas)
    conn = conectar_pedidos()
    try:
        if not linhas:
            total_local = conn.execute(
                'SELECT COUNT(*) FROM pendencia_aprovacao WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0] if data_corte else conn.execute(
                'SELECT COUNT(*) FROM pendencia_aprovacao'
            ).fetchone()[0]
            _registrar_sync(0, 'sem_novos', total_protheus=0, total_local=total_local)
            return 0

        dados = [tuple(_norm(v) for v in linha) for linha in linhas]
        chaves_protheus = {(_norm(d[1]), _norm(d[2])) for d in dados}

        try:
            novos, atualizados = _contar_mutacoes(conn, dados, data_corte)
        except Exception as exc:
            print(f'[PENDENCIA_APROV] diff falhou ({exc}); aplicando upsert cego.')
            novos, atualizados = total_protheus, 0

        if (novos + atualizados) > 0:
            conn.executemany(INSERT_PENDENCIA, dados)

        removidos = 0
        if data_corte:
            removidos = _detectar_deletados(chaves_protheus, data_corte, conn)

        conn.commit()

        total_local = conn.execute(
            'SELECT COUNT(*) FROM pendencia_aprovacao WHERE data_emissao >= ?', (data_corte,)
        ).fetchone()[0] if data_corte else conn.execute(
            'SELECT COUNT(*) FROM pendencia_aprovacao'
        ).fetchone()[0]
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

    _registrar_sync(mutacoes, status,
                    total_protheus=total_protheus, total_local=total_local)
    return mutacoes


def _calcular_data_corte(data_maxima):
    if not data_maxima:
        return None
    data_base = parse_protheus_date(data_maxima)
    return format_protheus_date(data_base - timedelta(days=SYNC_LOOKBACK_DAYS))


# ─── Funções públicas ─────────────────────────────────────────────────────────

def carga_completa() -> int:
    """Full refresh baseado em hash: detecta e aplica apenas as mudanças reais."""
    from services.sync_engine import full_refresh_com_hash
    return full_refresh_com_hash(
        tabela         = 'pendencia_aprovacao',
        chave_colunas  = ['filial', 'pedido_compra', 'nivel_aprovacao'],
        chave_idx      = (1, 2, 7),
        conn_fn        = conectar_pedidos,
        query_completa = QUERY_COMPLETA,
        insert_sql     = INSERT_PENDENCIA,
        norm_row       = lambda l: tuple(_norm(v) for v in l),
        registrar_sync_fn = _registrar_sync,
    )


def carga_inicial():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pendencia_aprovacao').fetchone()[0]
    conn.close()
    if total > 0:
        return 0
    linhas = executar_select(QUERY_COMPLETA)
    return _upsert(linhas)


def sincronizar():
    conn = conectar_pedidos()
    resultado = conn.execute('SELECT MAX(data_emissao) FROM pendencia_aprovacao').fetchone()[0]
    conn.close()
    if resultado:
        data_corte = _calcular_data_corte(resultado)
        linhas = executar_select(QUERY_NOVOS, (data_corte,))
    else:
        data_corte = None
        linhas = executar_select(QUERY_COMPLETA)
    return _upsert(linhas, data_corte=data_corte)


def info_relatorio():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pendencia_aprovacao').fetchone()[0]
    sync = conn.execute(
        'SELECT executado_em, registros_novos, '
        "COALESCE(status, CASE WHEN registros_novos > 0 THEN 'sucesso' ELSE 'sem_novos' END) AS status, "
        'erro_resumo '
        'FROM pendencia_aprovacao_sync_log ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    if not sync:
        return total, None, 'nunca', None
    return total, sync['executado_em'], sync['status'], sync['erro_resumo']


def historico_sync(limit=10, offset=0):
    conn = conectar_pedidos()
    linhas = conn.execute(
        'SELECT executado_em, registros_novos FROM pendencia_aprovacao_sync_log '
        'WHERE registros_novos > 0 ORDER BY id DESC LIMIT ? OFFSET ?',
        (limit, offset)
    ).fetchall()
    conn.close()
    return linhas


def listar_aprovadores():
    """Retorna lista distinta de aprovadores presentes no cache local."""
    conn = conectar_pedidos()
    rows = conn.execute(
        "SELECT DISTINCT aprovador FROM pendencia_aprovacao "
        "WHERE aprovador IS NOT NULL AND aprovador <> '' "
        "ORDER BY aprovador"
    ).fetchall()
    conn.close()
    return [r['aprovador'] for r in rows]


def _construir_query_export(data_inicio=None, data_fim=None, aprovador=None):
    sql = (
        'SELECT usuario, filial, pedido_compra, valor_total, data_emissao, '
        'cod_fornecedor, fornecedor, nivel_aprovacao, aprovador, '
        'data_aprovacao, status_aprovacao FROM pendencia_aprovacao'
    )
    params = []
    condicoes = []
    if data_inicio:
        condicoes.append('data_emissao >= ?')
        params.append(data_inicio)
    if data_fim:
        condicoes.append('data_emissao <= ?')
        params.append(data_fim)
    if aprovador:
        condicoes.append('aprovador = ?')
        params.append(aprovador)
    if condicoes:
        sql += ' WHERE ' + ' AND '.join(condicoes)
    sql += ' ORDER BY data_emissao DESC, pedido_compra, nivel_aprovacao'
    return sql, params


def gerar_excel(data_inicio=None, data_fim=None, aprovador=None):
    from openpyxl import Workbook

    sql, params = _construir_query_export(data_inicio, data_fim, aprovador)
    conn = conectar_pedidos()
    linhas = conn.execute(sql, params).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = 'Pendências de Aprovação'
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


def gerar_csv(data_inicio=None, data_fim=None, aprovador=None):
    import csv

    sql, params = _construir_query_export(data_inicio, data_fim, aprovador)
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
