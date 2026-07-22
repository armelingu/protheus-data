import sqlite3
import os
from datetime import datetime, timedelta

from services.catalogo_relatorios import listar_relatorios_flat
from services.time_utils import SAO_PAULO_TZ, agora_sp, agora_sp_str

# Aponta para a raiz do projeto (/app) independente de onde database.py estiver
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_DB      = os.path.join(DATA_DIR, 'users.db')
PEDIDOS_DB    = os.path.join(DATA_DIR, 'pedidos.db')
FINANCEIRO_DB = os.path.join(DATA_DIR, 'financeiro.db')
BACKUPS_DIR   = os.path.join(DATA_DIR, 'backups')


def agora():
    return agora_sp_str()


def _aplicar_pragmas(conn):
    """PRAGMAs aplicados a toda conexão SQLite.

    - journal_mode=WAL          -> leituras concorrentes com escritas
    - synchronous=NORMAL        -> seguro com WAL e mais rápido que FULL
    - cache_size=-65536         -> 64 MB de page cache por conexão (negativo = KB)
    - mmap_size=268435456       -> 256 MB via mmap, reduz syscalls em reads
    - temp_store=MEMORY         -> temp tables/indexes em RAM
    - busy_timeout=5000         -> 5s de espera antes de SQLITE_BUSY (sync vs API)
    """
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA cache_size=-65536')
    conn.execute('PRAGMA mmap_size=268435456')
    conn.execute('PRAGMA temp_store=MEMORY')
    conn.execute('PRAGMA busy_timeout=5000')


# ─── Pool opt-in (1 conexão por thread, por DB) ──────────────────────────────
#
# Trade-off: SQLite local + WAL torna open/close barato (~µs); o pool reduz
# syscalls e aproveita o page cache da própria conexão entre requests da mesma
# thread. Como a maioria do código chama `conn.close()` ao fim do uso, ativar
# pool exige wrapper que neutraliza o close.
#
# Habilitação: SQLITE_CONN_POOL=1 (default OFF). Ative em janela controlada.
# Ao desligar (default), o comportamento é IDÊNTICO ao anterior à mudança.
import threading

_POOL_HABILITADO = os.getenv('SQLITE_CONN_POOL', '0') == '1'
_pool_local = threading.local()


class _PooledConn:
    """Wrapper que delega tudo para sqlite3.Connection mas torna close() no-op."""

    __slots__ = ('_conn',)

    def __init__(self, conn):
        self._conn = conn

    def close(self):
        # No-op: a conexão real é fechada apenas no encerramento da thread/worker.
        # Para forçar fechamento real, use `_real_close()`.
        pass

    def _real_close(self):
        try:
            self._conn.close()
        except Exception:
            pass

    def __getattr__(self, item):
        return getattr(self._conn, item)

    def __enter__(self):
        return self._conn.__enter__()

    def __exit__(self, exc_type, exc_val, exc_tb):
        return self._conn.__exit__(exc_type, exc_val, exc_tb)


def _abrir_conexao(path):
    conn = sqlite3.connect(path, check_same_thread=False, timeout=10)
    conn.row_factory = sqlite3.Row
    _aplicar_pragmas(conn)
    return conn


def _conectar(path, atributo):
    if not _POOL_HABILITADO:
        return _abrir_conexao(path)

    pool = getattr(_pool_local, 'pool', None)
    if pool is None:
        pool = {}
        _pool_local.pool = pool
    if atributo not in pool:
        pool[atributo] = _PooledConn(_abrir_conexao(path))
    return pool[atributo]


def conectar_users():
    return _conectar(USERS_DB, 'users')


def conectar_pedidos():
    return _conectar(PEDIDOS_DB, 'pedidos')


def conectar_financeiro():
    return _conectar(FINANCEIRO_DB, 'financeiro')




def fechar_pool_thread():
    """Fecha as conexões pool da thread atual. Chamar no fim do worker."""
    pool = getattr(_pool_local, 'pool', None)
    if not pool:
        return
    for c in list(pool.values()):
        if hasattr(c, '_real_close'):
            c._real_close()
        else:
            try:
                c.close()
            except Exception:
                pass
    _pool_local.pool = {}


def _garantir_coluna(conn, tabela, coluna, definicao):
    colunas = {
        row['name']
        for row in conn.execute(f'PRAGMA table_info({tabela})').fetchall()
    }
    if coluna not in colunas:
        conn.execute(f'ALTER TABLE {tabela} ADD COLUMN {coluna} {definicao}')


def _recriar_estoque_saldos_sem_unique(conn):
    tabela_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'estoque_saldos'"
    ).fetchone()

    if tabela_sql and tabela_sql['sql'] and 'UNIQUE(produto, filial, armazem)' in tabela_sql['sql']:
        conn.execute('DROP TABLE IF EXISTS estoque_saldos')


def _migrar_estoque_saldos_para_real(conn):
    """Recria estoque_saldos com colunas numéricas REAL se ainda estiverem como TEXT."""
    tabela_sql = conn.execute(
        "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'estoque_saldos'"
    ).fetchone()

    if not tabela_sql or not tabela_sql['sql']:
        return

    ddl = tabela_sql['sql'].upper()
    if 'SALDO_ATUAL REAL' not in ddl:
        conn.execute('DROP TABLE IF EXISTS estoque_saldos')


