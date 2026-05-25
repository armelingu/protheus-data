import csv
import io
from collections import Counter
from decimal import Decimal, InvalidOperation

from dotenv import load_dotenv

from database import conectar_pedidos, agora
from services.protheus_readonly import executar_select

load_dotenv()

COLUNAS = [
    'PRODUTO',
    'FILIAL',
    'ARMAZEM',
    'SALDO_ATUAL',
    'QTDE_EM_PEDIDOS_VENDA',
    'QTDE_EM_RESERVA',
    'SALDO_DISPONIVEL',
]

QUERY_ESTOQUE = """
SELECT
    B2.B2_COD        AS Produto,
    B2.B2_FILIAL     AS Filial,
    B2.B2_LOCAL      AS Armazem,
    B2.B2_QATU       AS SaldoAtual,
    B2.B2_QPEDVEN    AS QtdeEmPedidosVenda,
    B2.B2_RESERVA    AS QtdeEmReserva
FROM SB2010 B2
WHERE 
    B2.D_E_L_E_T_ = ''
ORDER BY
    B2.B2_FILIAL,
    B2.B2_LOCAL,
    B2.B2_COD Desc;
"""

SELECT_ESTOQUE = (
    'SELECT produto, filial, armazem, saldo_atual, '
    'qtde_pedidos_venda, qtde_reserva, saldo_disponivel '
    'FROM estoque_saldos ORDER BY filial, armazem, produto DESC'
)

INSERT_ESTOQUE = '''
    INSERT INTO estoque_saldos
    (produto, descricao_produto, filial, armazem, saldo_atual,
     qtde_pedidos_venda, qtde_reserva, saldo_disponivel)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
'''


def registrar_sync_event(registros_novos, status, erro_resumo=None,
                         total_protheus=None, total_local=None):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO estoque_sync_log '
        '(executado_em, registros_novos, status, erro_resumo, total_protheus, total_local) '
        'VALUES (?, ?, ?, ?, ?, ?)',
        (agora(), registros_novos, status, erro_resumo, total_protheus, total_local)
    )
    conn.commit()
    conn.close()


def consolidar_sync_log():
    conn = conectar_pedidos()
    duplicados = conn.execute(
        'SELECT executado_em FROM estoque_sync_log '
        'WHERE executado_em IS NOT NULL '
        'GROUP BY executado_em HAVING COUNT(*) > 1'
    ).fetchall()

    for item in duplicados:
        executado_em = item['executado_em']
        linhas = conn.execute(
            'SELECT id, registros_novos, status, erro_resumo FROM estoque_sync_log '
            'WHERE executado_em = ? ORDER BY id ASC',
            (executado_em,)
        ).fetchall()
        if not linhas:
            continue

        linha_erro = next((linha for linha in linhas if linha['status'] == 'erro'), None)
        linha_sucesso = next((linha for linha in linhas if linha['registros_novos'] > 0), None)
        linha_base = linha_erro or linha_sucesso or linhas[0]

        conn.execute(
            'UPDATE estoque_sync_log SET registros_novos = ?, status = ?, erro_resumo = ? WHERE id = ?',
            (
                linha_base['registros_novos'],
                linha_base['status'],
                linha_base['erro_resumo'],
                linha_base['id'],
            )
        )
        conn.execute(
            'DELETE FROM estoque_sync_log WHERE executado_em = ? AND id <> ?',
            (executado_em, linha_base['id'])
        )

    conn.commit()
    conn.close()


def _normalizar_linhas(linhas):
    """Converte linhas do Protheus em tuplas com tipos nativos (float para números)."""
    dados = []

    for linha in linhas:
        produto = str(linha[0]).strip() if linha[0] is not None else ''
        filial = str(linha[1]).strip() if linha[1] is not None else ''
        armazem = str(linha[2]).strip() if linha[2] is not None else ''
        saldo_atual = float(_to_decimal(linha[3]))
        qtde_pedidos_venda = float(_to_decimal(linha[4]))
        qtde_reserva = float(_to_decimal(linha[5]))
        saldo_disponivel = float(
            _to_decimal(linha[3]) - _to_decimal(linha[4]) - _to_decimal(linha[5])
        )

        dados.append((
            produto,
            '',
            filial,
            armazem,
            saldo_atual,
            qtde_pedidos_venda,
            qtde_reserva,
            saldo_disponivel,
        ))

    return dados


def _to_decimal(valor):
    try:
        return Decimal(str(valor if valor is not None else '0').strip() or '0')
    except InvalidOperation:
        return Decimal('0')


def _formatar_numero_csv(valor):
    """Formata float para string limpa na exportação (sem zeros desnecessários)."""
    if valor is None:
        return ''
    try:
        v = Decimal(str(valor))
        texto = format(v.normalize(), 'f')
        if '.' in texto:
            texto = texto.rstrip('0').rstrip('.')
        return texto or '0'
    except Exception:
        return str(valor)


