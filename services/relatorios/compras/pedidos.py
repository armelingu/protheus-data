import csv
import io
import os
from datetime import timedelta

from dotenv import load_dotenv

from database import conectar_pedidos, agora
from services.protheus_readonly import executar_select
from time_utils import format_protheus_date, parse_protheus_date

load_dotenv()

DB_SERVER = os.getenv('DB_SERVER')
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USERNAME = os.getenv('DB_USERNAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')
SYNC_LOOKBACK_DAYS = int(os.getenv('SYNC_LOOKBACK_DAYS', '30'))

USUARIOS = "('000331', '000189', '000433', '000341', '000430', '000442', '000373', '000286')"

COLUNAS = [
    'USUARIO', 'FILIAL', 'PEDIDO_COMPRA', 'ITEM', 'PRODUTO',
    'DESCRICAO_PRODUTO', 'QUANTIDADE', 'COD_FORNECEDOR', 'FORNECEDOR',
    'DEPOSITO_ESTOQUE', 'DATA_EMISSAO'
]

QUERY_PEDIDOS = f"""
SELECT
    USR.USR_NOME      AS USUARIO,
    SC7.C7_FILIAL     AS FILIAL,
    SC7.C7_NUM        AS PEDIDO_COMPRA,
    SC7.C7_ITEM       AS ITEM,
    SC7.C7_PRODUTO    AS PRODUTO,
    SC7.C7_DESCRI     AS DESCRICAO_PRODUTO,
    SC7.C7_QUANT      AS QUANTIDADE,
    SC7.C7_FORNECE    AS COD_FORNECEDOR,
    SA2.A2_NOME       AS FORNECEDOR,
    SC7.C7_LOCAL      AS DEPOSITO_ESTOQUE,
    SC7.C7_EMISSAO    AS DATA_EMISSAO
FROM SC7010A SC7
INNER JOIN SYS_USR USR
    ON USR.USR_ID = SC7.C7_USER
    AND USR.D_E_L_E_T_ = ''
LEFT JOIN SA2010 SA2
    ON SA2.A2_COD = SC7.C7_FORNECE
    AND SA2.A2_LOJA = SC7.C7_LOJA
    AND SA2.D_E_L_E_T_ = ''
WHERE SC7.D_E_L_E_T_ = ''
    AND SC7.C7_USER IN {USUARIOS}
"""

QUERY_NOVOS = QUERY_PEDIDOS + "    AND SC7.C7_EMISSAO >= ?\nORDER BY SC7.C7_EMISSAO DESC"
QUERY_COMPLETA = QUERY_PEDIDOS + "ORDER BY SC7.C7_EMISSAO DESC"

SELECT_PEDIDOS = (
    'SELECT usuario, filial, pedido_compra, item, produto, '
    'descricao_produto, quantidade, cod_fornecedor, fornecedor, '
    'deposito_estoque, data_emissao FROM pedidos ORDER BY data_emissao DESC'
)

INSERT_PEDIDO = '''
    INSERT OR IGNORE INTO pedidos
    (usuario, filial, pedido_compra, item, produto,
     descricao_produto, quantidade, cod_fornecedor,
     fornecedor, deposito_estoque, data_emissao)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
'''


def registrar_sync_event(registros_novos, status, erro_resumo=None):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO sync_log (executado_em, registros_novos, status, erro_resumo) '
        'VALUES (?, ?, ?, ?)',
        (agora(), registros_novos, status, erro_resumo)
    )
    conn.commit()
    conn.close()


