"""Avisos de melhoria publicados pelo admin para quem tem acesso ao relatório."""
from services.database import agora, conectar_users


def criar_aviso(modulo_id, relatorio_id, titulo, mensagem, criado_por, versao=None):
    conn = conectar_users()
    try:
        cur = conn.execute(
            '''
            INSERT INTO avisos_melhoria (
                modulo_id, relatorio_id, titulo, mensagem, versao,
                criado_em, criado_por, emails_enviados, emails_falha
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, 0)
            ''',
            (modulo_id, relatorio_id, titulo, mensagem, versao, agora(), criado_por),
        )
        aviso_id = cur.lastrowid
        if criado_por:
            conn.execute(
                '''
                INSERT OR IGNORE INTO avisos_melhoria_leitura
                    (aviso_id, usuario_id, lido_em)
                VALUES (?, ?, ?)
                ''',
                (aviso_id, criado_por, agora()),
            )
        conn.commit()
        return aviso_id
    finally:
        conn.close()


def obter_aviso(aviso_id):
    conn = conectar_users()
    try:
        row = conn.execute(
            'SELECT * FROM avisos_melhoria WHERE id = ?',
            (aviso_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def listar_avisos_admin(limite=80):
    conn = conectar_users()
    try:
        rows = conn.execute(
            '''
            SELECT a.id, a.modulo_id, a.relatorio_id, a.titulo, a.mensagem,
                   a.versao, a.criado_em, a.criado_por, a.emails_enviados, a.emails_falha,
                   u.nome AS criado_por_nome
            FROM avisos_melhoria a
            LEFT JOIN usuarios u ON u.id = a.criado_por
            ORDER BY a.id DESC
            LIMIT ?
            ''',
            (limite,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def listar_avisos_nao_lidos(usuario_id):
    conn = conectar_users()
    try:
        rows = conn.execute(
            '''
            SELECT a.id, a.modulo_id, a.relatorio_id, a.titulo, a.mensagem,
                   a.versao, a.criado_em
            FROM avisos_melhoria a
            WHERE NOT EXISTS (
                SELECT 1 FROM avisos_melhoria_leitura r
                WHERE r.aviso_id = a.id AND r.usuario_id = ?
            )
            ORDER BY a.id ASC
            ''',
            (usuario_id,),
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def listar_usuarios_ativos():
    conn = conectar_users()
    try:
        rows = conn.execute(
            '''
            SELECT id, usuario, nome, email, ativo, is_admin, setor_id
            FROM usuarios
            WHERE ativo = 1
            '''
        ).fetchall()
        return [dict(row) for row in rows]
    finally:
        conn.close()


def marcar_aviso_lido(aviso_id, usuario_id):
    conn = conectar_users()
    try:
        conn.execute(
            '''
            INSERT OR IGNORE INTO avisos_melhoria_leitura
                (aviso_id, usuario_id, lido_em)
            VALUES (?, ?, ?)
            ''',
            (aviso_id, usuario_id, agora()),
        )
        conn.commit()
    finally:
        conn.close()


def atualizar_envio_emails(aviso_id, enviados, falhas):
    conn = conectar_users()
    try:
        conn.execute(
            '''
            UPDATE avisos_melhoria
            SET emails_enviados = ?, emails_falha = ?
            WHERE id = ?
            ''',
            (enviados, falhas, aviso_id),
        )
        conn.commit()
    finally:
        conn.close()
