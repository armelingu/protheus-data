"""
Pedidos de Compra — escopo Energy.

Fork dirigido de services/relatorios/compras/pedidos.py: mesma query e
mesmo esquema do relatório do módulo Compras, mudando apenas:
- o filtro de escopo: C7_ITEMCTA = 05.001 (item contábil Energy)
- a tabela local (pedidos_energy + pedidos_energy_sync_log)
- o nome do arquivo de download (pedidos_energy.{csv|xlsx})

Não usamos a tabela `pedidos` original para evitar misturar escopos
de negócios distintos (cada relatório vai para um setor diferente e
os KPIs precisam ser independentes).
"""
import csv
import io
import os
from datetime import timedelta

from dotenv import load_dotenv

from services.database import conectar_pedidos, agora
from services.protheus_readonly import executar_select
from services.time_utils import format_protheus_date, parse_protheus_date

load_dotenv()

# Pedidos Energy podem ter aprovações lançadas semanas após emissão.
# Configurável via SYNC_LOOKBACK_PEDIDOS (fallback: SYNC_LOOKBACK_DAYS → 60).
def _lookback_pedidos():
    for chave in ('SYNC_LOOKBACK_PEDIDOS', 'SYNC_LOOKBACK_DAYS'):
        val = os.getenv(chave)
        if val:
            try:
                return max(1, int(val))
            except (TypeError, ValueError):
                pass
    return 60

SYNC_LOOKBACK_DAYS = _lookback_pedidos()

# Item contábil do setor Energy — filtro por C7_ITEMCTA (substitui filtro por usuário).
ITEM_CONTABIL_ENERGY = '05.001'

TABELA   = 'pedidos_energy'
SYNC_LOG = 'pedidos_energy_sync_log'

COLUNAS = [
    'USUARIO', 'FILIAL', 'PEDIDO_COMPRA', 'ITEM', 'PRODUTO',
    'UNIDADE', 'DESCRICAO_PRODUTO', 'QUANTIDADE', 'PRECO_UNITARIO',
    'PRECO_TOTAL', 'DATA_ENTREGA', 'NUMERO_SC', 'ITEM_SC',
    'OBSERVACOES', 'CLASSE_VALOR', 'QTD_ENTREGUE', 'NUM_COTACAO',
    'MOEDA', 'COD_FORNECEDOR', 'FORNECEDOR', 'DEPOSITO_ESTOQUE',
    'DATA_EMISSAO', 'NIVEL_APROVACAO', 'APROVADOR', 'DATA_APROVACAO',
    'STATUS_APROVACAO',
]

QUERY_PEDIDOS = f"""
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
    END AS STATUS_APROVACAO
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
    AND SC7.C7_ITEMCTA = '{ITEM_CONTABIL_ENERGY}'
"""

QUERY_NOVOS    = QUERY_PEDIDOS + "    AND SC7.C7_EMISSAO >= ?\nORDER BY SC7.C7_EMISSAO DESC"
QUERY_COMPLETA = QUERY_PEDIDOS + "ORDER BY SC7.C7_EMISSAO DESC"

SELECT_PEDIDOS = (
    f'SELECT usuario, filial, pedido_compra, item, produto, unidade, '
    f'descricao_produto, quantidade, preco_unitario, preco_total, '
    f'data_entrega, numero_sc, item_sc, observacoes, classe_valor, '
    f'qtd_entregue, num_cotacao, moeda, cod_fornecedor, fornecedor, '
    f'deposito_estoque, data_emissao, nivel_aprovacao, aprovador, '
    f'data_aprovacao, status_aprovacao FROM {TABELA}'
)


