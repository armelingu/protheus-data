"""
Orquestrador de lote para o módulo PedCom.

Fluxo por lote:
  1. persistir_lote()   — grava lote + itens no SQLite com status 'pendente'
  2. iniciar_lote_async() — dispara processar_lote() em thread de background
  3. processar_lote()   — itera os itens, chama o WS e atualiza o status de cada um

Estratégia de concorrência (documentada no benchmark real — 07/07/2026):
  - Até LIMIAR_PARALELO itens → processamento sequencial
  - Acima             → pool de MAX_WORKERS threads (ThreadPoolExecutor)
  - Pico real medido: ~19 s sob contenção → timeout de 60 s por chamada no client.py

Estado por item: pendente → processando → sucesso (com C7_NUM) | falha (com erro)
Estado do lote:  pendente → processando → concluido | concluido_com_falhas

A conexão SQLite não é mantida aberta durante a chamada ao WS (~7–60 s):
  abre → lê/atualiza → fecha → chama WS → abre → grava resultado → fecha.
Isso evita write locks prolongados e é compatível com WAL + pool de conexões.
"""
from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

from services.database import agora, conectar_pedcom
from services.pedcom.client import incluir_pedido
from services.pedcom.validacao import validar_item

MAX_WORKERS = 3      # pool de workers — validado no benchmark com INSTANCES=1,5 no Protheus
LIMIAR_PARALELO = 50 # abaixo disso, sequencial é suficiente (~6 min para 50 itens)


# ─── Persistência ────────────────────────────────────────────────────────────

def persistir_lote(
    itens: list[dict],
    usuario_id: int,
    usuario_nome: str,
    nome_lote: str,
) -> int:
    """Grava o lote e seus itens no SQLite. Retorna o ID do lote criado.

    Parâmetros
    ----------
    itens         : list[dict] — resultado de importacao.importar_xlsx()['itens']
    usuario_id    : int        — ID do usuário que disparou o lote
    usuario_nome  : str        — nome do usuário (para exibição)
    nome_lote     : str        — nome do arquivo importado ou rótulo livre
    """
    conn = conectar_pedcom()
    try:
        codcc   = itens[0].get('CODCC', '')   if itens else ''
        codclvl = itens[0].get('CODCLVL', '') if itens else ''
        total   = len(itens)

        cur = conn.execute(
            '''
            INSERT INTO pedcom_lotes
                (criado_em, criado_por_id, criado_por_nome, nome_lote,
                 codcc, codclvl, total, pendente, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'pendente')
            ''',
            (agora(), usuario_id, usuario_nome, nome_lote,
             codcc, codclvl, total, total),
        )
        lote_id = cur.lastrowid

        for item in itens:
            conn.execute(
                '''
                INSERT INTO pedcom_itens
                    (lote_id, nome_colaborador, codfornecedor, lojafornec,
                     codigocond, codcc, codclvl, codigoproduto,
                     mesinicial, anoreferencia, qtdmeses,
                     rateios_json, status)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'pendente')
                ''',
                (
                    lote_id,
                    item.get('nome_colaborador', ''),
                    item.get('CODFORNECEDOR', ''),
                    item.get('LOJAFORNEC', ''),
                    item.get('CODIGOCOND', ''),
                    item.get('CODCC', ''),
                    item.get('CODCLVL', ''),
                    item.get('CODIGOPRODUTO', ''),
                    str(item.get('MESINICIAL', '')),
                    str(item.get('ANOREFERENCIA', '')),
                    str(item.get('QTDMESES', '')),
                    json.dumps(item.get('rateios', []), ensure_ascii=False),
                ),
            )

        conn.commit()
        return lote_id
    finally:
        conn.close()


# ─── Processamento de item individual ────────────────────────────────────────