def _migrar_pedidos_schema_v2(conn):
    """Recria a tabela pedidos com o schema expandido (aprovação, preços, SC, etc.).

    A nova UNIQUE key inclui nivel_aprovacao para suportar múltiplos níveis de
    aprovação por item de pedido provenientes do JOIN com SCR010.
    """
    tabela = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='pedidos'"
    ).fetchone()

    if not tabela:
        return  # tabela ainda não existe; CREATE TABLE abaixo vai criá-la

    colunas = {row['name'] for row in conn.execute('PRAGMA table_info(pedidos)').fetchall()}
    if 'nivel_aprovacao' in colunas:
        return  # schema já está atualizado

    # Schema desatualizado — dropa e recria para aplicar nova UNIQUE key
    conn.execute('DROP TABLE IF EXISTS pedidos')


def _popular_setores_iniciais(conn):
    """Seed dos setores APENAS no primeiro startup (tabela vazia).

    Antes este seed rodava em todo startup com INSERT OR IGNORE, o que
    REVERTIA qualquer setor deletado pelo admin assim que o container era
    reiniciado (cenário real: admin deletou 'Financeira' e 'Qualidade';
    rebuild via deploy.sh chamou criar_tabelas() de novo e os setores
    voltaram). Agora só popula se a tabela estiver completamente vazia,
    respeitando o que o admin gerencia em runtime.
    """
    total = conn.execute('SELECT COUNT(*) FROM setores').fetchone()[0]
    if total > 0:
        return

    setores = [
        ('Controladoria Financeira', 'Setor de Controladoria Financeira'),
        ('Financeira',               'Setor Financeiro'),
        ('Qualidade',                'Setor de Qualidade'),
    ]
    for nome, descricao in setores:
        conn.execute(
            'INSERT INTO setores (nome, descricao, ativo, criado_em) VALUES (?, ?, 1, ?)',
            (nome, descricao, agora())
        )


