import sqlite3
import os
from datetime import datetime, timedelta

from catalogo_relatorios import listar_relatorios_flat
from time_utils import SAO_PAULO_TZ, agora_sp, agora_sp_str

BASE_DIR = os.path.dirname(__file__)
DATA_DIR = os.path.join(BASE_DIR, 'data')
USERS_DB = os.path.join(DATA_DIR, 'users.db')
PEDIDOS_DB = os.path.join(DATA_DIR, 'pedidos.db')
BACKUPS_DIR = os.path.join(DATA_DIR, 'backups')


def agora():
    return agora_sp_str()


def conectar_users():
    conn = sqlite3.connect(USERS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


def conectar_pedidos():
    conn = sqlite3.connect(PEDIDOS_DB)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    return conn


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
    _popular_permissoes_iniciais(conn)
    _garantir_admin_inicial(conn)
    conn.commit()
    conn.close()

    conn = conectar_pedidos()
    _recriar_estoque_saldos_sem_unique(conn)
    _migrar_estoque_saldos_para_real(conn)
    conn.execute('''
        CREATE TABLE IF NOT EXISTS pedidos (
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
    conn.commit()
    conn.close()


def limpar_logs_antigos():
    agora_local = agora_sp()
    limite_logs_acesso = (agora_local - timedelta(days=90)).strftime('%Y-%m-%d %H:%M:%S')
    limite_downloads = (agora_local - timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
    limite_sync = (agora_local - timedelta(days=180)).strftime('%Y-%m-%d %H:%M:%S')
    limite_tentativas = (agora_local - timedelta(days=1)).strftime('%Y-%m-%d %H:%M:%S')

    conn = conectar_users()
    conn.execute('DELETE FROM logs_acesso WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_logs_acesso,))
    conn.execute('DELETE FROM auditoria_admin WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_logs_acesso,))
    conn.execute(
        'DELETE FROM emails_usuarios_log WHERE atualizado_em IS NOT NULL AND atualizado_em < ?',
        (limite_downloads,)
    )
    conn.execute(
        'DELETE FROM login_tentativas WHERE '
        '(primeira_tentativa IS NOT NULL AND primeira_tentativa < ?) '
        'AND (bloqueado_ate IS NULL OR bloqueado_ate < ?)',
        (limite_tentativas, agora())
    )
    conn.commit()
    conn.close()

    conn = conectar_pedidos()
    conn.execute('DELETE FROM downloads_log WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_downloads,))
    conn.execute('DELETE FROM sync_log WHERE executado_em IS NOT NULL AND executado_em < ?', (limite_sync,))
    conn.execute('DELETE FROM estoque_downloads_log WHERE data_hora IS NOT NULL AND data_hora < ?', (limite_downloads,))
    conn.execute('DELETE FROM estoque_sync_log WHERE executado_em IS NOT NULL AND executado_em < ?', (limite_sync,))
    conn.commit()
    conn.close()


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
    users_backup = os.path.join(BACKUPS_DIR, f'users_{data_tag}.db')
    pedidos_backup = os.path.join(BACKUPS_DIR, f'pedidos_{data_tag}.db')

    criou_backup = False

    if os.path.exists(USERS_DB) and not os.path.exists(users_backup):
        _backup_sqlite(USERS_DB, users_backup)
        criou_backup = True

    if os.path.exists(PEDIDOS_DB) and not os.path.exists(pedidos_backup):
        _backup_sqlite(PEDIDOS_DB, pedidos_backup)
        criou_backup = True

    limpar_backups_antigos()
    return criou_backup