def _montar_payload_ws(item: dict) -> dict:
    """Converte o dict do banco para o formato que o zeep espera."""
    return {
        'CODFORNECEDOR': item['codfornecedor'],
        'LOJAFORNEC':    item['lojafornec'],
        'CODIGOCOND':    item['codigocond'],
        'CODCC':         item['codcc'],
        'CODCLVL':       item['codclvl'],
        'CODIGOPRODUTO': item['codigoproduto'],
        'MESINICIAL':    str(item['mesinicial']),
        'ANOREFERENCIA': str(item['anoreferencia']),
        'QTDMESES':      str(item['qtdmeses']),
        'RATEIOS': {
            'WSHBPEDC_RATEIO': [
                {
                    'CODITEMCTA':  r['CODITEMCTA'],
                    'VALORMENSAL': str(r['VALORMENSAL']),
                }
                for r in json.loads(item['rateios_json'])
            ]
        },
    }


def _processar_item(item_id: int) -> None:
    """Processa um único item: valida → chama WS → grava resultado.

    A conexão é aberta e fechada antes e depois da chamada ao WS para não
    manter write locks durante o tempo de esposta da rede (~7–60 s).
    """
    lote_id: int | None = None
    item: dict | None = None

    # 1. Lê o item e marca como 'processando'
    conn = conectar_pedcom()
    try:
        row = conn.execute(
            'SELECT * FROM pedcom_itens WHERE id = ?', (item_id,)
        ).fetchone()
        if row is None:
            return

        item    = dict(row)
        lote_id = item['lote_id']

        conn.execute(
            'UPDATE pedcom_itens SET status = ?, iniciado_em = ? WHERE id = ?',
            ('processando', agora(), item_id),
        )
        conn.execute(
            'UPDATE pedcom_lotes SET processando = processando + 1 WHERE id = ?',
            (lote_id,),
        )
        conn.commit()
    finally:
        conn.close()

    # 2. Validação client-side + chamada ao WS (sem conexão aberta)
    erro: str | None = None
    numero: str | None = None
    try:
        # Adapta o item do banco para o formato de validar_item()
        item_validacao = {
            'CODFORNECEDOR': item['codfornecedor'],
            'LOJAFORNEC':    item['lojafornec'],
            'CODIGOCOND':    item['codigocond'],
            'CODCC':         item['codcc'],
            'CODCLVL':       item['codclvl'],
            'CODIGOPRODUTO': item['codigoproduto'],
            'MESINICIAL':    item['mesinicial'],
            'ANOREFERENCIA': item['anoreferencia'],
            'QTDMESES':      item['qtdmeses'],
            'rateios':       json.loads(item['rateios_json']),
        }
        erros_validacao = validar_item(item_validacao)
        if erros_validacao:
            raise ValueError('; '.join(erros_validacao))

        payload = _montar_payload_ws(item)
        numero  = incluir_pedido(payload)

    except Exception as e:
        erro = str(e)[:500]

    # 3. Persiste o resultado
    conn = conectar_pedcom()
    try:
        if erro is None:
            conn.execute(
                '''UPDATE pedcom_itens
                   SET status = 'sucesso', numero_pedido = ?, concluido_em = ?
                   WHERE id = ?''',
                (numero, agora(), item_id),
            )
            conn.execute(
                '''UPDATE pedcom_lotes
                   SET sucesso      = sucesso + 1,
                       processando  = processando - 1,
                       pendente     = pendente - 1
                   WHERE id = ?''',
                (lote_id,),
            )
        else:
            conn.execute(
                '''UPDATE pedcom_itens
                   SET status = 'falha', erro = ?, concluido_em = ?
                   WHERE id = ?''',
                (erro, agora(), item_id),
            )
            conn.execute(
                '''UPDATE pedcom_lotes
                   SET falha        = falha + 1,
                       processando  = processando - 1,
                       pendente     = pendente - 1
                   WHERE id = ?''',
                (lote_id,),
            )
        conn.commit()
    except Exception:
        # Garantia: mesmo que o commit falhe, não propaga para não matar o pool
        pass
    finally:
        conn.close()


# ─── Processamento do lote ────────────────────────────────────────────────────