def _popular_permissoes_iniciais(conn):
    usuarios = conn.execute('SELECT id FROM usuarios').fetchall()
    total_permissoes = conn.execute(
        'SELECT COUNT(*) AS total FROM usuario_permissoes_relatorio'
    ).fetchone()['total']

    if not usuarios or total_permissoes > 0:
        return

    permissoes = []
    for usuario in usuarios:
        for relatorio in listar_relatorios_flat():
            permissoes.append((
                usuario['id'],
                relatorio['modulo_id'],
                relatorio['relatorio_id'],
                1,
                agora(),
                agora(),
            ))

    conn.executemany(
        '''
        INSERT INTO usuario_permissoes_relatorio
        (usuario_id, modulo_id, relatorio_id, permitido, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        permissoes
    )


def _garantir_admin_inicial(conn):
    total_admins = conn.execute(
        'SELECT COUNT(*) AS total FROM usuarios WHERE COALESCE(is_admin, 0) = 1'
    ).fetchone()['total']
    if total_admins > 0:
        return

    primeiro_usuario = conn.execute(
        'SELECT id FROM usuarios ORDER BY id ASC LIMIT 1'
    ).fetchone()
    if not primeiro_usuario:
        return

    conn.execute(
        '''
        UPDATE usuarios
        SET is_admin = 1,
            ativo = 1,
            atualizado_em = ?
        WHERE id = ?
        ''',
        (agora(), primeiro_usuario['id'])
    )


def criar_tabelas():
    conn = conectar_users()
    # Migration: tabela 'pedidos' órfã (cópia histórica) que sobrou em users.db.
    # Inflama backup e não é referenciada por nenhum código. Idempotente.
    conn.execute('DROP TABLE IF EXISTS pedidos')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT UNIQUE NOT NULL,
            senha TEXT NOT NULL,
            nome TEXT NOT NULL,
            criado_em TEXT
        )
    ''')
    _garantir_coluna(conn, 'usuarios', 'email', 'TEXT')
    _garantir_coluna(conn, 'usuarios', 'ativo', 'INTEGER DEFAULT 1')
    _garantir_coluna(conn, 'usuarios', 'is_admin', 'INTEGER DEFAULT 0')
    _garantir_coluna(conn, 'usuarios', 'deve_trocar_senha', 'INTEGER DEFAULT 0')
    _garantir_coluna(conn, 'usuarios', 'ultimo_login_em', 'TEXT')
    _garantir_coluna(conn, 'usuarios', 'desativado_em', 'TEXT')
    _garantir_coluna(conn, 'usuarios', 'desativado_por', 'INTEGER')
    _garantir_coluna(conn, 'usuarios', 'atualizado_em', 'TEXT')
    _garantir_coluna(conn, 'usuarios', 'pode_ver_query', 'INTEGER DEFAULT 0')
    _garantir_coluna(conn, 'usuarios', 'setor_id', 'INTEGER')
    _garantir_coluna(conn, 'usuarios', 'is_gerente', 'INTEGER DEFAULT 0')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_usuarios_usuario ON usuarios(usuario)')
    conn.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_usuarios_email_unique "
        "ON usuarios(email) WHERE email IS NOT NULL AND TRIM(email) <> ''"
    )
    conn.execute('CREATE INDEX IF NOT EXISTS idx_usuarios_ativo ON usuarios(ativo)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS login_tentativas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ip TEXT NOT NULL,
            tentativas INTEGER DEFAULT 1,
            primeira_tentativa TEXT,
            bloqueado_ate TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_login_tentativas_ip ON login_tentativas(ip)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS logs_acesso (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            acao TEXT NOT NULL,
            ip TEXT,
            data_hora TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_logs_acesso_data_hora ON logs_acesso(data_hora)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS usuario_permissoes_relatorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            modulo_id TEXT NOT NULL,
            relatorio_id TEXT NOT NULL,
            permitido INTEGER DEFAULT 1,
            criado_em TEXT,
            atualizado_em TEXT,
            UNIQUE(usuario_id, modulo_id, relatorio_id)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_usuario_permissoes_usuario ON usuario_permissoes_relatorio(usuario_id)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_usuario_permissoes_relatorio '
        'ON usuario_permissoes_relatorio(modulo_id, relatorio_id)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS auditoria_admin (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_usuario_id INTEGER,
            admin_usuario_nome TEXT,
            acao TEXT NOT NULL,
            usuario_afetado_id INTEGER,
            usuario_afetado_login TEXT,
            detalhes_antes TEXT,
            detalhes_depois TEXT,
            detalhe TEXT,
            ip TEXT,
            data_hora TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_auditoria_admin_data_hora ON auditoria_admin(data_hora)')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_auditoria_admin_usuario_afetado '
        'ON auditoria_admin(usuario_afetado_id, data_hora)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS emails_usuarios_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            email_destino TEXT,
            tipo TEXT NOT NULL,
            status TEXT NOT NULL,
            tentativas INTEGER DEFAULT 1,
            ultimo_erro TEXT,
            payload TEXT,
            criado_em TEXT,
            enviado_em TEXT,
            atualizado_em TEXT
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_emails_usuarios_log_usuario '
        'ON emails_usuarios_log(usuario_id, id DESC)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_emails_usuarios_log_status '
        'ON emails_usuarios_log(status, atualizado_em)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS setores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT UNIQUE NOT NULL,
            descricao TEXT,
            ativo INTEGER DEFAULT 1,
            criado_em TEXT
        )
    ''')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS setor_permissoes_relatorio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            setor_id INTEGER NOT NULL,
            modulo_id TEXT NOT NULL,
            relatorio_id TEXT NOT NULL,
            criado_em TEXT,
            UNIQUE(setor_id, modulo_id, relatorio_id)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_setor_permissoes_setor '
        'ON setor_permissoes_relatorio(setor_id)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_tokens (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            token TEXT UNIQUE NOT NULL,
            criado_em TEXT,
            ultimo_uso TEXT,
            ativo INTEGER DEFAULT 1
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_api_tokens_usuario '
        'ON api_tokens(usuario_id)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS api_token_permissoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            token_id INTEGER NOT NULL,
            modulo_id TEXT NOT NULL,
            relatorio_id TEXT NOT NULL,
            UNIQUE(token_id, modulo_id, relatorio_id)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_api_token_permissoes_token '
        'ON api_token_permissoes(token_id)'
    )
    _popular_setores_iniciais(conn)
    _popular_permissoes_iniciais(conn)
    _garantir_admin_inicial(conn)
    conn.commit()
    conn.close()

    conn = conectar_pedidos()
    _recriar_estoque_saldos_sem_unique(conn)
    _migrar_estoque_saldos_para_real(conn)
    _migrar_pedidos_schema_v2(conn)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            filial TEXT,
            pedido_compra TEXT,
            item TEXT,
            produto TEXT,
            unidade TEXT,
            descricao_produto TEXT,
            quantidade TEXT,
            preco_unitario TEXT,
            preco_total TEXT,
            data_entrega TEXT,
            numero_sc TEXT,
            item_sc TEXT,
            observacoes TEXT,
            classe_valor TEXT,
            qtd_entregue TEXT,
            num_cotacao TEXT,
            moeda TEXT,
            cod_fornecedor TEXT,
            fornecedor TEXT,
            deposito_estoque TEXT,
            data_emissao TEXT,
            nivel_aprovacao TEXT NOT NULL DEFAULT '',
            aprovador TEXT,
            data_aprovacao TEXT,
            status_aprovacao TEXT,
            UNIQUE(filial, pedido_compra, item, nivel_aprovacao)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_emissao ON pedidos(data_emissao)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT
        )
    ''')
    _garantir_coluna(conn, 'sync_log', 'status', 'TEXT')
    _garantir_coluna(conn, 'sync_log', 'erro_resumo', 'TEXT')
    _garantir_coluna(conn, 'sync_log', 'total_protheus', 'INTEGER')
    _garantir_coluna(conn, 'sync_log', 'total_local', 'INTEGER')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_sync_log_executado_em ON sync_log(executado_em)')

    # ── Pedidos de Compra Detalhado (CC, Item Orçamentário, Conta, Cond. Pgto) ─
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_detalhado (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            filial TEXT,
            pedido_compra TEXT,
            item TEXT,
            produto TEXT,
            unidade TEXT,
            descricao_produto TEXT,
            quantidade TEXT,
            preco_unitario TEXT,
            preco_total TEXT,
            data_entrega TEXT,
            numero_sc TEXT,
            item_sc TEXT,
            observacoes TEXT,
            classe_valor TEXT,
            qtd_entregue TEXT,
            num_cotacao TEXT,
            moeda TEXT,
            cod_fornecedor TEXT,
            fornecedor TEXT,
            deposito_estoque TEXT,
            data_emissao TEXT,
            nivel_aprovacao TEXT NOT NULL DEFAULT '',
            aprovador TEXT,
            data_aprovacao TEXT,
            status_aprovacao TEXT,
            centro_custo TEXT,
            centro_custo_desc TEXT,
            item_conta TEXT,
            item_conta_desc TEXT,
            conta_contabil TEXT,
            conta_contabil_desc TEXT,
            cond_pagamento TEXT,
            cond_pagamento_desc TEXT,
            UNIQUE(filial, pedido_compra, item, nivel_aprovacao)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pedidos_detalhado_emissao '
        'ON pedidos_detalhado(data_emissao)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_detalhado_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT,
            total_protheus INTEGER,
            total_local INTEGER
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pedidos_detalhado_sync_log_executado_em '
        'ON pedidos_detalhado_sync_log(executado_em)'
    )

    # ── Pedidos Energy (mesma estrutura de `pedidos`, escopo separado) ──────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_energy (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            filial TEXT,
            pedido_compra TEXT,
            item TEXT,
            produto TEXT,
            unidade TEXT,
            descricao_produto TEXT,
            quantidade TEXT,
            preco_unitario TEXT,
            preco_total TEXT,
            data_entrega TEXT,
            numero_sc TEXT,
            item_sc TEXT,
            observacoes TEXT,
            classe_valor TEXT,
            qtd_entregue TEXT,
            num_cotacao TEXT,
            moeda TEXT,
            cod_fornecedor TEXT,
            fornecedor TEXT,
            deposito_estoque TEXT,
            data_emissao TEXT,
            nivel_aprovacao TEXT NOT NULL DEFAULT '',
            aprovador TEXT,
            data_aprovacao TEXT,
            status_aprovacao TEXT,
            UNIQUE(filial, pedido_compra, item, nivel_aprovacao)
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_pedidos_energy_emissao ON pedidos_energy(data_emissao)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_energy_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT,
            total_protheus INTEGER,
            total_local INTEGER
        )
    ''')
    _garantir_coluna(conn, 'pedidos_energy_sync_log', 'status', 'TEXT')
    _garantir_coluna(conn, 'pedidos_energy_sync_log', 'erro_resumo', 'TEXT')
    _garantir_coluna(conn, 'pedidos_energy_sync_log', 'total_protheus', 'INTEGER')
    _garantir_coluna(conn, 'pedidos_energy_sync_log', 'total_local', 'INTEGER')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pedidos_energy_sync_log_executado_em '
        'ON pedidos_energy_sync_log(executado_em)'
    )
    # ── Pedidos de Compra — Conta Contábil 05.001 (Energy, todos os compradores) ─
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_conta_05001 (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            filial TEXT,
            pedido_compra TEXT,
            item TEXT,
            produto TEXT,
            unidade TEXT,
            descricao_produto TEXT,
            quantidade TEXT,
            preco_unitario TEXT,
            preco_total TEXT,
            data_entrega TEXT,
            numero_sc TEXT,
            item_sc TEXT,
            observacoes TEXT,
            classe_valor TEXT,
            qtd_entregue TEXT,
            num_cotacao TEXT,
            moeda TEXT,
            cod_fornecedor TEXT,
            fornecedor TEXT,
            deposito_estoque TEXT,
            data_emissao TEXT,
            aprovador TEXT,
            data_aprovacao TEXT,
            status_aprovacao TEXT,
            UNIQUE(filial, pedido_compra, item)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pedidos_conta_05001_emissao '
        'ON pedidos_conta_05001(data_emissao)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_conta_05001_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT,
            total_protheus INTEGER,
            total_local INTEGER
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pedidos_conta_05001_sync_log_executado_em '
        'ON pedidos_conta_05001_sync_log(executado_em)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS downloads_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            formato TEXT,
            registros INTEGER,
            data_hora TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_downloads_log_data_hora ON downloads_log(data_hora)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS estoque_saldos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto TEXT,
            descricao_produto TEXT,
            filial TEXT,
            armazem TEXT,
            saldo_atual REAL,
            qtde_pedidos_venda REAL,
            qtde_reserva REAL,
            saldo_disponivel REAL
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_estoque_saldos_filial_armazem ON estoque_saldos(filial, armazem)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS estoque_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT
        )
    ''')
    _garantir_coluna(conn, 'estoque_sync_log', 'status', 'TEXT')
    _garantir_coluna(conn, 'estoque_sync_log', 'erro_resumo', 'TEXT')
    _garantir_coluna(conn, 'estoque_sync_log', 'total_protheus', 'INTEGER')
    _garantir_coluna(conn, 'estoque_sync_log', 'total_local', 'INTEGER')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_estoque_sync_log_executado_em ON estoque_sync_log(executado_em)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS estoque_downloads_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            formato TEXT,
            registros INTEGER,
            data_hora TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_estoque_downloads_log_data_hora ON estoque_downloads_log(data_hora)')

    # ── Histórico de pedidos (2024–hoje, todos os usuários Protheus) ──────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos_historico (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            filial TEXT,
            pedido_compra TEXT,
            item TEXT,
            produto TEXT,
            descricao_produto TEXT,
            quantidade TEXT,
            cod_fornecedor TEXT,
            fornecedor TEXT,
            deposito_estoque TEXT,
            data_emissao TEXT,
            UNIQUE(filial, pedido_compra, item)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pedidos_historico_emissao ON pedidos_historico(data_emissao)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS historico_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT,
            total_protheus INTEGER,
            total_local INTEGER
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_historico_sync_log_executado_em ON historico_sync_log(executado_em)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS historico_downloads_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            formato TEXT,
            registros INTEGER,
            data_hora TEXT
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_historico_downloads_log_data_hora ON historico_downloads_log(data_hora)'
    )
    # ── Pendências de Aprovação de Pedidos de Compra ──────────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pendencia_aprovacao (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario TEXT,
            filial TEXT,
            pedido_compra TEXT,
            valor_total TEXT,
            data_emissao TEXT,
            cod_fornecedor TEXT,
            fornecedor TEXT,
            nivel_aprovacao TEXT NOT NULL DEFAULT '',
            aprovador TEXT,
            data_aprovacao TEXT,
            status_aprovacao TEXT,
            UNIQUE(filial, pedido_compra, nivel_aprovacao)
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pendencia_aprovacao_emissao ON pendencia_aprovacao(data_emissao)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pendencia_aprovacao_aprovador ON pendencia_aprovacao(aprovador)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pendencia_aprovacao_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT,
            registros_novos INTEGER DEFAULT 0,
            status TEXT,
            erro_resumo TEXT,
            total_protheus INTEGER,
            total_local INTEGER
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_pendencia_aprovacao_sync_log_executado_em '
        'ON pendencia_aprovacao_sync_log(executado_em)'
    )
    conn.commit()
    conn.close()
    criar_tabelas_financeiro()