def _construir_query_export(data_inicio=None, data_fim=None):
    sql = (
        f'SELECT usuario, filial, pedido_compra, item, produto, unidade, '
        f'descricao_produto, quantidade, preco_unitario, preco_total, '
        f'data_entrega, numero_sc, item_sc, observacoes, classe_valor, '
        f'qtd_entregue, num_cotacao, moeda, cod_fornecedor, fornecedor, '
        f'deposito_estoque, data_emissao, nivel_aprovacao, aprovador, '
        f'data_aprovacao, status_aprovacao FROM {TABELA}'
    )
    params = []
    condicoes = []
    if data_inicio:
        condicoes.append('data_emissao >= ?')
        params.append(data_inicio)
    if data_fim:
        condicoes.append('data_emissao <= ?')
        params.append(data_fim)
    if condicoes:
        sql += ' WHERE ' + ' AND '.join(condicoes)
    sql += ' ORDER BY data_emissao DESC, pedido_compra, item, nivel_aprovacao'
    return sql, params


INSERT_PEDIDO = f'''
    INSERT INTO {TABELA}
    (usuario, filial, pedido_compra, item, produto, unidade,
     descricao_produto, quantidade, preco_unitario, preco_total,
     data_entrega, numero_sc, item_sc, observacoes, classe_valor,
     qtd_entregue, num_cotacao, moeda, cod_fornecedor, fornecedor,
     deposito_estoque, data_emissao, nivel_aprovacao, aprovador,
     data_aprovacao, status_aprovacao)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        aprovador         = excluded.aprovador,
        data_aprovacao    = excluded.data_aprovacao,
        status_aprovacao  = excluded.status_aprovacao
'''


def registrar_sync_event(registros_novos, status, erro_resumo=None,
                         total_protheus=None, total_local=None):
    conn = conectar_pedidos()
    conn.execute(
        f'INSERT INTO {SYNC_LOG} '
        '(executado_em, registros_novos, status, erro_resumo, total_protheus, total_local) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (agora(), registros_novos, status, erro_resumo, total_protheus, total_local)
    )
    conn.commit()
    conn.close()


def _detectar_e_remover_deletados(chaves_protheus, data_corte, conn):
    """Remove do cache local registros que sumiram do Protheus na janela."""
    locais = conn.execute(
        f'SELECT DISTINCT filial, pedido_compra, item FROM {TABELA} WHERE data_emissao >= ?',
        (data_corte,)
    ).fetchall()

    para_deletar = [
        (r['filial'], r['pedido_compra'], r['item'])
        for r in locais
        if (r['filial'], r['pedido_compra'], r['item']) not in chaves_protheus
    ]

    if para_deletar:
        conn.executemany(
            f'DELETE FROM {TABELA} WHERE filial=? AND pedido_compra=? AND item=?',
            para_deletar
        )

    return len(para_deletar)


def _norm(v):
    return str(v).strip() if v is not None else ''


def _contar_mutacoes(conn, dados, data_corte):
    if not dados:
        return 0, 0

    where = 'data_emissao >= ?' if data_corte else '1=1'
    params = (data_corte,) if data_corte else ()
    locais_rows = conn.execute(
        SELECT_PEDIDOS + f' WHERE {where}', params
    ).fetchall()

    KEY_IDX = (1, 2, 3, 22)  # FILIAL, PEDIDO_COMPRA, ITEM, NIVEL_APROVACAO
    locais_by_key = {}
    for row in locais_rows:
        key = tuple(_norm(row[i]) for i in KEY_IDX)
        locais_by_key[key] = tuple(_norm(v) for v in row)

    novos = atualizados = 0
    for d in dados:
        key = (d[1], d[2], d[3], d[22])
        if key not in locais_by_key:
            novos += 1
        elif locais_by_key[key] != tuple(_norm(v) for v in d):
            atualizados += 1
    return novos, atualizados


