"""
ETL Sync Engine — full refresh baseado em hash MD5.

Estratégia:
  1. Busca TODOS os registros do Protheus (sem janela de data)
  2. Compara o hash MD5 de cada linha com o cache local (_etl_hash_cache)
  3. Aplica UPSERT apenas nas linhas que mudaram (novos + atualizados)
  4. Deleta orphans: registros locais que não vieram mais do Protheus
  5. Atualiza o cache de hashes
  6. Registra evento de sync com status 'full_refresh'

Vantagens vs DELETE + INSERT completo:
  - Escreve somente o que mudou   → lock de escrita mínimo no SQLite
  - Detecta deletions reais       → sem registros "fantasma" por lookback
  - Idempotente e atômico         → pode ser interrompido e re-executado sem inconsistência
  - Independente de datas         → não há janela de lookback para corromper

Uso em cada serviço:
    from services.sync_engine import full_refresh_com_hash

    def carga_completa():
        return full_refresh_com_hash(
            tabela        = 'pedidos',
            chave_colunas = ['filial', 'pedido_compra', 'item', 'nivel_aprovacao'],
            chave_idx     = (1, 2, 3, 22),
            conn_fn       = conectar_pedidos,
            query_completa= QUERY_COMPLETA,
            insert_sql    = INSERT_PEDIDO,
            norm_row      = lambda l: tuple(_norm(v) for v in l),
            registrar_sync_fn = registrar_sync_event,
        )
"""
from __future__ import annotations

import hashlib
from typing import Callable, Sequence


# ── Hash ──────────────────────────────────────────────────────────────────────

def hash_linha(valores: Sequence) -> str:
    """MD5 de todos os valores de uma linha (já normalizados como strings)."""
    conteudo = '|'.join(str(v) if v is not None else '' for v in valores)
    return hashlib.md5(conteudo.encode('utf-8')).hexdigest()


# ── Cache de hashes ───────────────────────────────────────────────────────────

def _garantir_hash_cache(conn) -> None:
    conn.execute('''
        CREATE TABLE IF NOT EXISTS _etl_hash_cache (
            tabela TEXT NOT NULL,
            chave  TEXT NOT NULL,
            hash   TEXT NOT NULL,
            PRIMARY KEY (tabela, chave)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_etl_hash_tabela ON _etl_hash_cache(tabela)'
    )


def _carregar_hashes(conn, tabela: str) -> dict[str, str]:
    _garantir_hash_cache(conn)
    return {
        r[0]: r[1]
        for r in conn.execute(
            'SELECT chave, hash FROM _etl_hash_cache WHERE tabela = ?', (tabela,)
        )
    }


def _carregar_chaves_locais(conn, tabela: str, chave_colunas: list[str]) -> dict[str, tuple]:
    """Devolve dict de {chave_str: (val1, val2, ...)} para todas as linhas locais."""
    rows = conn.execute(
        f'SELECT {", ".join(chave_colunas)} FROM {tabela}'
    ).fetchall()
    return {
        '|'.join(str(r[i]) for i in range(len(chave_colunas))): tuple(str(r[i]) for i in range(len(chave_colunas)))
        for r in rows
    }


# ── Engine principal ──────────────────────────────────────────────────────────

def full_refresh_com_hash(
    tabela:            str,
    chave_colunas:     list[str],
    chave_idx:         tuple[int, ...],
    conn_fn:           Callable,
    query_completa:    str,
    insert_sql:        str,
    norm_row:          Callable,
    registrar_sync_fn: Callable,
) -> int:
    """
    Full refresh com hash para tabelas do tipo pedidos / estoque.

    Parâmetros
    ----------
    tabela            : nome da tabela SQLite
    chave_colunas     : colunas que formam a chave única, ex: ['filial', 'pedido_compra', 'item', 'nivel_aprovacao']
    chave_idx         : índices dessas colunas na tupla normalizada, ex: (1, 2, 3, 22)
    conn_fn           : função que retorna uma conexão SQLite (ex: conectar_pedidos)
    query_completa    : query SQL que retorna TODOS os registros do Protheus
    insert_sql        : SQL de UPSERT a ser executado para cada linha mudada
    norm_row          : função que transforma uma linha bruta do Protheus em tupla normalizada
    registrar_sync_fn : função(registros_novos, status, total_protheus, total_local) para log

    Retorna
    -------
    int : número de mutações (linhas inseridas/atualizadas + orphans deletados)
    """
    from services.protheus_readonly import executar_select

    # ── 1. Busca Protheus ──────────────────────────────────────────────────────
    linhas_raw = executar_select(query_completa)
    dados = [norm_row(l) for l in linhas_raw]
    total_protheus = len(dados)

    # ── 2. Leitura do estado local (sem lock) ─────────────────────────────────
    conn = conn_fn()
    try:
        hashes_atuais  = _carregar_hashes(conn, tabela)
        chaves_locais  = _carregar_chaves_locais(conn, tabela, chave_colunas)
    finally:
        conn.close()

    # ── 3. Classifica mudanças em memória ─────────────────────────────────────
    para_inserir   : list[tuple]      = []
    novos_hashes   : dict[str, str]   = {}
    chaves_protheus: set[str]         = set()

    for d in dados:
        chave = '|'.join(str(d[i]) for i in chave_idx)
        h     = hash_linha(d)
        chaves_protheus.add(chave)
        if hashes_atuais.get(chave) != h:
            para_inserir.append(d)
            novos_hashes[chave] = h

    # Orphans: existem localmente mas não vieram mais do Protheus
    orphans_chaves = set(chaves_locais.keys()) - chaves_protheus
    orphans_values = [chaves_locais[k] for k in orphans_chaves]

    mutacoes = len(para_inserir) + len(orphans_values)

    # ── 4. Aplica em transação atômica ────────────────────────────────────────
    if mutacoes == 0 and not orphans_chaves - set(hashes_atuais.keys()):
        # Nada mudou
        registrar_sync_fn(0, 'full_refresh',
                          total_protheus=total_protheus, total_local=total_protheus)
        return 0

    conn = conn_fn()
    try:
        conn.execute('BEGIN IMMEDIATE')

        if para_inserir:
            conn.executemany(insert_sql, para_inserir)

        if orphans_values:
            delete_sql = (
                f'DELETE FROM {tabela} WHERE '
                + ' AND '.join(f'{col} = ?' for col in chave_colunas)
            )
            conn.executemany(delete_sql, orphans_values)

        # Atualiza cache de hashes
        if novos_hashes:
            conn.executemany(
                'INSERT OR REPLACE INTO _etl_hash_cache (tabela, chave, hash) VALUES (?, ?, ?)',
                [(tabela, k, h) for k, h in novos_hashes.items()],
            )
        if orphans_chaves:
            conn.executemany(
                'DELETE FROM _etl_hash_cache WHERE tabela = ? AND chave = ?',
                [(tabela, k) for k in orphans_chaves],
            )

        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()

    total_local = total_protheus - len(orphans_values)
    registrar_sync_fn(mutacoes, 'full_refresh',
                      total_protheus=total_protheus, total_local=total_local)
    return mutacoes