def _migrar_tabela_financeiro(conn, tabela, coluna_marcadora, sync_log=None, cursor_key=None):
    """Dropa a tabela se não tiver a coluna_marcadora (schema desatualizado).
    Usa PRAGMA table_info para verificação confiável — SQLite trata identificadores
    em aspas duplas inexistentes como string literals, não como erro."""
    try:
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info({tabela})').fetchall()]
    except Exception:
        return
    if cols and coluna_marcadora not in cols:
        print(f'[MIGRAÇÃO] {tabela}: schema desatualizado — recriando com campos completos.')
        conn.execute(f'DROP TABLE IF EXISTS {tabela}')
        if sync_log:
            conn.execute(f'DROP TABLE IF EXISTS {sync_log}')
        if cursor_key:
            conn.execute("DELETE FROM sync_cursor WHERE tabela = ?", (cursor_key,))


def criar_tabelas_financeiro():
    """Cria/migra o banco financeiro.db com as 5 tabelas do módulo Controladoria.
    Colunas nomeadas conforme campos originais do Protheus (D1_*, E1_*, etc.)."""
    conn = conectar_financeiro()

    # ── Cursor de extração keyset (R_E_C_N_O_ por tabela) ────────────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS sync_cursor (
            tabela TEXT PRIMARY KEY,
            ultimo_recno INTEGER DEFAULT 0,
            atualizado_em TEXT
        )
    ''')

    # ── SD1010 — Itens de NF de Entrada ──────────────────────────────────────
    _migrar_tabela_financeiro(conn, 'nf_entrada_itens', 'D1_ITEM',
                              sync_log='nf_entrada_sync_log', cursor_key='nf_entrada')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nf_entrada_itens (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            recno     INTEGER UNIQUE NOT NULL,
            D1_FILIAL  TEXT, D1_DOC   TEXT, D1_SERIE  TEXT, D1_ITEM   TEXT,
            D1_FORNECE TEXT, D1_LOJA  TEXT, NomeFornecedor TEXT,
            D1_EMISSAO TEXT, D1_DTDIGIT TEXT,
            D1_COD    TEXT,  D1_DESC  TEXT,  D1_UM     TEXT,
            D1_QUANT  REAL,  D1_VUNIT REAL,  D1_TOTAL  REAL,
            D1_VALIPI REAL,  D1_IPI   REAL,
            D1_VALICM REAL,  D1_PICM  REAL,
            D1_TP     TEXT,  D1_TES   TEXT,  D1_CF     TEXT,
            D1_GRUPO  TEXT,  D1_LOCAL TEXT,
            D1_PEDIDO TEXT,  D1_ITEMPC TEXT,
            D1_VALDESC REAL, D1_PESO  REAL
        )
    ''')
    # Migração: adiciona NomeFornecedor a tabelas criadas antes desta versão
    try:
        conn.execute('ALTER TABLE nf_entrada_itens ADD COLUMN NomeFornecedor TEXT')
    except Exception:
        pass  # coluna já existe
    conn.execute('CREATE INDEX IF NOT EXISTS idx_nf_entrada_emissao    ON nf_entrada_itens(D1_EMISSAO)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_nf_entrada_fornecedor ON nf_entrada_itens(D1_FORNECE)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_nf_entrada_produto    ON nf_entrada_itens(D1_COD)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nf_entrada_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT, registros_novos INTEGER DEFAULT 0,
            status TEXT, erro_resumo TEXT
        )
    ''')

    # ── SD2010 — Itens de NF de Saída ────────────────────────────────────────
    _migrar_tabela_financeiro(conn, 'nf_saida_itens', 'D2_ITEM',
                              sync_log='nf_saida_sync_log', cursor_key='nf_saida')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nf_saida_itens (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            recno     INTEGER UNIQUE NOT NULL,
            D2_FILIAL  TEXT, D2_DOC    TEXT, D2_SERIE  TEXT, D2_ITEM   TEXT,
            D2_CLIENTE TEXT, D2_LOJA   TEXT, NomeCliente TEXT,
            D2_EMISSAO TEXT, D2_DTDIGIT TEXT,
            D2_COD    TEXT,  D2_DESC   TEXT,  D2_UM     TEXT,
            D2_QUANT  REAL,  D2_PRUNIT REAL,  D2_PRCVEN REAL,
            D2_VALIPI REAL,  D2_IPI    REAL,
            D2_VALICM REAL,  D2_PICM   REAL,
            D2_TP     TEXT,  D2_TES    TEXT,  D2_CF     TEXT,
            D2_GRUPO  TEXT,  D2_LOCAL  TEXT,
            D2_PEDIDO TEXT,  D2_ITEMPV TEXT,
            D2_DESCON REAL,  D2_TIPO   TEXT
        )
    ''')
    # Migração: adiciona NomeCliente a tabelas criadas antes desta versão
    try:
        conn.execute('ALTER TABLE nf_saida_itens ADD COLUMN NomeCliente TEXT')
    except Exception:
        pass  # coluna já existe
    conn.execute('CREATE INDEX IF NOT EXISTS idx_nf_saida_emissao  ON nf_saida_itens(D2_EMISSAO)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_nf_saida_cliente  ON nf_saida_itens(D2_CLIENTE)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_nf_saida_produto  ON nf_saida_itens(D2_COD)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS nf_saida_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT, registros_novos INTEGER DEFAULT 0,
            status TEXT, erro_resumo TEXT
        )
    ''')

    # ── SE1010 — Contas a Receber ─────────────────────────────────────────────
    _migrar_tabela_financeiro(conn, 'contas_receber', 'E1_PREFIXO',
                              sync_log='contas_receber_sync_log', cursor_key='contas_receber')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contas_receber (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            recno     INTEGER UNIQUE NOT NULL,
            E1_FILIAL  TEXT, E1_PREFIXO TEXT, E1_NUM    TEXT, E1_PARCELA TEXT, E1_TIPO TEXT,
            E1_CLIENTE TEXT, E1_LOJA    TEXT, E1_NOMCLI TEXT,
            E1_EMISSAO TEXT, E1_VENCTO  TEXT, E1_VENCREA TEXT,
            E1_VALOR   REAL, E1_SALDO   REAL, E1_BAIXA  TEXT,
            E1_NATUREZ TEXT, E1_HIST    TEXT,
            E1_STATUS  TEXT, E1_SITUACA TEXT, E1_MOEDA  TEXT,
            E1_PORTADO TEXT, E1_AGEDEP  TEXT,
            E1_NUMNOTA TEXT, E1_SERIE   TEXT, E1_MOTIVO TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cr_vencimento ON contas_receber(E1_VENCTO)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cr_emissao    ON contas_receber(E1_EMISSAO)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cr_cliente    ON contas_receber(E1_CLIENTE)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contas_receber_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT, registros_novos INTEGER DEFAULT 0,
            status TEXT, erro_resumo TEXT
        )
    ''')

    # ── SE2010 — Contas a Pagar ───────────────────────────────────────────────
    _migrar_tabela_financeiro(conn, 'contas_pagar', 'E2_PREFIXO',
                              sync_log='contas_pagar_sync_log', cursor_key='contas_pagar')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contas_pagar (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            recno     INTEGER UNIQUE NOT NULL,
            E2_FILIAL  TEXT, E2_PREFIXO TEXT, E2_NUM    TEXT, E2_PARCELA TEXT, E2_TIPO TEXT,
            E2_FORNECE TEXT, E2_LOJA    TEXT, E2_NOMFOR TEXT,
            E2_EMISSAO TEXT, E2_VENCTO  TEXT, E2_VENCREA TEXT, E2_VENCORI TEXT,
            E2_VALOR   REAL, E2_SALDO   REAL, E2_BAIXA  TEXT,
            E2_ISS     REAL, E2_IRRF    REAL, E2_DESCONT REAL, E2_MULTA  REAL, E2_JUROS  REAL,
            E2_CORREC  REAL, E2_ACRESC  REAL, E2_DECRESC REAL, E2_VALLIQ REAL, E2_VLCRUZ REAL,
            E2_TXMOEDA REAL, E2_DATALIB TEXT,
            E2_NATUREZ TEXT, E2_HIST    TEXT,
            E2_STATUS  TEXT, E2_MOEDA   TEXT,
            E2_BCOPAG  TEXT, E2_MOTIVO  TEXT, E2_RATEIO TEXT
        )
    ''')
    # Migração: adiciona campos financeiros ausentes em tabelas criadas antes desta versão
    _novos_campos_cp = [
        ('E2_VENCORI', 'TEXT'), ('E2_ISS',    'REAL'), ('E2_IRRF',    'REAL'),
        ('E2_DESCONT', 'REAL'), ('E2_MULTA',  'REAL'), ('E2_JUROS',   'REAL'),
        ('E2_CORREC',  'REAL'), ('E2_ACRESC', 'REAL'), ('E2_DECRESC', 'REAL'),
        ('E2_VALLIQ',  'REAL'), ('E2_VLCRUZ', 'REAL'), ('E2_TXMOEDA', 'REAL'),
        ('E2_DATALIB', 'TEXT'),
    ]
    for coluna, tipo in _novos_campos_cp:
        try:
            conn.execute(f'ALTER TABLE contas_pagar ADD COLUMN {coluna} {tipo}')
        except Exception:
            pass  # coluna já existe
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cp_vencimento  ON contas_pagar(E2_VENCTO)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cp_emissao     ON contas_pagar(E2_EMISSAO)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_cp_fornecedor  ON contas_pagar(E2_FORNECE)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS contas_pagar_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT, registros_novos INTEGER DEFAULT 0,
            status TEXT, erro_resumo TEXT
        )
    ''')

    # ── SE5010 — Movimentos Bancários ─────────────────────────────────────────
    _migrar_tabela_financeiro(conn, 'mov_bancarios', 'E5_TIPO',
                              sync_log='mov_bancarios_sync_log', cursor_key='mov_bancarios')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mov_bancarios (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            recno     INTEGER UNIQUE NOT NULL,
            E5_FILIAL  TEXT, E5_BANCO  TEXT, E5_AGENCIA TEXT, E5_CONTA   TEXT,
            E5_DATA    TEXT, E5_VALOR  REAL,  E5_RECPAG  TEXT,
            E5_NATUREZ TEXT, E5_HISTOR TEXT, E5_DOCUMEN TEXT,
            E5_TIPO    TEXT, E5_TIPOLAN TEXT, E5_NUMCHEQ TEXT,
            E5_VENCTO  TEXT, E5_BENEF  TEXT,
            E5_PREFIXO TEXT, E5_NUMERO TEXT, E5_PARCELA TEXT,
            E5_CLIFOR  TEXT, E5_LOJA   TEXT,
            E5_MOTBX   TEXT, E5_TIPODOC TEXT, E5_DTDIGIT TEXT
        )
    ''')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mb_data_mov ON mov_bancarios(E5_DATA)')
    conn.execute('CREATE INDEX IF NOT EXISTS idx_mb_conta    ON mov_bancarios(E5_BANCO, E5_AGENCIA, E5_CONTA)')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS mov_bancarios_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT, registros_novos INTEGER DEFAULT 0,
            status TEXT, erro_resumo TEXT
        )
    ''')

    # ── Energy — Contas a Pagar (subset de SE2010 com filtros do negócio Energy) ──
    # Colunas com nomes amigáveis (Filial, Vencimento, ...) para usuários leigos.
    # Marker 'Negocio' força recriação se a tabela ainda estiver no schema antigo (E2_*).
    _migrar_tabela_financeiro(conn, 'energy_contas_pagar', 'Negocio',
                              sync_log='energy_contas_pagar_sync_log',
                              cursor_key='energy_contas_pagar')
    conn.execute('''
        CREATE TABLE IF NOT EXISTS energy_contas_pagar (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            recno     INTEGER UNIQUE NOT NULL,
            Filial         TEXT, Prefixo  TEXT, NumeroTitulo TEXT, Parcela TEXT, Tipo TEXT,
            Natureza       TEXT, Negocio  TEXT, Rastreamento TEXT, CentroCusto TEXT,
            Fornecedor     TEXT, Loja     TEXT, NomeFornecedor TEXT,
            DataEmissao    TEXT, Vencimento TEXT, VencimentoReal TEXT,
            ValorTitulo    REAL, ISS REAL, IRRF REAL, Databaixa TEXT,
            BancoPagamento TEXT, DataContabil TEXT, Historico TEXT,
            Saldo          REAL, Desconto REAL, Multa REAL, Juros REAL, Correcao REAL,
            ValorLiquidoBaixado REAL, VencimentoOriginal TEXT, Moeda TEXT, VlrEmReal REAL,
            Acrescimo      REAL, DataLiberacao TEXT, TaxaMoeda REAL, Decrescimo REAL, FilialOriginal TEXT
        )
    ''')
    # Migração: corrige typo FilialOrignal → FilialOriginal (SQLite 3.25+)
    try:
        conn.execute('ALTER TABLE energy_contas_pagar RENAME COLUMN FilialOrignal TO FilialOriginal')
    except Exception:
        pass  # coluna já foi renomeada ou SQLite < 3.25
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_energy_contas_pagar_vencto '
        'ON energy_contas_pagar(Vencimento)'
    )
    conn.execute('''
        CREATE TABLE IF NOT EXISTS energy_contas_pagar_sync_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            executado_em TEXT, registros_novos INTEGER DEFAULT 0,
            status TEXT, erro_resumo TEXT
        )
    ''')

    # ── Log de downloads dos relatórios financeiros (auditoria) ──────────────
    conn.execute('''
        CREATE TABLE IF NOT EXISTS financeiro_downloads_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER,
            usuario_nome TEXT,
            relatorio TEXT NOT NULL,
            formato TEXT,
            registros INTEGER,
            ip TEXT,
            data_hora TEXT
        )
    ''')
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_financeiro_downloads_log_data_hora '
        'ON financeiro_downloads_log(data_hora)'
    )
    conn.execute(
        'CREATE INDEX IF NOT EXISTS idx_financeiro_downloads_log_relatorio '
        'ON financeiro_downloads_log(relatorio, data_hora)'
    )

    conn.commit()
    conn.close()