def _upsert_no_sqlite(linhas, data_corte=None):
    total_protheus = len(linhas)

    conn = conectar_pedidos()
    try:
        if not linhas:
            total_local_janela = conn.execute(
                f'SELECT COUNT(*) FROM {TABELA} WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0] if data_corte else conn.execute(
                f'SELECT COUNT(*) FROM {TABELA}'
            ).fetchone()[0]
            registrar_sync_event(0, 'sem_novos', total_protheus=0, total_local=total_local_janela)
            return 0

        dados = [tuple(_norm(val) for val in linha) for linha in linhas]
        chaves_protheus = {(d[1], d[2], d[3]) for d in dados}

        try:
            novos, atualizados = _contar_mutacoes(conn, dados, data_corte)
        except Exception as exc_diff:
            print(f'[PEDIDOS_ENERGY] diff falhou ({exc_diff}); aplicando upsert cego.')
            novos, atualizados = total_protheus, 0

        if (novos + atualizados) > 0:
            conn.executemany(INSERT_PEDIDO, dados)

        removidos = 0
        if data_corte:
            removidos = _detectar_e_remover_deletados(chaves_protheus, data_corte, conn)

        conn.commit()

        if data_corte:
            total_local_janela = conn.execute(
                f'SELECT COUNT(*) FROM {TABELA} WHERE data_emissao >= ?', (data_corte,)
            ).fetchone()[0]
        else:
            total_local_janela = conn.execute(f'SELECT COUNT(*) FROM {TABELA}').fetchone()[0]
    finally:
        conn.close()

    mutacoes = novos + atualizados + removidos
    divergencia = abs(total_protheus - total_local_janela) / max(total_protheus, 1)
    if divergencia > 0.05:
        status = 'alerta'
    elif mutacoes > 0:
        status = 'sucesso'
    else:
        status = 'sem_novos'

    registrar_sync_event(
        mutacoes,
        status,
        total_protheus=total_protheus,
        total_local=total_local_janela,
    )
    return mutacoes


def _calcular_data_corte(data_emissao_maxima):
    if not data_emissao_maxima:
        return None
    data_base = parse_protheus_date(data_emissao_maxima)
    data_corte = data_base - timedelta(days=SYNC_LOOKBACK_DAYS)
    return format_protheus_date(data_corte)


def carga_inicial():
    conn = conectar_pedidos()
    total = conn.execute(f'SELECT COUNT(*) FROM {TABELA}').fetchone()[0]
    conn.close()

    if total > 0:
        return 0

    linhas = executar_select(QUERY_COMPLETA)
    return _upsert_no_sqlite(linhas)


def sincronizar():
    conn = conectar_pedidos()
    resultado = conn.execute(f'SELECT MAX(data_emissao) FROM {TABELA}').fetchone()[0]
    conn.close()

    if resultado:
        data_corte = _calcular_data_corte(resultado)
        linhas = executar_select(QUERY_NOVOS, (data_corte,))
    else:
        data_corte = None
        linhas = executar_select(QUERY_COMPLETA)

    return _upsert_no_sqlite(linhas, data_corte=data_corte)


def info_relatorio():
    conn = conectar_pedidos()
    total = conn.execute(f'SELECT COUNT(*) FROM {TABELA}').fetchone()[0]
    sync = conn.execute(
        'SELECT executado_em, registros_novos, '
        "COALESCE(status, CASE WHEN registros_novos > 0 THEN 'sucesso' ELSE 'sem_novos' END) AS status, "
        'erro_resumo '
        f'FROM {SYNC_LOG} ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    if not sync:
        return total, None, 'nunca', None
    return total, sync['executado_em'], sync['status'], sync['erro_resumo']


def historico_sync(limit=10, offset=0):
    conn = conectar_pedidos()
    linhas = conn.execute(
        f'SELECT executado_em, registros_novos FROM {SYNC_LOG} '
        'WHERE registros_novos > 0 '
        'ORDER BY id DESC LIMIT ? OFFSET ?',
        (limit, offset)
    ).fetchall()
    conn.close()
    return linhas


def gerar_csv(data_inicio=None, data_fim=None):
    sql, params = _construir_query_export(data_inicio, data_fim)
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


def gerar_excel(data_inicio=None, data_fim=None):
    from openpyxl import Workbook

    sql, params = _construir_query_export(data_inicio, data_fim)
    conn = conectar_pedidos()
    linhas = conn.execute(sql, params).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = 'Pedidos Energy'
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