def _snapshot_atual():
    conn = conectar_pedidos()
    rows = conn.execute(
        'SELECT produto, filial, armazem, saldo_atual, '
        'qtde_pedidos_venda, qtde_reserva, saldo_disponivel FROM estoque_saldos'
    ).fetchall()
    conn.close()
    return [
        (
            row['produto'],
            row['filial'],
            row['armazem'],
            row['saldo_atual'],
            row['qtde_pedidos_venda'],
            row['qtde_reserva'],
            row['saldo_disponivel'],
        )
        for row in rows
    ]


def _substituir_snapshot(dados, total_protheus=None):
    anterior = Counter(_snapshot_atual())
    atual = Counter(
        (linha[0], linha[2], linha[3], linha[4], linha[5], linha[6], linha[7])
        for linha in dados
    )
    alterados = sum((atual - anterior).values()) + sum((anterior - atual).values())

    conn = conectar_pedidos()
    conn.execute('DELETE FROM estoque_saldos')
    if dados:
        conn.executemany(INSERT_ESTOQUE, dados)
    conn.commit()
    total_local = conn.execute('SELECT COUNT(*) FROM estoque_saldos').fetchone()[0]
    conn.close()

    tp = total_protheus if total_protheus is not None else len(dados)
    divergencia = abs(tp - total_local) / max(tp, 1) if tp > 0 else 0
    if divergencia > 0.05:
        status = 'alerta'
    elif alterados > 0:
        status = 'sucesso'
    else:
        status = 'sem_novos'

    registrar_sync_event(
        alterados,
        status,
        total_protheus=tp,
        total_local=total_local,
    )
    return alterados


def carga_inicial():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM estoque_saldos').fetchone()[0]
    conn.close()

    if total > 0:
        return 0

    linhas = executar_select(QUERY_ESTOQUE)
    dados = _normalizar_linhas(linhas)
    return _substituir_snapshot(dados, total_protheus=len(linhas))


def sincronizar():
    linhas = executar_select(QUERY_ESTOQUE)
    dados = _normalizar_linhas(linhas)
    return _substituir_snapshot(dados, total_protheus=len(linhas))


def info_relatorio():
    conn = conectar_pedidos()
    total = conn.execute('SELECT COUNT(*) FROM estoque_saldos').fetchone()[0]
    sync = conn.execute(
        'SELECT executado_em, registros_novos, '
        "COALESCE(status, CASE WHEN registros_novos > 0 THEN 'sucesso' ELSE 'sem_novos' END) AS status, "
        'erro_resumo '
        'FROM estoque_sync_log ORDER BY id DESC LIMIT 1'
    ).fetchone()
    conn.close()

    if not sync:
        return total, None, 'nunca', None
    return total, sync['executado_em'], sync['status'], sync['erro_resumo']


def historico_sync(limit=10, offset=0):
    conn = conectar_pedidos()
    linhas = conn.execute(
        'SELECT executado_em, registros_novos FROM estoque_sync_log '
        'WHERE registros_novos > 0 '
        'ORDER BY id DESC LIMIT ? OFFSET ?',
        (limit, offset)
    ).fetchall()
    conn.close()
    return linhas


def gerar_csv():
    conn = conectar_pedidos()
    linhas = conn.execute(SELECT_ESTOQUE).fetchall()
    conn.close()

    colunas_numericas = {'SALDO_ATUAL', 'QTDE_EM_PEDIDOS_VENDA', 'QTDE_EM_RESERVA', 'SALDO_DISPONIVEL'}
    indices_numericos = {i for i, c in enumerate(COLUNAS) if c in colunas_numericas}

    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    writer.writerow(COLUNAS)
    for linha in linhas:
        writer.writerow([
            _formatar_numero_csv(valor) if i in indices_numericos
            else (str(valor).strip() if valor is not None else '')
            for i, valor in enumerate(linha)
        ])
    output.seek(0)
    return output.getvalue(), len(linhas)


def gerar_excel():
    from openpyxl import Workbook

    conn = conectar_pedidos()
    linhas = conn.execute(SELECT_ESTOQUE).fetchall()
    conn.close()

    colunas_numericas = {'SALDO_ATUAL', 'QTDE_EM_PEDIDOS_VENDA', 'QTDE_EM_RESERVA', 'SALDO_DISPONIVEL'}
    indices_numericos = {i for i, c in enumerate(COLUNAS) if c in colunas_numericas}

    wb = Workbook()
    ws = wb.active
    ws.title = 'Saldo em Estoque'
    ws.append(COLUNAS)

    for linha in linhas:
        linha_formatada = []
        for i, valor in enumerate(linha):
            if i in indices_numericos and valor is not None:
                try:
                    linha_formatada.append(float(valor))
                except (TypeError, ValueError):
                    linha_formatada.append(valor)
            else:
                linha_formatada.append(str(valor).strip() if valor is not None else '')
        ws.append(linha_formatada)

    for col in ws.columns:
        max_len = max(len(str(cell.value or '')) for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 2, 40)

    output = io.BytesIO()
    wb.save(output)
    output.seek(0)
    return output.getvalue(), len(linhas)