def consolidar_sync_log():
    conn = conectar_pedidos()
    duplicados = conn.execute(
        'SELECT executado_em FROM sync_log '
        'WHERE executado_em IS NOT NULL '
        'GROUP BY executado_em HAVING COUNT(*) > 1'
    ).fetchall()

    for item in duplicados:
        executado_em = item['executado_em']
        linhas = conn.execute(
            'SELECT id, registros_novos, status, erro_resumo FROM sync_log '
            'WHERE executado_em = ? ORDER BY id ASC',
            (executado_em,)
        ).fetchall()
        if not linhas:
            continue

        linha_erro = next((linha for linha in linhas if linha['status'] == 'erro'), None)
        linha_sucesso = next((linha for linha in linhas if linha['registros_novos'] > 0), None)
        linha_base = linha_erro or linha_sucesso or linhas[0]

        conn.execute(
            'UPDATE sync_log SET registros_novos = ?, status = ?, erro_resumo = ? WHERE id = ?',
            (
                linha_base['registros_novos'],
                linha_base['status'],
                linha_base['erro_resumo'],
                linha_base['id'],
            )
        )
        conn.execute(
            'DELETE FROM sync_log WHERE executado_em = ? AND id <> ?',
            (executado_em, linha_base['id'])
        )

    conn.commit()
    conn.close()
def _inserir_no_sqlite(linhas):
    if not linhas:
        registrar_sync_event(0, 'sem_novos')
        return 0

    dados = [
        tuple(str(val).strip() if val else '' for val in linha)
        for linha in linhas
    ]

    conn = conectar_pedidos()
    antes = conn.execute('SELECT COUNT(*) FROM pedidos').fetchone()[0]
    conn.executemany(INSERT_PEDIDO, dados)
    depois = conn.execute('SELECT COUNT(*) FROM pedidos').fetchone()[0]
    inseridos = depois - antes
    conn.commit()
    conn.close()

    registrar_sync_event(
        inseridos,
        'sucesso' if inseridos > 0 else 'sem_novos'
    )
    return inseridos


def _calcular_data_corte(data_emissao_maxima):
    if not data_emissao_maxima:
        return None

    data_base = parse_protheus_date(data_emissao_maxima)
    data_corte = data_base - timedelta(days=SYNC_LOOKBACK_DAYS)
    return format_protheus_date(data_corte)


def carga_inicial():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pedidos').fetchone()[0]
    conn.close()

    if total > 0:
        return 0

    linhas = executar_select(QUERY_COMPLETA)

    return _inserir_no_sqlite(linhas)


def sincronizar():
    conn = conectar_pedidos()
    resultado = conn.execute('SELECT MAX(data_emissao) FROM pedidos').fetchone()[0]
    conn.close()

    if resultado:
        data_corte = _calcular_data_corte(resultado)
        linhas = executar_select(QUERY_NOVOS, (data_corte,))
    else:
        linhas = executar_select(QUERY_COMPLETA)

    return _inserir_no_sqlite(linhas)


def info_relatorio():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM pedidos').fetchone()[0]
    sync = conn.execute(
        'SELECT executado_em, registros_novos, '
        "COALESCE(status, CASE WHEN registros_novos > 0 THEN 'sucesso' ELSE 'sem_novos' END) AS status, "
        'erro_resumo '
        'FROM sync_log ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()
    if not sync:
        return total, None, 'nunca', None
    return total, sync['executado_em'], sync['status'], sync['erro_resumo']


def historico_sync(limit=10):
    conn = conectar_pedidos()
    linhas = conn.execute(
        'SELECT executado_em, registros_novos FROM sync_log '
        'WHERE registros_novos > 0 '
        'ORDER BY id DESC LIMIT ?',
        (limit,)
    ).fetchall()
    conn.close()
    return linhas


def gerar_csv():
    conn = conectar_pedidos()
    linhas = conn.execute(SELECT_PEDIDOS).fetchall()
    conn.close()

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(COLUNAS)
    for linha in linhas:
        writer.writerow([str(val).strip() if val else '' for val in linha])
    output.seek(0)
    return output.getvalue(), len(linhas)


def gerar_excel():
    from openpyxl import Workbook

    conn = conectar_pedidos()
    linhas = conn.execute(SELECT_PEDIDOS).fetchall()
    conn.close()

    wb = Workbook()
    ws = wb.active
    ws.title = 'Pedidos de Compra'
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