def processar_lote(lote_id: int) -> None:
    """Processa todos os itens pendentes de um lote e finaliza o status do lote."""

    # Marca o lote como 'processando'
    conn = conectar_pedcom()
    try:
        conn.execute(
            "UPDATE pedcom_lotes SET status = 'processando', iniciado_em = ? WHERE id = ?",
            (agora(), lote_id),
        )
        conn.commit()

        rows = conn.execute(
            "SELECT id FROM pedcom_itens WHERE lote_id = ? AND status = 'pendente'",
            (lote_id,),
        ).fetchall()
        item_ids = [r['id'] for r in rows]
    finally:
        conn.close()

    # Processa os itens: sequencial até LIMIAR_PARALELO, pool acima disso
    if len(item_ids) <= LIMIAR_PARALELO:
        for item_id in item_ids:
            _processar_item(item_id)
    else:
        with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = {executor.submit(_processar_item, iid): iid for iid in item_ids}
            for future in as_completed(futures):
                try:
                    future.result()
                except Exception:
                    pass  # erros individuais já foram gravados em _processar_item

    # Finaliza o status do lote
    conn = conectar_pedcom()
    try:
        row = conn.execute(
            'SELECT sucesso, falha, pendente FROM pedcom_lotes WHERE id = ?',
            (lote_id,),
        ).fetchone()

        if row:
            if row['pendente'] == 0 and row['falha'] == 0:
                novo_status = 'concluido'
            else:
                novo_status = 'concluido_com_falhas'
        else:
            novo_status = 'concluido_com_falhas'

        conn.execute(
            'UPDATE pedcom_lotes SET status = ?, concluido_em = ? WHERE id = ?',
            (novo_status, agora(), lote_id),
        )
        conn.commit()
    finally:
        conn.close()


def iniciar_lote_async(lote_id: int) -> None:
    """Dispara processar_lote() em thread de background (daemon).

    O Flask não espera o resultado — o frontend usa polling para acompanhar
    o progresso via /api/rh/pedcom/lote/<id>/status.
    """
    t = threading.Thread(
        target=processar_lote,
        args=(lote_id,),
        daemon=True,
        name=f'pedcom-lote-{lote_id}',
    )
    t.start()


# ─── Consultas de status ──────────────────────────────────────────────────────

def obter_status_lote(lote_id: int) -> dict | None:
    """Retorna o status atual do lote e seus itens para o endpoint de polling."""
    conn = conectar_pedcom()
    try:
        lote = conn.execute(
            'SELECT * FROM pedcom_lotes WHERE id = ?', (lote_id,)
        ).fetchone()
        if lote is None:
            return None

        itens = conn.execute(
            '''SELECT id, nome_colaborador, codfornecedor, lojafornec,
                      status, numero_pedido, erro, iniciado_em, concluido_em
               FROM pedcom_itens WHERE lote_id = ? ORDER BY id''',
            (lote_id,),
        ).fetchall()

        return {
            'lote':  dict(lote),
            'itens': [dict(i) for i in itens],
        }
    finally:
        conn.close()


def listar_lotes(pagina: int = 1, por_pagina: int = 20) -> dict:
    """Lista os lotes mais recentes para a página de histórico."""
    offset = (pagina - 1) * por_pagina
    conn = conectar_pedcom()
    try:
        total = conn.execute('SELECT COUNT(*) FROM pedcom_lotes').fetchone()[0]
        rows  = conn.execute(
            '''SELECT id, criado_em, criado_por_nome, nome_lote,
                      codcc, codclvl, total, sucesso, falha, pendente,
                      status, iniciado_em, concluido_em
               FROM pedcom_lotes
               ORDER BY id DESC
               LIMIT ? OFFSET ?''',
            (por_pagina, offset),
        ).fetchall()
        return {
            'total':    total,
            'pagina':   pagina,
            'lotes':    [dict(r) for r in rows],
        }
    finally:
        conn.close()
