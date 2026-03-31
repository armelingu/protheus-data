import os
import json
import time
import secrets
import threading
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, redirect, render_template, send_from_directory, Response, session, g
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from catalogo_relatorios import listar_modulos, listar_relatorios_flat, obter_relatorio, chave_relatorio
from database import (
    conectar_users,
    conectar_pedidos,
    criar_tabelas,
    limpar_logs_antigos,
    criar_backup_diario,
    agora,
)
from services.relatorios.compras.pedidos import (
    QUERY_PEDIDOS,
    consolidar_sync_log as consolidar_sync_log_pedidos,
    gerar_csv as gerar_csv_pedidos,
    gerar_excel as gerar_excel_pedidos,
    info_relatorio as info_relatorio_pedidos,
    historico_sync as historico_sync_pedidos,
    sincronizar as sincronizar_pedidos,
    carga_inicial as carga_inicial_pedidos,
    registrar_sync_event as registrar_sync_event_pedidos,
)
from services.relatorios.estoque.saldos import (
    QUERY_ESTOQUE,
    consolidar_sync_log as consolidar_sync_log_estoque,
    gerar_csv as gerar_csv_estoque,
    gerar_excel as gerar_excel_estoque,
    info_relatorio as info_relatorio_estoque,
    historico_sync as historico_sync_estoque,
    sincronizar as sincronizar_estoque,
    carga_inicial as carga_inicial_estoque,
    registrar_sync_event as registrar_sync_event_estoque,
)
from services.email_service import montar_email_acesso, enviar_email
from time_utils import APP_TIMEZONE, agora_sp, parse_db_datetime

load_dotenv()

app = Flask(
    __name__,
    template_folder='templates',
    static_folder='statics',
    static_url_path='/statics'
)

_secret_key = os.getenv('SECRET_KEY')
if not _secret_key:
    raise RuntimeError(
        'Variável de ambiente SECRET_KEY não definida. '
        'Gere uma chave segura e adicione ao .env antes de iniciar.'
    )
app.secret_key = _secret_key
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.getenv('SESSION_LIFETIME_SECONDS', '28800'))  # 8h padrão

SYNC_INTERVALO = 3600
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_MINUTOS = 5
EMAIL_CORPORATIVO_DOMINIO = 'hbraviacao.com.br'
ROTAS_LIBERADAS_TROCA_SENHA = {'/primeiro-acesso', '/api/primeiro-acesso', '/api/logout', '/favicon.ico'}

ultimo_sync_dt = None
sync_timer = None
sync_lock = threading.Lock()
QUERY_PREVIEW_PEDIDOS = QUERY_PEDIDOS.strip() + '\nORDER BY SC7.C7_EMISSAO DESC'
QUERY_PREVIEW_ESTOQUE = QUERY_ESTOQUE.strip()


def _json_dump(valor):
    if valor is None:
        return None
    return json.dumps(valor, ensure_ascii=True, sort_keys=True)