def limpar_logs_antigos():
    """Retention diferenciada por tipo de log:

    - auditoria_admin (compliance/segurança): 180 dias
    - logs_acesso (operacional): 90 dias
    - emails_usuarios_log (debug envio):     90 dias
    - downloads_log (auditoria de extração): 180 dias
    - sync_log (saúde dos jobs):              90 dias  (suficiente para troubleshoot)
    - login_tentativas (rate-limit de login): 1 dia    (efêmero)

    Após limpar, executa PRAGMA optimize em cada DB para manter estatísticas
    atualizadas (D4 — barato, recomendado pelo SQLite).
    """
    agora_local = agora_sp()
    limite_auditoria  = (agora_local - timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
    limite_acesso     = (agora_local - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    limite_emails     = (agora_local - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    limite_downloads  = (agora_local - timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
    limite_sync       = (agora_local - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    limite_tentativas = (agora_local - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

    conn = conectar_users()
    conn.execute('DELETE FROM logs_acesso WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_acesso,))
    conn.execute('DELETE FROM auditoria_admin WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_auditoria,))
    conn.execute(
        'DELETE FROM emails_usuarios_log WHERE atualizado_em IS NOT NULL AND atualizado_em < ?',
        (limite_emails,)
    )
    conn.execute(
        'DELETE FROM login_tentativas WHERE '
        '(primeira_tentativa IS NOT NULL AND primeira_tentativa < ?) '
        'AND (bloqueado_ate IS NULL OR bloqueado_ate < ?)',
        (limite_tentativas, agora())
    )
    conn.execute('PRAGMA optimize')
    conn.commit()
    conn.close()

    conn = conectar_pedidos()
    conn.execute('DELETE FROM downloads_log WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_downloads,))
    conn.execute('DELETE FROM sync_log WHERE executado_em IS NOT NULL AND executado_em < ?', (limite_sync,))
    conn.execute('DELETE FROM pedidos_energy_sync_log WHERE executado_em IS NOT NULL AND executado_em < ?', (limite_sync,))
    conn.execute('DELETE FROM estoque_downloads_log WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_downloads,))
    conn.execute('DELETE FROM estoque_sync_log WHERE executado_em IS NOT NULL AND executado_em < ?', (limite_sync,))
    conn.execute(
        'DELETE FROM historico_downloads_log WHERE data_hora IS NOT NULL AND data_hora < ?',
        (limite_downloads,)
    )
    conn.execute(
        'DELETE FROM historico_sync_log WHERE executado_em IS NOT NULL AND executado_em < ?',
        (limite_sync,)
    )
    conn.execute('PRAGMA optimize')
    conn.commit()
    conn.close()

    try:
        conn = conectar_financeiro()
        conn.execute(
            'DELETE FROM financeiro_downloads_log WHERE data_hora IS NOT NULL AND data_hora < ?',
            (limite_downloads,)
        )
        for t in ('nf_entrada_sync_log', 'nf_saida_sync_log', 'contas_receber_sync_log',
                  'contas_pagar_sync_log', 'mov_bancarios_sync_log',
                  'energy_contas_pagar_sync_log'):
            conn.execute(
                f'DELETE FROM {t} WHERE executado_em IS NOT NULL AND executado_em < ?',
                (limite_sync,)
            )
        conn.execute('PRAGMA optimize')
        conn.commit()
        conn.close()
    except Exception:
        # Financeiro.db pode não existir em ambientes antigos; ignore silenciosamente.
        pass


def _backup_sqlite(origem, destino):
    conn_origem = sqlite3.connect(origem)
    conn_destino = sqlite3.connect(destino)
    with conn_destino:
        conn_origem.backup(conn_destino)
    conn_destino.close()
    conn_origem.close()


def limpar_backups_antigos(dias=7):
    if not os.path.isdir(BACKUPS_DIR):
        return

    limite = agora_sp() - timedelta(days=dias)
    for nome in os.listdir(BACKUPS_DIR):
        caminho = os.path.join(BACKUPS_DIR, nome)
        if not os.path.isfile(caminho) or not nome.endswith('.db'):
            continue

        modificado_em = datetime.fromtimestamp(os.path.getmtime(caminho), SAO_PAULO_TZ)
        if modificado_em < limite:
            os.remove(caminho)


def criar_backup_diario():
    os.makedirs(BACKUPS_DIR, exist_ok=True)

    data_tag = agora_sp().strftime('%Y%m%d')
    users_backup      = os.path.join(BACKUPS_DIR, f'users_{data_tag}.db')
    pedidos_backup    = os.path.join(BACKUPS_DIR, f'pedidos_{data_tag}.db')
    financeiro_backup = os.path.join(BACKUPS_DIR, f'financeiro_{data_tag}.db')

    criou_backup = False

    if os.path.exists(USERS_DB) and not os.path.exists(users_backup):
        _backup_sqlite(USERS_DB, users_backup)
        criou_backup = True

    if os.path.exists(PEDIDOS_DB) and not os.path.exists(pedidos_backup):
        _backup_sqlite(PEDIDOS_DB, pedidos_backup)
        criou_backup = True

    if os.path.exists(FINANCEIRO_DB) and not os.path.exists(financeiro_backup):
        _backup_sqlite(FINANCEIRO_DB, financeiro_backup)
        criou_backup = True


    limpar_backups_antigos()
    return criou_backup