def obter_usuario_por_id(usuario_id):
    conn = conectar_users()
    usuario = conn.execute('SELECT * FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
    conn.close()
    return usuario


def obter_usuario_por_login(login):
    conn = conectar_users()
    usuario = conn.execute('SELECT * FROM usuarios WHERE usuario = ?', (login,)).fetchone()
    conn.close()
    return usuario


def obter_usuario_por_email(email):
    conn = conectar_users()
    usuario = conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
    conn.close()
    return usuario


def obter_ultimo_email_usuario(usuario_id):
    conn = conectar_users()
    linha = conn.execute(
        '''
        SELECT status, tentativas, ultimo_erro, criado_em, enviado_em, atualizado_em
        FROM emails_usuarios_log
        WHERE usuario_id = ? AND tipo = 'acesso'
        ORDER BY id DESC
        LIMIT 1
        ''',
        (usuario_id,)
    ).fetchone()
    conn.close()
    return linha


def normalizar_email_corporativo(email):
    email_normalizado = (email or '').strip().lower()
    if not email_normalizado or '@' not in email_normalizado:
        raise ValueError('Informe um e-mail corporativo válido.')

    login, dominio = email_normalizado.split('@', 1)
    if dominio != EMAIL_CORPORATIVO_DOMINIO:
        raise ValueError(f'Apenas e-mails @{EMAIL_CORPORATIVO_DOMINIO} são permitidos.')
    if not login:
        raise ValueError('O e-mail informado é inválido.')
    return email_normalizado


def gerar_nome_por_login(login):
    partes = [parte for parte in login.replace('-', '.').replace('_', '.').split('.') if parte]
    return ' '.join(parte[:1].upper() + parte[1:] for parte in partes)


def obter_relatorios_catalogo():
    return listar_relatorios_flat()


def obter_chaves_relatorio_validas():
    return {relatorio['chave'] for relatorio in obter_relatorios_catalogo()}


def obter_relatorios_permitidos(usuario_id):
    conn = conectar_users()
    linhas = conn.execute(
        '''
        SELECT modulo_id, relatorio_id
        FROM usuario_permissoes_relatorio
        WHERE usuario_id = ? AND COALESCE(permitido, 1) = 1
        ''',
        (usuario_id,)
    ).fetchall()
    conn.close()
    return {chave_relatorio(linha['modulo_id'], linha['relatorio_id']) for linha in linhas}


def obter_relatorios_permitidos_setor(setor_id):
    if not setor_id:
        return None
    conn = conectar_users()
    linhas = conn.execute(
        'SELECT modulo_id, relatorio_id FROM setor_permissoes_relatorio WHERE setor_id = ?',
        (setor_id,)
    ).fetchall()
    conn.close()
    return {chave_relatorio(l['modulo_id'], l['relatorio_id']) for l in linhas}


def listar_setores(apenas_ativos=True):
    conn = conectar_users()
    if apenas_ativos:
        rows = conn.execute('SELECT * FROM setores WHERE ativo=1 ORDER BY nome').fetchall()
    else:
        rows = conn.execute('SELECT * FROM setores ORDER BY nome').fetchall()
    conn.close()
    return [dict(r) for r in rows]


def obter_setor_por_id(setor_id):
    conn = conectar_users()
    row = conn.execute('SELECT * FROM setores WHERE id=?', (setor_id,)).fetchone()
    conn.close()
    return dict(row) if row else None


def validar_api_token(token_str):
    if not token_str:
        return None
    conn = conectar_users()
    row = conn.execute(
        'SELECT t.id AS token_id, t.usuario_id '
        'FROM api_tokens t WHERE t.token=? AND t.ativo=1',
        (token_str,)
    ).fetchone()
    if not row:
        conn.close()
        return None
    usuario = conn.execute('SELECT * FROM usuarios WHERE id=? AND ativo=1', (row['usuario_id'],)).fetchone()
    if usuario:
        conn.execute('UPDATE api_tokens SET ultimo_uso=? WHERE id=?', (agora(), row['token_id']))
        conn.commit()
    conn.close()
    return usuario


def salvar_permissoes_setor(setor_id, permissoes, conn=None):
    """Salva as permissões de relatório de um setor.

    Aceita um `conn` externo para evitar conflito de lock quando chamado
    dentro de uma transação já aberta (ex: criação de setor).
    Quando `conn` é None, abre e fecha sua própria conexão.
    """
    fechar = conn is None
    if fechar:
        conn = conectar_users()
    conn.execute('DELETE FROM setor_permissoes_relatorio WHERE setor_id=?', (setor_id,))
    for chave in permissoes:
        # chave pode ser 'modulo.relatorio' (ponto) ou 'modulo:relatorio' (dois-pontos)
        sep = '.' if '.' in chave else ':'
        partes = chave.split(sep, 1)
        if len(partes) == 2:
            conn.execute(
                'INSERT OR IGNORE INTO setor_permissoes_relatorio '
                '(setor_id, modulo_id, relatorio_id, criado_em) VALUES (?,?,?,?)',
                (setor_id, partes[0], partes[1], agora())
            )
    if fechar:
        conn.commit()
        conn.close()


def usuario_atual():
    user_id = session.get('usuario_id')
    if not user_id:
        return None

    if hasattr(g, 'current_user'):
        return g.current_user

    usuario = obter_usuario_por_id(user_id)
    g.current_user = usuario
    return usuario


def usuario_para_contexto(usuario):
    if not usuario:
        return None
    return {
        'id': usuario['id'],
        'usuario': usuario['usuario'],
        'nome': usuario['nome'],
        'ativo': bool(usuario['ativo']),
        'is_admin': bool(usuario['is_admin']),
        'is_gerente': bool(usuario['is_gerente'] if 'is_gerente' in usuario.keys() else 0),
        'setor_id': usuario['setor_id'] if 'setor_id' in usuario.keys() else None,
        'deve_trocar_senha': bool(usuario['deve_trocar_senha']),
        'ultimo_login_em': usuario['ultimo_login_em'],
        'criado_em': usuario['criado_em'],
        'desativado_em': usuario['desativado_em'],
    }


def atualizar_sessao_usuario(usuario):
    session['usuario_id']    = usuario['id']
    session['usuario_nome']  = usuario['nome']
    session['usuario_login'] = usuario['usuario']
    session['is_admin']      = int(usuario['is_admin'] or 0)
    session['is_gerente']    = int(usuario['is_gerente'] if 'is_gerente' in usuario.keys() else 0)
    session['setor_id']      = usuario['setor_id'] if 'setor_id' in usuario.keys() else None


def usuario_tem_acesso_relatorio(usuario, modulo_id, relatorio_id):
    if not usuario:
        return False
    if usuario['is_admin']:
        return True
    chave = chave_relatorio(modulo_id, relatorio_id)
    perms_usuario = obter_relatorios_permitidos(usuario['id'])
    usuario_tem = chave in perms_usuario
    setor_id = usuario['setor_id'] if 'setor_id' in usuario.keys() else None
    if setor_id:
        perms_setor = obter_relatorios_permitidos_setor(setor_id)
        return usuario_tem and chave in perms_setor
    return usuario_tem


def filtrar_modulos_usuario(usuario):
    modulos_filtrados = []
    if usuario['is_admin']:
        permissoes_usuario = None
        permissoes_setor   = None
    else:
        permissoes_usuario = obter_relatorios_permitidos(usuario['id'])
        setor_id = usuario['setor_id'] if 'setor_id' in usuario.keys() else None
        permissoes_setor = obter_relatorios_permitidos_setor(setor_id) if setor_id else None

    for modulo in listar_modulos():
        relatorios = []
        for relatorio in modulo['relatorios']:
            if usuario['is_admin']:
                relatorios.append(relatorio)
            else:
                chave = chave_relatorio(modulo['id'], relatorio['id'])
                tem_usuario = chave in permissoes_usuario
                tem_setor   = permissoes_setor is None or chave in permissoes_setor
                if tem_usuario and tem_setor:
                    relatorios.append(relatorio)
        if relatorios:
            modulos_filtrados.append({**modulo, 'relatorios': relatorios})
    return modulos_filtrados


def contexto_auth(page_title):
    usuario = usuario_atual()
    return {
        'page_title': page_title,
        'modulos_menu': filtrar_modulos_usuario(usuario) if usuario else [],
        'current_path': request.path,
        'usuario_atual': usuario_para_contexto(usuario),
    }


def registrar_auditoria_admin(
    acao,
    usuario_afetado_id=None,
    usuario_afetado_login=None,
    detalhe=None,
    antes=None,
    depois=None,
):
    conn = conectar_users()
    conn.execute(
        '''
        INSERT INTO auditoria_admin (
            admin_usuario_id,
            admin_usuario_nome,
            acao,
            usuario_afetado_id,
            usuario_afetado_login,
            detalhes_antes,
            detalhes_depois,
            detalhe,
            ip,
            data_hora
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            session.get('usuario_id'),
            session.get('usuario_nome'),
            acao,
            usuario_afetado_id,
            usuario_afetado_login,
            _json_dump(antes),
            _json_dump(depois),
            detalhe,
            request.remote_addr,
            agora(),
        )
    )
    conn.commit()
    conn.close()


def resposta_sem_acesso(mensagem='Você não tem permissão para acessar este conteúdo.'):
    if request.path.startswith('/api/'):
        return jsonify({'erro': mensagem}), 403
    return render_template(
        'auth/acesso_negado.html',
        mensagem=mensagem,
        **contexto_auth('ProtheusData - Acesso negado')
    ), 403


def login_requerido(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        usuario = usuario_atual()
        if not usuario:
            session.clear()
            if request.path.startswith('/api/'):
                return jsonify({'erro': 'Não autenticado'}), 401
            return redirect('/login')
        if not usuario['ativo']:
            session.clear()
            if request.path.startswith('/api/'):
                return jsonify({'erro': 'Usuário desativado.'}), 403
            return redirect('/login')
        if usuario['deve_trocar_senha'] and request.path not in ROTAS_LIBERADAS_TROCA_SENHA:
            if request.path.startswith('/api/'):
                return jsonify({
                    'erro': 'Troca de senha obrigatória.',
                    'redirect': '/primeiro-acesso',
                }), 403
            return redirect('/primeiro-acesso')
        return f(*args, **kwargs)
    return wrapper


def admin_requerido(f):
    @wraps(f)
    @login_requerido
    def wrapper(*args, **kwargs):
        usuario = usuario_atual()
        if not usuario or not usuario['is_admin']:
            return resposta_sem_acesso('Somente superadmins podem acessar esta área.')
        return f(*args, **kwargs)
    return wrapper


def gerente_requerido(f):
    @wraps(f)
    @login_requerido
    def wrapper(*args, **kwargs):
        usuario = usuario_atual()
        if not usuario or not (usuario['is_admin'] or
                               (usuario['is_gerente'] if 'is_gerente' in usuario.keys() else 0)):
            return resposta_sem_acesso('Somente gerentes ou admins podem acessar esta área.')
        return f(*args, **kwargs)
    return wrapper


def acesso_relatorio_requerido(modulo_id, relatorio_id):
    def decorator(f):
        @wraps(f)
        @login_requerido
        def wrapper(*args, **kwargs):
            if not usuario_tem_acesso_relatorio(usuario_atual(), modulo_id, relatorio_id):
                return resposta_sem_acesso('Seu usuário não possui permissão para este relatório.')
            return f(*args, **kwargs)
        return wrapper
    return decorator


def registrar_log(acao, usuario_id=None, usuario_nome=None):
    conn = conectar_users()
    conn.execute(
        'INSERT INTO logs_acesso (usuario_id, usuario_nome, acao, ip, data_hora) VALUES (?, ?, ?, ?, ?)',
        (usuario_id, usuario_nome, acao, request.remote_addr, agora())
    )
    conn.commit()
    conn.close()


def serializar_data(data):
    if not data:
        return None
    return parse_db_datetime(data).strftime('%d/%m/%Y %H:%M')


def contar_outros_admins_ativos(usuario_id):
    conn = conectar_users()
    total = conn.execute(
        '''
        SELECT COUNT(*) AS total
        FROM usuarios
        WHERE COALESCE(is_admin, 0) = 1
          AND COALESCE(ativo, 1) = 1
          AND id <> ?
        ''',
        (usuario_id,)
    ).fetchone()['total']
    conn.close()
    return total


def salvar_permissoes_usuario(conn, usuario_id, permissoes):
    conn.execute('DELETE FROM usuario_permissoes_relatorio WHERE usuario_id = ?', (usuario_id,))
    if not permissoes:
        return

    agora_atual = agora()
    valores = []
    for chave in sorted(permissoes):
        modulo_id, relatorio_id = chave.split('.', 1)
        valores.append((usuario_id, modulo_id, relatorio_id, 1, agora_atual, agora_atual))

    conn.executemany(
        '''
        INSERT INTO usuario_permissoes_relatorio
        (usuario_id, modulo_id, relatorio_id, permitido, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        valores
    )


def listar_usuarios_admin():
    conn = conectar_users()
    usuarios = conn.execute(
        '''
        SELECT u.id, u.usuario, u.nome, u.email, u.ativo, u.is_admin,
               u.deve_trocar_senha, u.criado_em, u.ultimo_login_em, u.desativado_em,
               COALESCE(u.pode_ver_query, 0) AS pode_ver_query,
               COALESCE(u.setor_id, NULL) AS setor_id,
               COALESCE(u.is_gerente, 0) AS is_gerente,
               s.nome AS setor_nome
        FROM usuarios u
        LEFT JOIN setores s ON s.id = u.setor_id
        ORDER BY LOWER(u.nome), LOWER(u.usuario)
        '''
    ).fetchall()
    permissoes = conn.execute(
        '''
        SELECT usuario_id, modulo_id, relatorio_id
        FROM usuario_permissoes_relatorio
        WHERE COALESCE(permitido, 1) = 1
        '''
    ).fetchall()
    emails = conn.execute(
        '''
        SELECT usuario_id, status, tentativas, ultimo_erro, criado_em, enviado_em, atualizado_em
        FROM emails_usuarios_log
        WHERE tipo = 'acesso'
        ORDER BY id DESC
        '''
    ).fetchall()
    conn.close()

    permissoes_por_usuario = {}
    for linha in permissoes:
        permissoes_por_usuario.setdefault(linha['usuario_id'], []).append(
            chave_relatorio(linha['modulo_id'], linha['relatorio_id'])
        )

    emails_por_usuario = {}
    for linha in emails:
        if linha['usuario_id'] in emails_por_usuario:
            continue
        emails_por_usuario[linha['usuario_id']] = linha

    usuarios_serializados = []
    for usuario in usuarios:
        usuario_permissoes = sorted(permissoes_por_usuario.get(usuario['id'], []))
        email_log = emails_por_usuario.get(usuario['id'])
        usuarios_serializados.append({
            'id': usuario['id'],
            'usuario': usuario['usuario'],
            'nome': usuario['nome'],
            'email': usuario['email'],
            'ativo': bool(usuario['ativo']),
            'is_admin': bool(usuario['is_admin']),
            'deve_trocar_senha': bool(usuario['deve_trocar_senha']),
            'criado_em': serializar_data(usuario['criado_em']),
            'ultimo_login_em': serializar_data(usuario['ultimo_login_em']),
            'desativado_em': serializar_data(usuario['desativado_em']),
            'pode_ver_query': bool(usuario['pode_ver_query']),
            'setor_id': usuario['setor_id'],
            'setor_nome': usuario['setor_nome'],
            'is_gerente': bool(usuario['is_gerente']),
            'permissoes': usuario_permissoes,
            'email_acesso': {
                'status': email_log['status'] if email_log else 'nunca_enviado',
                'tentativas': email_log['tentativas'] if email_log else 0,
                'ultimo_erro': email_log['ultimo_erro'] if email_log else None,
                'enviado_em': serializar_data(email_log['enviado_em']) if email_log else None,
                'atualizado_em': serializar_data(email_log['atualizado_em']) if email_log else None,
            }
        })

    return usuarios_serializados


def listar_logs_acesso(limit=80):
    conn = conectar_users()
    linhas = conn.execute(
        '''
        SELECT usuario_nome, acao, ip, data_hora
        FROM logs_acesso
        ORDER BY id DESC
        LIMIT ?
        ''',
        (limit,)
    ).fetchall()
    conn.close()
    return [
        {
            'usuario_nome': linha['usuario_nome'] or 'Sistema',
            'acao': linha['acao'],
            'ip': linha['ip'] or '--',
            'data_hora': serializar_data(linha['data_hora']) or '--',
        }
        for linha in linhas
    ]


def listar_auditoria_admin(limit=120, usuario_id=None, acao=None):
    conn = conectar_users()
    sql = (
        'SELECT admin_usuario_nome, acao, usuario_afetado_login, detalhe, ip, data_hora '
        'FROM auditoria_admin WHERE 1=1'
    )
    params = []

    if usuario_id:
        sql += ' AND usuario_afetado_id = ?'
        params.append(usuario_id)
    if acao:
        sql += ' AND acao = ?'
        params.append(acao)

    sql += ' ORDER BY id DESC LIMIT ?'
    params.append(limit)

    linhas = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return [
        {
            'admin_usuario_nome': linha['admin_usuario_nome'] or 'Sistema',
            'acao': linha['acao'],
            'usuario_afetado_login': linha['usuario_afetado_login'] or '--',
            'detalhe': linha['detalhe'] or '',
            'ip': linha['ip'] or '--',
            'data_hora': serializar_data(linha['data_hora']) or '--',
        }
        for linha in linhas
    ]


def registrar_email_usuario_log(usuario_id, email_destino, payload, resultado):
    conn = conectar_users()
    linha_anterior = conn.execute(
        '''
        SELECT tentativas
        FROM emails_usuarios_log
        WHERE usuario_id = ? AND tipo = 'acesso'
        ORDER BY id DESC
        LIMIT 1
        ''',
        (usuario_id,)
    ).fetchone()
    tentativas = (linha_anterior['tentativas'] if linha_anterior else 0) + 1
    agora_atual = agora()
    conn.execute(
        '''
        INSERT INTO emails_usuarios_log (
            usuario_id,
            email_destino,
            tipo,
            status,
            tentativas,
            ultimo_erro,
            payload,
            criado_em,
            enviado_em,
            atualizado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            usuario_id,
            email_destino,
            'acesso',
            'enviado' if resultado['ok'] else 'falha',
            tentativas,
            resultado['error'],
            _json_dump(payload),
            agora_atual,
            agora_atual if resultado['ok'] else None,
            agora_atual,
        )
    )
    conn.commit()
    conn.close()
    return {
        'status': 'enviado' if resultado['ok'] else 'falha',
        'tentativas': tentativas,
        'erro': resultado['error'],
    }


def tentar_enviar_email_acesso_usuario(usuario):
    payload = montar_email_acesso(
        usuario['nome'],
        usuario['email'],
        usuario['usuario'],
        request.host_url.rstrip('/'),
    )
    resultado = enviar_email(payload)
    log = registrar_email_usuario_log(usuario['id'], usuario['email'], payload, resultado)

    if resultado['ok']:
        registrar_auditoria_admin(
            'email_acesso_enviado',
            usuario_afetado_id=usuario['id'],
            usuario_afetado_login=usuario['usuario'],
            detalhe='E-mail de acesso enviado com sucesso.',
            depois={'email': usuario['email'], 'tentativas': log['tentativas']},
        )
    else:
        registrar_auditoria_admin(
            'email_acesso_falhou',
            usuario_afetado_id=usuario['id'],
            usuario_afetado_login=usuario['usuario'],
            detalhe=f'Falha ao enviar e-mail de acesso: {resultado["error"]}',
            depois={'email': usuario['email'], 'tentativas': log['tentativas']},
        )

    return {
        'ok': resultado['ok'],
        'error': resultado['error'],
        'payload': payload,
        'status': log['status'],
        'tentativas': log['tentativas'],
    }


def verificar_bloqueio(ip):
    conn = conectar_users()
    row = conn.execute(
        'SELECT tentativas, bloqueado_ate, primeira_tentativa FROM login_tentativas WHERE ip = ?',
        (ip,)
    ).fetchone()
    conn.close()

    if not row:
        return False

    if row['bloqueado_ate']:
        bloqueado = parse_db_datetime(row['bloqueado_ate'])
        if agora_sp() < bloqueado:
            return True
        limpar_tentativas(ip)
        return False

    primeira = parse_db_datetime(row['primeira_tentativa'])
    if agora_sp() - primeira > timedelta(minutes=BLOQUEIO_MINUTOS):
        limpar_tentativas(ip)
        return False

    return False


def registrar_tentativa(ip):
    conn = conectar_users()
    row = conn.execute(
        'SELECT id, tentativas, primeira_tentativa FROM login_tentativas WHERE ip = ?',
        (ip,)
    ).fetchone()

    if row:
        primeira = parse_db_datetime(row['primeira_tentativa'])
        if agora_sp() - primeira > timedelta(minutes=BLOQUEIO_MINUTOS):
            conn.execute('DELETE FROM login_tentativas WHERE ip = ?', (ip,))
            conn.execute(
                'INSERT INTO login_tentativas (ip, primeira_tentativa) VALUES (?, ?)',
                (ip, agora())
            )
        else:
            novas = row['tentativas'] + 1
            bloqueio = None
            if novas >= MAX_TENTATIVAS_LOGIN:
                bloqueio = (agora_sp() + timedelta(minutes=BLOQUEIO_MINUTOS)).strftime('%Y-%m-%d %H:%M:%S')
            conn.execute(
                'UPDATE login_tentativas SET tentativas = ?, bloqueado_ate = ? WHERE ip = ?',
                (novas, bloqueio, ip)
            )
    else:
        conn.execute(
            'INSERT INTO login_tentativas (ip, primeira_tentativa) VALUES (?, ?)',
            (ip, agora())
        )

    conn.commit()
    conn.close()


def limpar_tentativas(ip):
    conn = conectar_users()
    conn.execute('DELETE FROM login_tentativas WHERE ip = ?', (ip,))
    conn.commit()
    conn.close()


def calcular_proximo_sync():
    return calcular_proximo_sync_dt().strftime('%d/%m/%Y %H:%M')


def calcular_proximo_sync_dt():
    agora_local = agora_sp().replace(second=0, microsecond=0)
    hora_atual = agora_local.hour

    if hora_atual < 8:
        return agora_local.replace(hour=8, minute=0)

    if hora_atual >= 19:
        return (agora_local + timedelta(days=1)).replace(hour=8, minute=0)

    proxima_hora_cheia = (agora_local + timedelta(hours=1)).replace(minute=0)
    if proxima_hora_cheia.hour >= 19:
        return (agora_local + timedelta(days=1)).replace(hour=8, minute=0)
    return proxima_hora_cheia


def agendar_proximo_sync():
    global sync_timer

    proximo = calcular_proximo_sync_dt()
    segundos = max(1, int((proximo - agora_sp()).total_seconds()))

    timer = threading.Timer(segundos, rotina_sync)
    timer.daemon = True
    timer.start()
    sync_timer = timer


def rotina_sync():
    global ultimo_sync_dt
    hora_atual = agora_sp().hour
    if 8 <= hora_atual < 19:
        if not sync_lock.acquire(blocking=False):
            print('[SYNC] Sincronização já em andamento. Pulando execução automática.')
        else:
            MAX_TENTATIVAS_SYNC = 3
            ultimo_erro = None
            try:
                for tentativa in range(1, MAX_TENTATIVAS_SYNC + 1):
                    try:
                        novos_pedidos = sincronizar_pedidos()
                        alterados_estoque = sincronizar_estoque()
                        ultimo_sync_dt = agora_sp()
                        if criar_backup_diario():
                            print('[BACKUP] Backup diário criado com sucesso.')
                        print(f'[SYNC] Pedidos sincronizados. {novos_pedidos} registro(s) novo(s).')
                        print(f'[SYNC] Estoque sincronizado. {alterados_estoque} registro(s) alterado(s).')
                        ultimo_erro = None
                        break
                    except Exception as e:
                        ultimo_erro = e
                        if tentativa < MAX_TENTATIVAS_SYNC:
                            espera = 60 * tentativa
                            print(f'[SYNC] Tentativa {tentativa}/{MAX_TENTATIVAS_SYNC} falhou: {e}. '
                                  f'Aguardando {espera}s antes de tentar novamente.')
                            time.sleep(espera)
                        else:
                            print(f'[SYNC] Todas as {MAX_TENTATIVAS_SYNC} tentativas falharam. Último erro: {e}')
                if ultimo_erro is not None:
                    registrar_sync_event_pedidos(0, 'erro', str(ultimo_erro)[:180])
                    registrar_sync_event_estoque(0, 'erro', str(ultimo_erro)[:180])
            finally:
                sync_lock.release()
    else:
        print(f'[SYNC] Fora do horário (08h-19h). Atual: {hora_atual}h. Pulando.')

    limpar_logs_antigos()
    agendar_proximo_sync()


@app.route('/favicon.ico')
@app.route('/favicon.png')
def favicon():
    return send_from_directory(
        os.path.join(app.root_path, 'statics'),
        'favicon.png',
        mimetype='image/png'
    )


@app.route('/')
def index():
    return redirect('/login')


@app.route('/login')
def pagina_login():
    usuario = usuario_atual()
    if usuario:
        if usuario['deve_trocar_senha']:
            return redirect('/primeiro-acesso')
        return redirect('/relatorios')
    return send_from_directory('templates/login', 'login.html')


@app.route('/primeiro-acesso')
@login_requerido
def pagina_primeiro_acesso():
    usuario = usuario_atual()
    if not usuario['deve_trocar_senha']:
        return redirect('/relatorios')
    return render_template(
        'auth/primeiro_acesso.html',
        usuario_atual=usuario_para_contexto(usuario),
        page_title='ProtheusData - Atualizar senha'
    )


@app.route('/relatorios')
@login_requerido
def pagina_relatorios():
    return render_template(
        'relatorios/home.html',
        **contexto_auth('ProtheusData - Relatórios')
    )


@app.route('/consulta')
@login_requerido
def pagina_consulta():
    return redirect('/relatorios/compras/pedidos')


@app.route('/relatorios/compras/pedidos')
@acesso_relatorio_requerido('compras', 'pedidos')
def pagina_relatorio_compras_pedidos():
    modulo, relatorio = obter_relatorio('compras', 'pedidos')
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and (usuario['is_admin'] or usuario['pode_ver_query']))
    return render_template(
        'relatorios/compras_pedidos.html',
        modulo_ativo=modulo,
        relatorio_ativo=relatorio,
        query_preview=QUERY_PREVIEW_PEDIDOS if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Pedidos de Compra')
    )


@app.route('/relatorios/estoque/saldos')
@acesso_relatorio_requerido('estoque', 'saldos')
def pagina_relatorio_estoque_saldos():
    modulo, relatorio = obter_relatorio('estoque', 'saldos')
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and (usuario['is_admin'] or usuario['pode_ver_query']))
    return render_template(
        'relatorios/estoque_saldos.html',
        modulo_ativo=modulo,
        relatorio_ativo=relatorio,
        query_preview=QUERY_PREVIEW_ESTOQUE if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Saldo em Estoque')
    )


@app.route('/admin/usuarios')
@admin_requerido
def pagina_admin_usuarios():
    return render_template(
        'admin/usuarios.html',
        relatorios_catalogo=obter_relatorios_catalogo(),
        **contexto_auth('ProtheusData - Usuários')
    )


@app.route('/admin/setores')
@admin_requerido
def pagina_admin_setores():
    return render_template(
        'admin/setores.html',
        relatorios_catalogo=obter_relatorios_catalogo(),
        **contexto_auth('ProtheusData - Setores')
    )


@app.route('/admin/auditoria')
@admin_requerido
def pagina_admin_auditoria():
    return render_template(
        'admin/auditoria.html',
        **contexto_auth('ProtheusData - Auditoria')
    )


@app.route('/gerente')
@gerente_requerido
def pagina_gerente():
    usuario = usuario_atual()
    setor_id = usuario['setor_id'] if 'setor_id' in usuario.keys() else None
    if usuario['is_admin'] and not setor_id:
        return redirect('/admin/usuarios')
    setor = obter_setor_por_id(setor_id) if setor_id else None
    return render_template(
        'gerente/meu_setor.html',
        setor=setor,
        relatorios_catalogo=obter_relatorios_catalogo(),
        **contexto_auth('ProtheusData - Meu Setor')
    )


# ── Perfil / Tokens de API ───────────────────────────────────────────────────

@app.route('/meu-perfil')
@login_requerido
def pagina_perfil():
    usuario = usuario_atual()
    pode_pedidos = usuario_tem_acesso_relatorio(usuario, 'compras', 'pedidos')
    pode_estoque = usuario_tem_acesso_relatorio(usuario, 'estoque', 'saldos')
    return render_template(
        'perfil/index.html',
        pode_pedidos=pode_pedidos,
        pode_estoque=pode_estoque,
        **contexto_auth('ProtheusData - Meu Perfil')
    )


@app.route('/api/meu-perfil/tokens', methods=['GET'])
@login_requerido
def api_listar_tokens():
    uid = session['usuario_id']
    conn = conectar_users()
    tokens = conn.execute(
        'SELECT id, nome, criado_em, ultimo_uso FROM api_tokens '
        'WHERE usuario_id=? AND ativo=1 ORDER BY criado_em DESC',
        (uid,)
    ).fetchall()
    conn.close()
    return jsonify({'tokens': [
        {'id': t['id'], 'nome': t['nome'],
         'criado_em': serializar_data(t['criado_em']),
         'ultimo_uso': serializar_data(t['ultimo_uso']) or 'Nunca utilizado'}
        for t in tokens
    ]})


@app.route('/api/meu-perfil/tokens', methods=['POST'])
@login_requerido
def api_criar_token():
    dados = request.get_json() or {}
    nome = (dados.get('nome') or '').strip()
    if not nome:
        return jsonify({'erro': 'Informe um nome para identificar o token.'}), 400
    uid = session['usuario_id']
    conn = conectar_users()
    total = conn.execute(
        'SELECT COUNT(*) FROM api_tokens WHERE usuario_id=? AND ativo=1', (uid,)
    ).fetchone()[0]
    if total >= 5:
        conn.close()
        return jsonify({'erro': 'Limite de 5 tokens ativos por usuário atingido. Revogue um antes de criar novo.'}), 409
    token = secrets.token_urlsafe(32)
    conn.execute(
        'INSERT INTO api_tokens (usuario_id, nome, token, criado_em, ativo) VALUES (?,?,?,?,1)',
        (uid, nome, token, agora())
    )
    conn.commit()
    conn.close()
    return jsonify({'mensagem': f'Token "{nome}" criado.', 'token': token}), 201


@app.route('/api/meu-perfil/tokens/<int:token_id>', methods=['DELETE'])
@login_requerido
def api_revogar_token(token_id):
    uid = session['usuario_id']
    conn = conectar_users()
    conn.execute(
        'UPDATE api_tokens SET ativo=0 WHERE id=? AND usuario_id=?', (token_id, uid)
    )
    conn.commit()
    conn.close()
    return jsonify({'mensagem': 'Token revogado com sucesso.'}), 200


# ── OData endpoints (Power BI / Excel) ───────────────────────────────────────

def _token_da_request():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return request.args.get('token') or ''


def _odata_response(entity_name, rows, colunas=None):
    if colunas:
        dados = [{c: r[c] for c in colunas if c in r.keys()} for r in rows]
    else:
        dados = [dict(r) for r in rows]
    payload = {
        '@odata.context': request.url_root.rstrip('/') + f'/odata/$metadata#{entity_name}',
        'value': dados,
    }
    return Response(
        json.dumps(payload, ensure_ascii=False, default=str),
        mimetype='application/json;odata.metadata=minimal',
        headers={'OData-Version': '4.0'}
    )


@app.route('/odata/pedidos')
def odata_pedidos():
    usuario = validar_api_token(_token_da_request())
    if not usuario:
        return Response(
            json.dumps({'error': 'Token inválido ou expirado.'}),
            status=401, mimetype='application/json'
        )
    if not usuario_tem_acesso_relatorio(usuario, 'compras', 'pedidos'):
        return Response(
            json.dumps({'error': 'Sem permissão para o relatório de Pedidos de Compra.'}),
            status=403, mimetype='application/json'
        )
    conn = conectar_pedidos()
    rows = conn.execute('SELECT * FROM pedidos ORDER BY data_emissao DESC, pedido_compra').fetchall()
    conn.close()
    colunas = ['filial', 'pedido_compra', 'item', 'produto', 'descricao_produto',
               'quantidade', 'cod_fornecedor', 'fornecedor', 'deposito_estoque', 'data_emissao']
    return _odata_response('Pedidos', rows, colunas)


@app.route('/odata/estoque')
def odata_estoque():
    usuario = validar_api_token(_token_da_request())
    if not usuario:
        return Response(
            json.dumps({'error': 'Token inválido ou expirado.'}),
            status=401, mimetype='application/json'
        )
    if not usuario_tem_acesso_relatorio(usuario, 'estoque', 'saldos'):
        return Response(
            json.dumps({'error': 'Sem permissão para o relatório de Estoque.'}),
            status=403, mimetype='application/json'
        )
    conn = conectar_pedidos()
    rows = conn.execute('SELECT * FROM estoque_saldos ORDER BY produto').fetchall()
    conn.close()
    colunas = ['produto', 'descricao_produto', 'filial', 'armazem',
               'saldo_atual', 'qtde_pedidos_venda', 'qtde_reserva', 'saldo_disponivel']
    return _odata_response('Estoque', rows, colunas)


# ── API Admin: Setores ────────────────────────────────────────────────────────

@app.route('/api/admin/setores', methods=['GET'])
@admin_requerido
def api_admin_listar_setores():
    conn = conectar_users()
    setores = conn.execute('SELECT * FROM setores ORDER BY nome').fetchall()
    perms = conn.execute('SELECT * FROM setor_permissoes_relatorio').fetchall()
    contagens = conn.execute(
        'SELECT setor_id, COUNT(*) AS total FROM usuarios WHERE ativo=1 GROUP BY setor_id'
    ).fetchall()
    gerentes = conn.execute(
        'SELECT setor_id, usuario, nome FROM usuarios WHERE is_gerente=1 AND ativo=1'
    ).fetchall()
    conn.close()

    perms_por_setor = {}
    for p in perms:
        perms_por_setor.setdefault(p['setor_id'], []).append(
            chave_relatorio(p['modulo_id'], p['relatorio_id'])
        )
    contagem_por_setor = {r['setor_id']: r['total'] for r in contagens}
    gerentes_por_setor = {}
    for g in gerentes:
        gerentes_por_setor.setdefault(g['setor_id'], []).append(
            {'usuario': g['usuario'], 'nome': g['nome']}
        )

    resultado = []
    for s in setores:
        sid = s['id']
        resultado.append({
            'id': sid,
            'nome': s['nome'],
            'descricao': s['descricao'],
            'ativo': bool(s['ativo']),
            'permissoes': sorted(perms_por_setor.get(sid, [])),
            'total_usuarios': contagem_por_setor.get(sid, 0),
            'gerentes': gerentes_por_setor.get(sid, []),
        })
    return jsonify({'setores': resultado})


@app.route('/api/admin/setores', methods=['POST'])
@admin_requerido
def api_admin_criar_setor():
    dados = request.get_json() or {}
    nome = (dados.get('nome') or '').strip()
    descricao = (dados.get('descricao') or '').strip()
    permissoes = set(dados.get('permissoes') or [])
    if not nome:
        return jsonify({'erro': 'Nome do setor é obrigatório.'}), 400
    relatorios_validos = obter_chaves_relatorio_validas()
    if permissoes - relatorios_validos:
        return jsonify({'erro': 'Há permissões inválidas.'}), 400
    conn = conectar_users()
    try:
        cursor = conn.execute(
            'INSERT INTO setores (nome, descricao, ativo, criado_em) VALUES (?,?,1,?)',
            (nome, descricao or None, agora())
        )
        setor_id = cursor.lastrowid
        # Passa conn para evitar segunda conexão com transação aberta (database is locked)
        salvar_permissoes_setor(setor_id, permissoes, conn=conn)
        conn.commit()
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        conn.close()
        if 'UNIQUE' in str(exc):
            return jsonify({'erro': 'Já existe um setor com esse nome.'}), 409
        return jsonify({'erro': f'Erro ao criar setor: {exc}'}), 500
    conn.close()
    registrar_auditoria_admin('setor_criado', detalhe=f'Setor "{nome}" criado.')
    return jsonify({'mensagem': f'Setor "{nome}" criado com sucesso.'}), 201


@app.route('/api/admin/setores/<int:setor_id>', methods=['DELETE'])
@admin_requerido
def api_admin_excluir_setor(setor_id):
    setor = obter_setor_por_id(setor_id)
    if not setor:
        return jsonify({'erro': 'Setor não encontrado.'}), 404
    conn = conectar_users()
    total_usuarios = conn.execute(
        'SELECT COUNT(*) FROM usuarios WHERE setor_id=? AND ativo=1', (setor_id,)
    ).fetchone()[0]
    conn.close()
    if total_usuarios > 0:
        return jsonify({
            'erro': f'Este setor possui {total_usuarios} usuário(s) ativo(s). '
                    'Remova-os do setor antes de excluir.'
        }), 409
    conn = conectar_users()
    conn.execute('DELETE FROM setor_permissoes_relatorio WHERE setor_id=?', (setor_id,))
    conn.execute('DELETE FROM setores WHERE id=?', (setor_id,))
    conn.commit()
    conn.close()
    registrar_auditoria_admin('setor_excluido', detalhe=f'Setor "{setor["nome"]}" excluído.')
    return jsonify({'mensagem': f'Setor "{setor["nome"]}" excluído com sucesso.'}), 200


@app.route('/api/admin/setores/<int:setor_id>/configuracao', methods=['POST'])
@admin_requerido
def api_admin_configurar_setor(setor_id):
    dados = request.get_json() or {}
    nome = (dados.get('nome') or '').strip()
    descricao = (dados.get('descricao') or '').strip()
    permissoes = set(dados.get('permissoes') or [])
    ativo = bool(dados.get('ativo', True))
    setor = obter_setor_por_id(setor_id)
    if not setor:
        return jsonify({'erro': 'Setor não encontrado.'}), 404
    relatorios_validos = obter_chaves_relatorio_validas()
    if permissoes - relatorios_validos:
        return jsonify({'erro': 'Há permissões inválidas.'}), 400
    conn = conectar_users()
    conn.execute(
        'UPDATE setores SET nome=?, descricao=?, ativo=? WHERE id=?',
        (nome or setor['nome'], descricao or None, 1 if ativo else 0, setor_id)
    )
    salvar_permissoes_setor(setor_id, permissoes, conn=conn)
    conn.commit()
    conn.close()
    registrar_auditoria_admin('setor_atualizado', detalhe=f'Setor id={setor_id} atualizado.')
    return jsonify({'mensagem': 'Setor atualizado com sucesso.'}), 200


# ── API Gerente ───────────────────────────────────────────────────────────────

@app.route('/api/gerente/usuarios', methods=['GET'])
@gerente_requerido
def api_gerente_listar_usuarios():
    usuario = usuario_atual()
    setor_id = usuario['setor_id'] if 'setor_id' in usuario.keys() else None
    if not setor_id and not usuario['is_admin']:
        return jsonify({'erro': 'Você não está vinculado a um setor.'}), 400

    conn = conectar_users()
    if setor_id:
        usuarios = conn.execute(
            '''SELECT id, usuario, nome, email, ativo, deve_trocar_senha,
                      COALESCE(pode_ver_query,0) AS pode_ver_query,
                      ultimo_login_em
               FROM usuarios WHERE setor_id=? AND COALESCE(is_admin,0)=0
               ORDER BY LOWER(nome)''',
            (setor_id,)
        ).fetchall()
    else:
        usuarios = []
    perms = conn.execute(
        'SELECT usuario_id, modulo_id, relatorio_id FROM usuario_permissoes_relatorio '
        'WHERE COALESCE(permitido,1)=1'
    ).fetchall()
    conn.close()

    perms_setor = obter_relatorios_permitidos_setor(setor_id) or set()
    perms_por_usuario = {}
    for p in perms:
        perms_por_usuario.setdefault(p['usuario_id'], []).append(
            chave_relatorio(p['modulo_id'], p['relatorio_id'])
        )

    resultado = []
    for u in usuarios:
        resultado.append({
            'id': u['id'],
            'usuario': u['usuario'],
            'nome': u['nome'],
            'email': u['email'],
            'ativo': bool(u['ativo']),
            'deve_trocar_senha': bool(u['deve_trocar_senha']),
            'ultimo_login_em': serializar_data(u['ultimo_login_em']),
            'permissoes': sorted(perms_por_usuario.get(u['id'], [])),
            'permissoes_setor': sorted(perms_setor),
        })
    setor = obter_setor_por_id(setor_id)
    return jsonify({'usuarios': resultado, 'setor': setor})


@app.route('/api/gerente/usuarios/<int:usuario_id>/configuracao', methods=['POST'])
@gerente_requerido
def api_gerente_configurar_usuario(usuario_id):
    gerente = usuario_atual()
    setor_id = gerente['setor_id'] if 'setor_id' in gerente.keys() else None
    if not setor_id:
        return jsonify({'erro': 'Você não está vinculado a um setor.'}), 400

    conn = conectar_users()
    alvo = conn.execute('SELECT * FROM usuarios WHERE id=?', (usuario_id,)).fetchone()
    conn.close()
    if not alvo or alvo['setor_id'] != setor_id:
        return jsonify({'erro': 'Usuário não encontrado neste setor.'}), 404

    dados = request.get_json() or {}
    permissoes = set(dados.get('permissoes') or [])
    perms_setor = obter_relatorios_permitidos_setor(setor_id)
    if perms_setor is not None and not permissoes.issubset(perms_setor):
        return jsonify({'erro': 'Permissão fora do escopo do setor.'}), 400

    conn = conectar_users()
    salvar_permissoes_usuario(conn, usuario_id, permissoes)
    conn.commit()
    conn.close()
    registrar_auditoria_admin(
        'gerente_atualizou_permissoes',
        usuario_afetado_id=usuario_id,
        usuario_afetado_login=alvo['usuario'],
        detalhe='Permissões ajustadas pelo gerente do setor.',
    )
    return jsonify({'mensagem': 'Permissões atualizadas.'}), 200



@app.route('/cadastro')
def pagina_cadastro():
    return redirect('/login')


@app.route('/api/login', methods=['POST'])
def api_login():
    ip = request.remote_addr

    if verificar_bloqueio(ip):
        return jsonify({'erro': f'Muitas tentativas. Aguarde {BLOQUEIO_MINUTOS} minutos.'}), 429

    dados = request.get_json()
    if not dados:
        return jsonify({'erro': 'Dados inválidos'}), 400

    usuario = dados.get('usuario', '').strip()
    senha = dados.get('senha', '')

    if not usuario or not senha:
        return jsonify({'erro': 'Preencha todos os campos'}), 400

    user = obter_usuario_por_login(usuario)

    if user and check_password_hash(user['senha'], senha):
        if not user['ativo']:
            registrar_auditoria_admin(
                'login_negado_usuario_inativo',
                usuario_afetado_id=user['id'],
                usuario_afetado_login=user['usuario'],
                detalhe='Tentativa de login em conta desativada.'
            )
            return jsonify({'erro': 'Usuário desativado. Entre em contato com o TI.'}), 403

        limpar_tentativas(ip)
        session.clear()
        atualizar_sessao_usuario(user)
        session.permanent = True
        conn = conectar_users()
        conn.execute(
            'UPDATE usuarios SET ultimo_login_em = ?, atualizado_em = ? WHERE id = ?',
            (agora(), agora(), user['id'])
        )
        conn.commit()
        conn.close()
        if user['deve_trocar_senha']:
            registrar_log('login_primeiro_acesso', user['id'], user['nome'])
            return jsonify({
                'mensagem': 'Primeiro acesso identificado.',
                'redirect': '/primeiro-acesso',
                'deve_trocar_senha': True,
            }), 200

        registrar_log('login', user['id'], user['nome'])
        return jsonify({'mensagem': 'Login realizado com sucesso', 'redirect': '/relatorios'}), 200

    registrar_tentativa(ip)
    if user:
        registrar_auditoria_admin(
            'login_negado_senha_incorreta',
            usuario_afetado_id=user['id'],
            usuario_afetado_login=user['usuario'],
            detalhe='Senha inválida informada.'
        )
    return jsonify({'erro': 'Usuário ou senha incorretos'}), 401


@app.route('/api/logout', methods=['POST'])
def api_logout():
    registrar_log('logout', session.get('usuario_id'), session.get('usuario_nome'))
    session.clear()
    return jsonify({'mensagem': 'Logout realizado'}), 200


@app.route('/api/cadastro', methods=['POST'])
def api_cadastro():
    return jsonify({'erro': 'Cadastro desativado. Entre em contato com o TI.'}), 403


@app.route('/api/primeiro-acesso', methods=['POST'])
@login_requerido
def api_primeiro_acesso():
    usuario = usuario_atual()
    if not usuario['deve_trocar_senha']:
        return jsonify({'redirect': '/relatorios'}), 200

    dados = request.get_json() or {}
    senha_atual = dados.get('senha_atual', '')
    nova_senha = dados.get('nova_senha', '')
    confirmar_senha = dados.get('confirmar_senha', '')

    if not senha_atual or not nova_senha or not confirmar_senha:
        return jsonify({'erro': 'Preencha todos os campos.'}), 400
    if nova_senha != confirmar_senha:
        return jsonify({'erro': 'A confirmação da senha não confere.'}), 400
    if len(nova_senha) < 6:
        return jsonify({'erro': 'A nova senha deve ter pelo menos 6 caracteres.'}), 400
    if nova_senha == usuario['usuario']:
        return jsonify({'erro': 'A nova senha não pode ser igual ao login.'}), 400
    if not check_password_hash(usuario['senha'], senha_atual):
        return jsonify({'erro': 'A senha atual está incorreta.'}), 400

    conn = conectar_users()
    conn.execute(
        '''
        UPDATE usuarios
        SET senha = ?, deve_trocar_senha = 0, atualizado_em = ?
        WHERE id = ?
        ''',
        (generate_password_hash(nova_senha), agora(), usuario['id'])
    )
    conn.commit()
    conn.close()

    atualizar_sessao_usuario(obter_usuario_por_id(usuario['id']))
    registrar_log('troca_senha_primeiro_acesso', usuario['id'], usuario['nome'])
    registrar_auditoria_admin(
        'troca_senha_primeiro_acesso',
        usuario_afetado_id=usuario['id'],
        usuario_afetado_login=usuario['usuario'],
        detalhe='Senha atualizada no primeiro acesso.'
    )
    return jsonify({'mensagem': 'Senha atualizada com sucesso.', 'redirect': '/relatorios'}), 200


@app.route('/api/relatorio/info', methods=['GET'])
@app.route('/api/relatorios/compras/pedidos/info', methods=['GET'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_relatorio_info():
    try:
        total, ultimo_sync, ultimo_sync_status, ultimo_sync_erro = info_relatorio_pedidos()
        if ultimo_sync:
            dt = parse_db_datetime(ultimo_sync)
            ultimo_sync = dt.strftime('%d/%m/%Y %H:%M')
        else:
            ultimo_sync = 'Nunca'

        labels = {
            'sucesso': 'Novos registros',
            'sem_novos': 'Sem novidades',
            'erro': 'Falha no sync',
            'nunca': 'Nunca executado',
        }
        return jsonify({
            'total_registros': total,
            'ultima_atualizacao': ultimo_sync,
            'proximo_sync': calcular_proximo_sync(),
            'ultimo_sync_status': ultimo_sync_status,
            'ultimo_sync_status_label': labels.get(ultimo_sync_status, 'Desconhecido'),
            'ultimo_sync_erro': ultimo_sync_erro
        })
    except Exception:
        return jsonify({
            'total_registros': 'Erro',
            'ultima_atualizacao': 'Falha ao consultar',
            'proximo_sync': '--',
            'ultimo_sync_status': 'erro',
            'ultimo_sync_status_label': 'Falha ao consultar',
            'ultimo_sync_erro': None
        }), 500


@app.route('/api/relatorios/estoque/saldos/info', methods=['GET'])
@acesso_relatorio_requerido('estoque', 'saldos')
def api_relatorio_estoque_info():
    try:
        total, ultimo_sync, ultimo_sync_status, ultimo_sync_erro = info_relatorio_estoque()
        if ultimo_sync:
            dt = parse_db_datetime(ultimo_sync)
            ultimo_sync = dt.strftime('%d/%m/%Y %H:%M')
        else:
            ultimo_sync = 'Nunca'

        labels = {
            'sucesso': 'Atualizado com alterações',
            'sem_novos': 'Sem alterações',
            'erro': 'Falha no sync',
            'nunca': 'Nunca executado',
        }
        return jsonify({
            'total_registros': total,
            'ultima_atualizacao': ultimo_sync,
            'proximo_sync': calcular_proximo_sync(),
            'ultimo_sync_status': ultimo_sync_status,
            'ultimo_sync_status_label': labels.get(ultimo_sync_status, 'Desconhecido'),
            'ultimo_sync_erro': ultimo_sync_erro
        })
    except Exception:
        return jsonify({
            'total_registros': 'Erro',
            'ultima_atualizacao': 'Falha ao consultar',
            'proximo_sync': '--',
            'ultimo_sync_status': 'erro',
            'ultimo_sync_status_label': 'Falha ao consultar',
            'ultimo_sync_erro': None
        }), 500


@app.route('/api/relatorio/historico-sync', methods=['GET'])
@app.route('/api/relatorios/compras/pedidos/historico-sync', methods=['GET'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_historico_sync():
    try:
        historico = []
        for linha in historico_sync_pedidos():
            executado_em = linha['executado_em']
            if executado_em:
                executado_em = parse_db_datetime(executado_em).strftime('%d/%m/%Y %H:%M')

            historico.append({
                'executado_em': executado_em or '--',
                'registros_novos': linha['registros_novos']
            })

        return jsonify({'historico': historico})
    except Exception:
        return jsonify({'erro': 'Falha ao carregar histórico de sincronização.'}), 500


@app.route('/api/relatorios/estoque/saldos/historico-sync', methods=['GET'])
@acesso_relatorio_requerido('estoque', 'saldos')
def api_historico_sync_estoque():
    try:
        historico = []
        for linha in historico_sync_estoque():
            executado_em = linha['executado_em']
            if executado_em:
                executado_em = parse_db_datetime(executado_em).strftime('%d/%m/%Y %H:%M')

            historico.append({
                'executado_em': executado_em or '--',
                'registros_novos': linha['registros_novos']
            })

        return jsonify({'historico': historico})
    except Exception:
        return jsonify({'erro': 'Falha ao carregar histórico de sincronização.'}), 500


@app.route('/api/relatorio/download', methods=['GET'])
@app.route('/api/relatorios/compras/pedidos/download', methods=['GET'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_relatorio_download():
    formato = request.args.get('formato', 'csv').lower()

    try:
        if formato == 'excel':
            dados, total = gerar_excel_pedidos()
            registrar_log('download_excel', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download(formato, total)
            return Response(
                dados,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment; filename=pedidos_compra.xlsx'}
            )
        else:
            dados, total = gerar_csv_pedidos()
            registrar_log('download_csv', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download(formato, total)
            return Response(
                dados,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=pedidos_compra.csv'}
            )
    except Exception:
        return jsonify({'erro': 'Falha ao gerar relatório.'}), 500


@app.route('/api/relatorios/estoque/saldos/download', methods=['GET'])
@acesso_relatorio_requerido('estoque', 'saldos')
def api_relatorio_estoque_download():
    formato = request.args.get('formato', 'csv').lower()

    try:
        if formato == 'excel':
            dados, total = gerar_excel_estoque()
            registrar_log('download_estoque_excel', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download_estoque(formato, total)
            return Response(
                dados,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment; filename=saldo_estoque.xlsx'}
            )
        else:
            dados, total = gerar_csv_estoque()
            registrar_log('download_estoque_csv', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download_estoque(formato, total)
            return Response(
                dados,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=saldo_estoque.csv'}
            )
    except Exception:
        return jsonify({'erro': 'Falha ao gerar relatório.'}), 500


@app.route('/api/relatorio/sync', methods=['POST'])
@app.route('/api/relatorios/compras/pedidos/sync', methods=['POST'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_relatorio_sync():
    global ultimo_sync_dt
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Já existe uma sincronização em andamento.'}), 409
    try:
        novos = sincronizar_pedidos()
        ultimo_sync_dt = agora_sp()
        criar_backup_diario()
        limpar_logs_antigos()
        registrar_log('sync_manual', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {novos} registro(s) novo(s).'
        })
    except Exception as e:
        registrar_sync_event_pedidos(0, 'erro', str(e)[:180])
        return jsonify({'erro': 'Falha ao sincronizar com o Protheus.'}), 500
    finally:
        sync_lock.release()


@app.route('/api/relatorios/estoque/saldos/sync', methods=['POST'])
@acesso_relatorio_requerido('estoque', 'saldos')
def api_relatorio_estoque_sync():
    global ultimo_sync_dt
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Já existe uma sincronização em andamento.'}), 409
    try:
        alterados = sincronizar_estoque()
        ultimo_sync_dt = agora_sp()
        criar_backup_diario()
        limpar_logs_antigos()
        registrar_log('sync_manual_estoque', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {alterados} registro(s) alterado(s).'
        })
    except Exception as e:
        registrar_sync_event_estoque(0, 'erro', str(e)[:180])
        return jsonify({'erro': 'Falha ao sincronizar com o Protheus.'}), 500
    finally:
        sync_lock.release()


def registrar_download(formato, registros):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO downloads_log (usuario_id, usuario_nome, formato, registros, data_hora) VALUES (?, ?, ?, ?, ?)',
        (session.get('usuario_id'), session.get('usuario_nome'), formato, registros, agora())
    )
    conn.commit()
    conn.close()


def registrar_download_estoque(formato, registros):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO estoque_downloads_log (usuario_id, usuario_nome, formato, registros, data_hora) VALUES (?, ?, ?, ?, ?)',
        (session.get('usuario_id'), session.get('usuario_nome'), formato, registros, agora())
    )
    conn.commit()
    conn.close()


@app.route('/api/admin/usuarios', methods=['GET'])
@admin_requerido
def api_admin_usuarios():
    return jsonify({
        'usuarios': listar_usuarios_admin(),
        'relatorios': obter_relatorios_catalogo(),
    })


@app.route('/api/admin/usuarios', methods=['POST'])
@admin_requerido
def api_admin_criar_usuario():
    dados = request.get_json() or {}
    is_admin       = bool(dados.get('is_admin'))
    is_gerente     = bool(dados.get('is_gerente'))
    pode_ver_query = bool(dados.get('pode_ver_query'))
    setor_id       = dados.get('setor_id') or None
    permissoes     = set(dados.get('permissoes') or [])
    relatorios_validos = obter_chaves_relatorio_validas()
    email = dados.get('email', '')

    try:
        email_normalizado = normalizar_email_corporativo(email)
    except ValueError as exc:
        return jsonify({'erro': str(exc)}), 400

    usuario_login = email_normalizado.split('@', 1)[0]
    nome = gerar_nome_por_login(usuario_login)

    if setor_id and not obter_setor_por_id(setor_id):
        return jsonify({'erro': 'Setor inválido.'}), 400
    if permissoes - relatorios_validos:
        return jsonify({'erro': 'Há permissões inválidas na requisição.'}), 400
    if not is_admin and not permissoes:
        return jsonify({'erro': 'Selecione pelo menos um relatório para o usuário.'}), 400
    if obter_usuario_por_login(usuario_login):
        return jsonify({'erro': 'Já existe um usuário com esse login.'}), 409
    if obter_usuario_por_email(email_normalizado):
        return jsonify({'erro': 'Já existe um usuário com esse e-mail.'}), 409

    senha_inicial = usuario_login
    conn = conectar_users()
    cursor = conn.execute(
        '''
        INSERT INTO usuarios (
            usuario, senha, nome, email, criado_em, ativo, is_admin,
            deve_trocar_senha, pode_ver_query, setor_id, is_gerente, atualizado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (
            usuario_login, generate_password_hash(senha_inicial), nome,
            email_normalizado, agora(), 1, 1 if is_admin else 0,
            1, 1 if pode_ver_query else 0, setor_id, 1 if is_gerente else 0, agora(),
        )
    )
    novo_usuario_id = cursor.lastrowid
    if not is_admin:
        salvar_permissoes_usuario(conn, novo_usuario_id, permissoes)
    conn.commit()
    conn.close()
    novo_usuario = obter_usuario_por_id(novo_usuario_id)
    email_resultado = tentar_enviar_email_acesso_usuario(novo_usuario)

    registrar_auditoria_admin(
        'usuario_criado',
        usuario_afetado_id=novo_usuario_id,
        usuario_afetado_login=usuario_login,
        detalhe='Usuário criado com senha inicial igual ao login.',
        depois={
            'email': email_normalizado,
            'nome': nome,
            'usuario': usuario_login,
            'is_admin': is_admin,
            'permissoes': sorted(permissoes),
        }
    )
    mensagem = 'Usuário criado com sucesso e e-mail de acesso enviado.'
    if not email_resultado['ok']:
        mensagem = 'Usuário criado com sucesso, mas o e-mail não foi enviado. Deixe o Gmail configurado e faça o reenvio manualmente.'

    return jsonify({
        'mensagem': mensagem,
        'email_enviado': email_resultado['ok'],
        'email_erro': email_resultado['error'],
    }), 201


@app.route('/api/admin/usuarios/<int:usuario_id>/configuracao', methods=['POST'])
@admin_requerido
def api_admin_atualizar_configuracao_usuario(usuario_id):
    dados = request.get_json() or {}
    is_admin       = bool(dados.get('is_admin'))
    is_gerente     = bool(dados.get('is_gerente'))
    pode_ver_query = bool(dados.get('pode_ver_query'))
    setor_id       = dados.get('setor_id') or None
    permissoes     = set(dados.get('permissoes') or [])
    relatorios_validos = obter_chaves_relatorio_validas()
    usuario = obter_usuario_por_id(usuario_id)

    if not usuario:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404
    if setor_id and not obter_setor_por_id(setor_id):
        return jsonify({'erro': 'Setor inválido.'}), 400
    if permissoes - relatorios_validos:
        return jsonify({'erro': 'Há permissões inválidas na requisição.'}), 400
    if not is_admin and not permissoes:
        return jsonify({'erro': 'Selecione pelo menos um relatório para o usuário.'}), 400
    if usuario['id'] == session.get('usuario_id') and not is_admin and contar_outros_admins_ativos(usuario['id']) == 0:
        return jsonify({'erro': 'É necessário manter ao menos um superadmin ativo.'}), 400

    antes = {
        'is_admin': bool(usuario['is_admin']),
        'pode_ver_query': bool(usuario['pode_ver_query'] if 'pode_ver_query' in usuario.keys() else 0),
        'setor_id': usuario['setor_id'] if 'setor_id' in usuario.keys() else None,
        'is_gerente': bool(usuario['is_gerente'] if 'is_gerente' in usuario.keys() else 0),
        'permissoes': sorted(obter_relatorios_permitidos(usuario['id'])),
    }

    conn = conectar_users()
    conn.execute(
        '''UPDATE usuarios
           SET is_admin=?, pode_ver_query=?, setor_id=?, is_gerente=?, atualizado_em=?
           WHERE id=?''',
        (1 if is_admin else 0, 1 if pode_ver_query else 0,
         setor_id, 1 if is_gerente else 0, agora(), usuario['id'])
    )
    salvar_permissoes_usuario(conn, usuario['id'], set() if is_admin else permissoes)
    conn.commit()
    conn.close()

    if usuario['id'] == session.get('usuario_id'):
        session['is_admin']   = 1 if is_admin else 0
        session['is_gerente'] = 1 if is_gerente else 0
        session['setor_id']   = setor_id

    registrar_auditoria_admin(
        'usuario_configuracao_atualizada',
        usuario_afetado_id=usuario['id'],
        usuario_afetado_login=usuario['usuario'],
        detalhe='Perfil, setor e permissões atualizados.',
        antes=antes,
        depois={'is_admin': is_admin, 'is_gerente': is_gerente, 'setor_id': setor_id,
                'pode_ver_query': pode_ver_query, 'permissoes': sorted(permissoes)},
    )
    return jsonify({'mensagem': 'Configuração atualizada com sucesso.'}), 200


@app.route('/api/admin/usuarios/<int:usuario_id>/status', methods=['POST'])
@admin_requerido
def api_admin_status_usuario(usuario_id):
    dados = request.get_json() or {}
    ativo = bool(dados.get('ativo'))
    usuario = obter_usuario_por_id(usuario_id)

    if not usuario:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404
    if not ativo and usuario['is_admin'] and contar_outros_admins_ativos(usuario['id']) == 0:
        return jsonify({'erro': 'É necessário manter ao menos um superadmin ativo.'}), 400

    conn = conectar_users()
    conn.execute(
        '''
        UPDATE usuarios
        SET ativo = ?, desativado_em = ?, desativado_por = ?, atualizado_em = ?
        WHERE id = ?
        ''',
        (
            1 if ativo else 0,
            None if ativo else agora(),
            None if ativo else session.get('usuario_id'),
            agora(),
            usuario['id'],
        )
    )
    conn.commit()
    conn.close()

    if not ativo and usuario['id'] == session.get('usuario_id'):
        registrar_auditoria_admin(
            'usuario_desativado',
            usuario_afetado_id=usuario['id'],
            usuario_afetado_login=usuario['usuario'],
            detalhe='Conta desativada pelo superadmin.'
        )
        session.clear()
        return jsonify({'mensagem': 'Usuário desativado e sessão encerrada.', 'redirect': '/login'}), 200

    registrar_auditoria_admin(
        'usuario_ativado' if ativo else 'usuario_desativado',
        usuario_afetado_id=usuario['id'],
        usuario_afetado_login=usuario['usuario'],
        detalhe='Conta ativada.' if ativo else 'Conta desativada.'
    )
    return jsonify({'mensagem': 'Status atualizado com sucesso.'}), 200


@app.route('/api/admin/usuarios/<int:usuario_id>/reset-senha', methods=['POST'])
@admin_requerido
def api_admin_reset_senha(usuario_id):
    usuario = obter_usuario_por_id(usuario_id)
    if not usuario:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404

    conn = conectar_users()
    conn.execute(
        '''
        UPDATE usuarios
        SET senha = ?, deve_trocar_senha = 1, atualizado_em = ?
        WHERE id = ?
        ''',
        (generate_password_hash(usuario['usuario']), agora(), usuario['id'])
    )
    conn.commit()
    conn.close()

    registrar_auditoria_admin(
        'usuario_reset_senha',
        usuario_afetado_id=usuario['id'],
        usuario_afetado_login=usuario['usuario'],
        detalhe='Senha resetada para o login.'
    )
    return jsonify({'mensagem': 'Senha resetada com sucesso.'}), 200


@app.route('/api/admin/usuarios/<int:usuario_id>/reenviar-email', methods=['POST'])
@admin_requerido
def api_admin_reenviar_email(usuario_id):
    usuario = obter_usuario_por_id(usuario_id)
    if not usuario:
        return jsonify({'erro': 'Usuário não encontrado.'}), 404
    if not usuario['email']:
        return jsonify({'erro': 'Usuário sem e-mail cadastrado.'}), 400

    email_resultado = tentar_enviar_email_acesso_usuario(usuario)
    if email_resultado['ok']:
        registrar_auditoria_admin(
            'email_acesso_reenviado',
            usuario_afetado_id=usuario['id'],
            usuario_afetado_login=usuario['usuario'],
            detalhe='Reenvio manual do e-mail de acesso concluído.'
        )
        return jsonify({'mensagem': 'E-mail reenviado com sucesso.'}), 200

    registrar_auditoria_admin(
        'email_acesso_reenvio_falhou',
        usuario_afetado_id=usuario['id'],
        usuario_afetado_login=usuario['usuario'],
        detalhe=f'Reenvio manual falhou: {email_resultado["error"]}'
    )
    return jsonify({
        'mensagem': 'Tentativa de reenvio registrada, mas o e-mail não foi enviado. Verifique a configuração do Gmail.',
        'erro': email_resultado['error'],
    }), 200


@app.route('/api/admin/logs', methods=['GET'])
@admin_requerido
def api_admin_logs():
    usuario_id = request.args.get('usuario_id', type=int)
    acao = request.args.get('acao', '').strip() or None
    return jsonify({
        'logs_acesso': listar_logs_acesso(),
        'auditoria': listar_auditoria_admin(usuario_id=usuario_id, acao=acao),
    })


@app.route('/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok'}), 200


@app.route('/api/health', methods=['GET'])
def api_health():
    status = {
        'status': 'ok',
        'banco_users': 'ok',
        'banco_pedidos': 'ok',
        'ultimo_sync': None,
        'hora_servidor': agora_sp().strftime('%Y-%m-%d %H:%M:%S'),
        'timezone': APP_TIMEZONE,
    }
    try:
        conn = conectar_users()
        conn.execute('SELECT 1').fetchone()
        conn.close()
    except Exception:
        status['banco_users'] = 'erro'
        status['status'] = 'degradado'

    try:
        conn = conectar_pedidos()
        conn.execute('SELECT 1').fetchone()
        conn.close()
    except Exception:
        status['banco_pedidos'] = 'erro'
        status['status'] = 'degradado'

    try:
        _, ultimo_pedidos, _, _ = info_relatorio_pedidos()
        _, ultimo_estoque, _, _ = info_relatorio_estoque()
        status['ultimo_sync'] = ultimo_pedidos or 'Nunca'
        status['ultimo_sync_estoque'] = ultimo_estoque or 'Nunca'
    except Exception:
        status['ultimo_sync'] = 'Erro'
        status['ultimo_sync_estoque'] = 'Erro'

    return jsonify(status)


def inicializar():
    global ultimo_sync_dt
    criar_tabelas()
    consolidar_sync_log_pedidos()
    consolidar_sync_log_estoque()
    limpar_logs_antigos()
    print('[STARTUP] Verificando carga inicial...')
    try:
        total_pedidos = carga_inicial_pedidos()
        total_estoque = carga_inicial_estoque()
        if total_pedidos > 0:
            print(f'[STARTUP] Carga inicial de pedidos concluída. {total_pedidos} registros importados.')
        else:
            print('[STARTUP] Dados de pedidos já existem no banco local.')

        if total_estoque > 0:
            print(f'[STARTUP] Carga inicial de estoque concluída. {total_estoque} registros importados.')
        else:
            print('[STARTUP] Dados de estoque já existem no banco local.')

        _, ultimo_sync_pedidos, _, _ = info_relatorio_pedidos()
        _, ultimo_sync_estoque, _, _ = info_relatorio_estoque()
        ultimo_sync_ref = ultimo_sync_pedidos or ultimo_sync_estoque
        if ultimo_sync_ref:
            ultimo_sync_dt = parse_db_datetime(ultimo_sync_ref)
        else:
            ultimo_sync_dt = agora_sp()
    except Exception as e:
        print(f'[STARTUP] Erro na carga inicial: {e}')

    if criar_backup_diario():
        print('[BACKUP] Backup diário criado com sucesso.')

    agendar_proximo_sync()
    print(f'[SYNC] Próximo sync agendado para {calcular_proximo_sync()}.')


inicializar()

if __name__ == '__main__':
    app.run(debug=False, port=5000, use_reloader=False)
