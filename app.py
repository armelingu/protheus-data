import os
import json
import re
import time
import hmac
import secrets
import threading
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, redirect, render_template, send_from_directory, Response, session, g, has_request_context
from werkzeug.security import check_password_hash, generate_password_hash
from dotenv import load_dotenv
from services.catalogo_relatorios import listar_modulos, listar_relatorios_flat, obter_relatorio, chave_relatorio
from services.database import (
    conectar_users,
    conectar_pedidos,
    conectar_financeiro,
    criar_tabelas,
    limpar_logs_antigos,
    criar_backup_diario,
    agora,
)
from services.cache import cache_get, cache_set, cache_namespace
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
from services.relatorios.energy.pedidos import (
    QUERY_PEDIDOS as QUERY_PEDIDOS_ENERGY,
    gerar_csv as gerar_csv_pedidos_energy,
    gerar_excel as gerar_excel_pedidos_energy,
    info_relatorio as info_relatorio_pedidos_energy,
    historico_sync as historico_sync_pedidos_energy,
    sincronizar as sincronizar_pedidos_energy,
    carga_inicial as carga_inicial_pedidos_energy,
    registrar_sync_event as registrar_sync_event_pedidos_energy,
)
from services.relatorios.compras.historico_pedidos import (
    QUERY_HISTORICO_BASE as QUERY_HISTORICO_PEDIDOS,
    gerar_csv_historico,
    gerar_excel_historico,
    info_relatorio_historico,
    historico_sync_historico,
    sincronizar_historico,
    carga_inicial_historico,
    registrar_sync_event_historico,
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
from services.relatorios.financeiro.nf_entrada import (
    gerar_csv_nf_entrada, gerar_excel_nf_entrada,
    info_relatorio_nf_entrada, historico_sync_nf_entrada,
    sincronizar_nf_entrada, carga_inicial_nf_entrada,
    QUERY_PAGINADA as QUERY_NF_ENTRADA,
)
from services.relatorios.financeiro.nf_saida import (
    gerar_csv_nf_saida, gerar_excel_nf_saida,
    info_relatorio_nf_saida, historico_sync_nf_saida,
    sincronizar_nf_saida, carga_inicial_nf_saida,
    QUERY_PAGINADA as QUERY_NF_SAIDA,
)
from services.relatorios.financeiro.contas_receber import (
    gerar_csv_contas_receber, gerar_excel_contas_receber,
    info_relatorio_contas_receber, historico_sync_contas_receber,
    sincronizar_contas_receber, carga_inicial_contas_receber,
    QUERY_PAGINADA as QUERY_CONTAS_RECEBER,
)
from services.relatorios.energy.contas_pagar import (
    gerar_csv_energy_contas_pagar, gerar_excel_energy_contas_pagar,
    info_relatorio_energy_contas_pagar, historico_sync_energy_contas_pagar,
    sincronizar_energy_contas_pagar, carga_inicial_energy_contas_pagar,
    QUERY_PAGINADA as QUERY_ENERGY_CONTAS_PAGAR,
)
from services.relatorios.financeiro.contas_pagar import (
    gerar_csv_contas_pagar, gerar_excel_contas_pagar,
    info_relatorio_contas_pagar, historico_sync_contas_pagar,
    sincronizar_contas_pagar, carga_inicial_contas_pagar,
    QUERY_PAGINADA as QUERY_CONTAS_PAGAR,
)
from services.relatorios.financeiro.mov_bancarios import (
    gerar_csv_mov_bancarios, gerar_excel_mov_bancarios,
    info_relatorio_mov_bancarios, historico_sync_mov_bancarios,
    sincronizar_mov_bancarios, carga_inicial_mov_bancarios,
    QUERY_PAGINADA as QUERY_MOV_BANCARIOS,
)
from services.email_service import montar_email_acesso, enviar_email
from services.time_utils import APP_TIMEZONE, agora_sp, parse_db_datetime

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
app.config['SESSION_COOKIE_NAME'] = 'protheusdata_session'
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.getenv('SESSION_COOKIE_SECURE', 'false').lower() == 'true'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(seconds=int(os.getenv('SESSION_LIFETIME_SECONDS', '604800')))  # 7 dias padrão
app.config['SESSION_REFRESH_EACH_REQUEST'] = True

# Compressão automática (gzip/deflate/br) negociada via Accept-Encoding.
# Aplica-se a JSON (OData), HTML, CSV e JS/CSS. Não recomprime XLSX (já zipado).
# Power BI envia Accept-Encoding: gzip por padrão -> reduz banda OData ~80%.
app.config['COMPRESS_MIMETYPES'] = [
    'application/json',
    'application/json;odata.metadata=minimal',
    'application/xml',  # OData $metadata
    'text/html',
    'text/css',
    'text/csv',
    'text/plain',
    'application/javascript',
]
app.config['COMPRESS_LEVEL']    = 6  # padrão; bom equilíbrio CPU x ratio
app.config['COMPRESS_MIN_SIZE'] = 500  # não comprime payloads minúsculos
try:
    from flask_compress import Compress
    Compress(app)
except ImportError:
    print('[WARN] flask_compress não instalado — respostas sairão sem gzip.')


def _gerar_csrf_token():
    """Gera e persiste um token CSRF na sessão. Idempotente."""
    if 'csrf_token' not in session:
        session['csrf_token'] = secrets.token_hex(32)
        session.modified = True
    return session['csrf_token']


@app.before_request
def renovar_sessao():
    """Garante que toda requisição autenticada renova o prazo da sessão e possui CSRF token."""
    if session.get('usuario_id'):
        session.permanent = True
        session.modified = True
        _gerar_csrf_token()


@app.before_request
def _validar_csrf():
    """Valida X-CSRF-Token em mutações de estado para rotas autenticadas por sessão.

    Rotas excluídas:
    - Métodos seguros (GET, HEAD, OPTIONS)
    - Prefixo /odata/ — autenticadas por Bearer token, não por cookie de sessão
    - Requisições sem sessão ativa — a rota própria rejeitará via @login_requerido
    """
    if request.method in ('GET', 'HEAD', 'OPTIONS'):
        return
    if request.path.startswith('/odata/'):
        return
    if not session.get('usuario_id'):
        return

    token_sessao  = session.get('csrf_token', '')
    token_recebido = request.headers.get('X-CSRF-Token', '')

    if not token_sessao or not hmac.compare_digest(token_sessao, token_recebido):
        return jsonify({'erro': 'Requisição inválida. Recarregue a página e tente novamente.'}), 403


@app.context_processor
def _injetar_csrf_token():
    """Disponibiliza {{ csrf_token }} em todos os templates Jinja2."""
    if session.get('usuario_id'):
        return {'csrf_token': _gerar_csrf_token()}
    return {'csrf_token': ''}


@app.route('/api/csrf-token', methods=['GET'])
def api_csrf_token():
    """Retorna o token CSRF da sessão atual (útil para diagnóstico e testes)."""
    if not session.get('usuario_id'):
        return jsonify({'erro': 'Não autenticado.'}), 401
    return jsonify({'csrf_token': _gerar_csrf_token()})


@app.after_request
def _no_cache_em_apis(resp):
    """Impede cache de browser em endpoints de API e telas administrativas.

    Safari/Chrome podem servir respostas em cache para fetch() GET, fazendo
    a UI mostrar dados velhos após uma mutação (ex.: setor recém-excluído
    reaparecendo após DELETE). Endpoints de assets estáticos não são afetados.
    """
    try:
        path = request.path or ''
        if path.startswith('/api/') or path.startswith('/admin/'):
            resp.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
            resp.headers['Pragma'] = 'no-cache'
            resp.headers['Expires'] = '0'
    except Exception:
        pass
    return resp

SYNC_INTERVALO = 3600
MAX_TENTATIVAS_LOGIN = 5
BLOQUEIO_MINUTOS = 5
EMAIL_CORPORATIVOS_DOMINIOS = ('hbraviacao.com.br', 'hbrenergy.com.br')

# Quando TRUST_PROXY_HEADERS=true, lê o IP real do cliente via X-Forwarded-For
# (definido pelo proxy/Nginx). Manter false se o app estiver exposto diretamente.
_TRUST_PROXY = os.getenv('TRUST_PROXY_HEADERS', 'false').lower() == 'true'


def _obter_ip_real():
    """Retorna o IP real do cliente, respeitando proxies se configurado.

    Com TRUST_PROXY_HEADERS=true: usa o primeiro IP de X-Forwarded-For,
    que é o IP original do cliente antes de passar pelo proxy/Nginx.
    Sem a flag: usa request.remote_addr diretamente (seguro em deploy sem proxy).
    """
    if _TRUST_PROXY:
        xff = request.headers.get('X-Forwarded-For', '')
        if xff:
            return xff.split(',')[0].strip()
    return request.remote_addr or '0.0.0.0'
ROTAS_LIBERADAS_TROCA_SENHA = {'/primeiro-acesso', '/api/primeiro-acesso', '/api/logout', '/favicon.ico'}

ultimo_sync_dt = None
sync_timer = None
sync_lock = threading.Lock()
QUERY_PREVIEW_PEDIDOS        = QUERY_PEDIDOS.strip() + '\nORDER BY SC7.C7_EMISSAO DESC'
QUERY_PREVIEW_PEDIDOS_ENERGY = QUERY_PEDIDOS_ENERGY.strip() + '\nORDER BY SC7.C7_EMISSAO DESC'
QUERY_PREVIEW_ESTOQUE = QUERY_ESTOQUE.strip()


def _json_dump(valor):
    if valor is None:
        return None
    return json.dumps(valor, ensure_ascii=True, sort_keys=True)


def obter_usuario_por_id(usuario_id):
    conn = conectar_users()
    try:
        return conn.execute('SELECT * FROM usuarios WHERE id = ?', (usuario_id,)).fetchone()
    finally:
        conn.close()


def obter_usuario_por_login(login):
    conn = conectar_users()
    try:
        return conn.execute('SELECT * FROM usuarios WHERE usuario = ?', (login,)).fetchone()
    finally:
        conn.close()


def obter_usuario_por_email(email):
    conn = conectar_users()
    try:
        return conn.execute('SELECT * FROM usuarios WHERE email = ?', (email,)).fetchone()
    finally:
        conn.close()


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
    if not email_normalizado or email_normalizado.count('@') != 1:
        raise ValueError('Informe um e-mail corporativo válido.')

    login, dominio = email_normalizado.split('@', 1)
    if dominio not in EMAIL_CORPORATIVOS_DOMINIOS:
        permitidos = ', '.join('@' + d for d in EMAIL_CORPORATIVOS_DOMINIOS)
        raise ValueError(f'Apenas e-mails corporativos são permitidos ({permitidos}).')
    if not login:
        raise ValueError('O e-mail informado é inválido.')
    return email_normalizado


def gerar_nome_por_login(login):
    partes = [parte for parte in login.replace('-', '.').replace('_', '.').split('.') if parte]
    return ' '.join(parte[:1].upper() + parte[1:] for parte in partes)


def obter_relatorios_catalogo():
    return listar_relatorios_flat()


def obter_chaves_relatorio_validas():
    return {relatorio['chave'] for relatorio in listar_relatorios_flat(incluir_admin_only=True)}


def _cache_request(chave):
    """Devolve um dict (cache local do request) ou None se fora do app context.

    Usado para memoizar leituras de permissões dentro do mesmo request HTTP.
    Em scripts/CLI (sem request ativo) caímos para leitura direta.
    """
    try:
        if not has_request_context():
            return None
        if not hasattr(g, '_perm_cache'):
            g._perm_cache = {}
        return g._perm_cache.setdefault(chave, {})
    except Exception:
        return None


_PERM_CACHE_TTL = int(os.getenv('CACHE_PERM_TTL_SECONDS', '30'))


def obter_relatorios_permitidos(usuario_id):
    # 1) Cache intra-request (g) — corta repeticoes dentro de uma mesma chamada
    cache = _cache_request('usuario')
    if cache is not None and usuario_id in cache:
        return cache[usuario_id]

    # 2) Cache cross-request (Redis ou fallback in-memory) — TTL curto
    chave_externa = f'perm:user:{usuario_id}'
    valor_ext = cache_get(chave_externa)
    if valor_ext is not None:
        resultado = set(valor_ext)
        if cache is not None:
            cache[usuario_id] = resultado
        return resultado

    # 3) Source of truth: SQLite
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
    resultado = {chave_relatorio(linha['modulo_id'], linha['relatorio_id']) for linha in linhas}

    cache_set(chave_externa, list(resultado), ttl=_PERM_CACHE_TTL)
    if cache is not None:
        cache[usuario_id] = resultado
    return resultado


def obter_relatorios_permitidos_setor(setor_id):
    if not setor_id:
        return None

    cache = _cache_request('setor')
    if cache is not None and setor_id in cache:
        return cache[setor_id]

    chave_externa = f'perm:setor:{setor_id}'
    valor_ext = cache_get(chave_externa)
    if valor_ext is not None:
        resultado = set(valor_ext)
        if cache is not None:
            cache[setor_id] = resultado
        return resultado

    conn = conectar_users()
    linhas = conn.execute(
        'SELECT modulo_id, relatorio_id FROM setor_permissoes_relatorio WHERE setor_id = ?',
        (setor_id,)
    ).fetchall()
    conn.close()
    resultado = {chave_relatorio(l['modulo_id'], l['relatorio_id']) for l in linhas}

    cache_set(chave_externa, list(resultado), ttl=_PERM_CACHE_TTL)
    if cache is not None:
        cache[setor_id] = resultado
    return resultado


def invalidar_cache_permissoes():
    """Invalida cache de permissões em todas as camadas.

    Chamar após qualquer escrita em usuario_permissoes_relatorio ou
    setor_permissoes_relatorio. Invalida tanto o cache intra-request (g) quanto
    o cache cross-request (Redis/fallback) — propaga para outros workers via
    Redis quando disponível.
    """
    try:
        if has_request_context() and hasattr(g, '_perm_cache'):
            g._perm_cache = {}
    except Exception:
        pass
    try:
        cache_namespace('perm:').invalidate()
    except Exception:
        pass


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
        g.api_token_id = row['token_id']
    conn.close()
    return usuario


def obter_permissoes_token(token_id):
    """Retorna o conjunto de chaves de relatório que o token tem escopo explícito.
    Retorna None se o token não tem escopos definidos (tokens legados — acesso via permissão do usuário)."""
    conn = conectar_users()
    linhas = conn.execute(
        'SELECT modulo_id, relatorio_id FROM api_token_permissoes WHERE token_id=?',
        (token_id,)
    ).fetchall()
    conn.close()
    if not linhas:
        return None
    return {chave_relatorio(l['modulo_id'], l['relatorio_id']) for l in linhas}


def token_tem_acesso_relatorio(token_id, modulo_id, relatorio_id):
    """Verifica se o token tem escopo explícito para o relatório.
    Tokens sem nenhum escopo definido são bloqueados por segurança (fail-closed)."""
    escopos = obter_permissoes_token(token_id)
    if escopos is None:
        return False
    return chave_relatorio(modulo_id, relatorio_id) in escopos


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
    agora_atual = agora()
    valores = []
    for chave in permissoes:
        # chave pode ser 'modulo.relatorio' (ponto) ou 'modulo:relatorio' (dois-pontos)
        sep = '.' if '.' in chave else ':'
        partes = chave.split(sep, 1)
        if len(partes) == 2:
            valores.append((setor_id, partes[0], partes[1], agora_atual))
    if valores:
        conn.executemany(
            'INSERT OR IGNORE INTO setor_permissoes_relatorio '
            '(setor_id, modulo_id, relatorio_id, criado_em) VALUES (?,?,?,?)',
            valores
        )
    if fechar:
        conn.commit()
        conn.close()
    invalidar_cache_permissoes()


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
        # Setor sem permissões configuradas = sem restrição de setor (não bloqueia).
        # Setor com permissões configuradas = usuário precisa ter E setor ter o relatório.
        if perms_setor:
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
                # not permissoes_setor: setor sem permissões configuradas (None ou set vazio) = sem restrição
                tem_setor   = not permissoes_setor or chave in permissoes_setor
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
    try:
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
                _obter_ip_real(),
                agora(),
            )
        )
        conn.commit()
    finally:
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
                try:
                    registrar_log(
                        f'acesso_negado_{modulo_id}_{relatorio_id}',
                        session.get('usuario_id'),
                        session.get('usuario_nome'),
                    )
                except Exception:
                    pass
                return resposta_sem_acesso('Seu usuário não possui permissão para este relatório.')
            return f(*args, **kwargs)
        return wrapper
    return decorator


def registrar_log(acao, usuario_id=None, usuario_nome=None):
    conn = conectar_users()
    conn.execute(
        'INSERT INTO logs_acesso (usuario_id, usuario_nome, acao, ip, data_hora) VALUES (?, ?, ?, ?, ?)',
        (usuario_id, usuario_nome, acao, _obter_ip_real(), agora())
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
        invalidar_cache_permissoes()
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
    invalidar_cache_permissoes()


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
        SELECT e.usuario_id, e.status, e.tentativas, e.ultimo_erro,
               e.criado_em, e.enviado_em, e.atualizado_em
        FROM emails_usuarios_log e
        INNER JOIN (
            SELECT usuario_id, MAX(id) AS max_id
            FROM emails_usuarios_log
            WHERE tipo = 'acesso'
            GROUP BY usuario_id
        ) m ON e.id = m.max_id
        '''
    ).fetchall()
    conn.close()

    permissoes_por_usuario = {}
    for linha in permissoes:
        permissoes_por_usuario.setdefault(linha['usuario_id'], []).append(
            chave_relatorio(linha['modulo_id'], linha['relatorio_id'])
        )

    emails_por_usuario = {linha['usuario_id']: linha for linha in emails}

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


def listar_logs_acesso(limit=500, offset=0, busca=None, acao=None, data_inicio=None, data_fim=None):
    conn = conectar_users()
    sql    = 'SELECT usuario_nome, acao, ip, data_hora FROM logs_acesso WHERE 1=1'
    params = []

    if busca:
        sql += ' AND (usuario_nome LIKE ? OR ip LIKE ?)'
        params += [f'%{busca}%', f'%{busca}%']
    if acao:
        sql += ' AND acao = ?'
        params.append(acao)
    if data_inicio:
        sql += ' AND date(data_hora) >= ?'
        params.append(data_inicio)
    if data_fim:
        sql += ' AND date(data_hora) <= ?'
        params.append(data_fim)

    total = conn.execute(
        sql.replace('SELECT usuario_nome, acao, ip, data_hora', 'SELECT COUNT(*)'),
        tuple(params),
    ).fetchone()[0]

    sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    params += [limit, offset]
    linhas = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return {
        'total': total,
        'itens': [
            {
                'usuario_nome': linha['usuario_nome'] or 'Sistema',
                'acao': linha['acao'],
                'ip': linha['ip'] or '--',
                'data_hora': serializar_data(linha['data_hora']) or '--',
            }
            for linha in linhas
        ],
    }


def listar_auditoria_admin(limit=500, offset=0, usuario_id=None, acao=None,
                           busca=None, data_inicio=None, data_fim=None):
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
    if busca:
        sql += ' AND (admin_usuario_nome LIKE ? OR usuario_afetado_login LIKE ? OR detalhe LIKE ?)'
        params += [f'%{busca}%', f'%{busca}%', f'%{busca}%']
    if data_inicio:
        sql += ' AND date(data_hora) >= ?'
        params.append(data_inicio)
    if data_fim:
        sql += ' AND date(data_hora) <= ?'
        params.append(data_fim)

    total = conn.execute(
        sql.replace(
            'SELECT admin_usuario_nome, acao, usuario_afetado_login, detalhe, ip, data_hora',
            'SELECT COUNT(*)',
        ),
        tuple(params),
    ).fetchone()[0]

    sql += ' ORDER BY id DESC LIMIT ? OFFSET ?'
    params += [limit, offset]

    linhas = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return {
        'total': total,
        'itens': [
            {
                'admin_usuario_nome': linha['admin_usuario_nome'] or 'Sistema',
                'acao': linha['acao'],
                'usuario_afetado_login': linha['usuario_afetado_login'] or '--',
                'detalhe': linha['detalhe'] or '',
                'ip': linha['ip'] or '--',
                'data_hora': serializar_data(linha['data_hora']) or '--',
            }
            for linha in linhas
        ],
    }


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
    try:
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
                            novos_pedidos        = sincronizar_pedidos()
                            novos_pedidos_energy = sincronizar_pedidos_energy()
                            alterados_estoque    = sincronizar_estoque()
                            novos_historico      = sincronizar_historico()

                            # Módulo Financeiro — paralelo (cada job tem sua própria
                            # conexão pyodbc + conexão SQLite; financeiro.db está em
                            # WAL, suporta leituras/escritas concorrentes).
                            _fin_syncs = [
                                ('NF Entrada',           sincronizar_nf_entrada),
                                ('NF Saída',             sincronizar_nf_saida),
                                ('Contas a Receber',     sincronizar_contas_receber),
                                ('Contas a Pagar',       sincronizar_contas_pagar),
                                ('Movimentos Bancários', sincronizar_mov_bancarios),
                                ('Energy — Contas a Pagar', sincronizar_energy_contas_pagar),
                            ]
                            from concurrent.futures import ThreadPoolExecutor, as_completed
                            with ThreadPoolExecutor(max_workers=3, thread_name_prefix='fin-sync') as ex:
                                futs = {ex.submit(_fn_f): _nome_f for _nome_f, _fn_f in _fin_syncs}
                                for fut in as_completed(futs):
                                    _nome_f = futs[fut]
                                    try:
                                        _tot_f = fut.result()
                                        print(f'[SYNC] Financeiro — {_nome_f}: {_tot_f} registro(s) processado(s).')
                                    except Exception as _e_f:
                                        print(f'[SYNC] Financeiro — {_nome_f}: erro: {_e_f}')

                            ultimo_sync_dt = agora_sp()
                            if criar_backup_diario():
                                print('[BACKUP] Backup diário criado com sucesso.')
                            print(f'[SYNC] Pedidos sincronizados. {novos_pedidos} registro(s) novo(s).')
                            print(f'[SYNC] Pedidos Energy sincronizados. {novos_pedidos_energy} registro(s) novo(s).')
                            print(f'[SYNC] Estoque sincronizado. {alterados_estoque} registro(s) alterado(s).')
                            print(f'[SYNC] Histórico sincronizado. {novos_historico} registro(s) novo(s).')
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
                        registrar_sync_event_pedidos_energy(0, 'erro', str(ultimo_erro)[:180])
                        registrar_sync_event_estoque(0, 'erro', str(ultimo_erro)[:180])
                        registrar_sync_event_historico(0, 'erro', str(ultimo_erro)[:180])
                finally:
                    sync_lock.release()
        else:
            print(f'[SYNC] Fora do horário (08h-19h). Atual: {hora_atual}h. Pulando.')

        limpar_logs_antigos()
    except Exception as e:
        print(f'[SYNC] Erro inesperado na rotina de sync: {e}')
    finally:
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
        page_title='ProtheusData - Atualizar senha',
        csrf_token=session.get('csrf_token', '')
    )


@app.route('/relatorios')
@login_requerido
def pagina_relatorios():
    usuario = usuario_atual()
    motivo_sem_acesso = None

    if not usuario['is_admin'] and not filtrar_modulos_usuario(usuario):
        setor_id = usuario['setor_id'] if 'setor_id' in usuario.keys() else None
        if setor_id:
            perms_setor = obter_relatorios_permitidos_setor(setor_id)
            setor = obter_setor_por_id(setor_id)
            nome_setor = setor['nome'] if setor else 'seu setor'
            if not perms_setor:
                motivo_sem_acesso = (
                    f'O setor <strong>{nome_setor}</strong> não tem relatórios '
                    f'configurados. Peça ao administrador para configurar as '
                    f'permissões do setor.'
                )
            else:
                motivo_sem_acesso = (
                    'Você não tem permissão para nenhum relatório. '
                    'Entre em contato com o administrador.'
                )
        else:
            motivo_sem_acesso = (
                'Você não tem permissão para nenhum relatório. '
                'Entre em contato com o administrador.'
            )

    return render_template(
        'relatorios/home.html',
        motivo_sem_acesso=motivo_sem_acesso,
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
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/compras_pedidos.html',
        modulo_ativo=modulo,
        relatorio_ativo=relatorio,
        query_preview=QUERY_PREVIEW_PEDIDOS if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Pedidos de Compra')
    )


@app.route('/relatorios/energy/pedidos')
@acesso_relatorio_requerido('energy', 'pedidos')
def pagina_relatorio_energy_pedidos():
    modulo, relatorio = obter_relatorio('energy', 'pedidos')
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/energy_pedidos.html',
        modulo_ativo=modulo,
        relatorio_ativo=relatorio,
        query_preview=QUERY_PREVIEW_PEDIDOS_ENERGY if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Pedidos Energy')
    )


@app.route('/relatorios/compras/historico')
@acesso_relatorio_requerido('compras', 'historico')
def pagina_relatorio_compras_historico():
    modulo, relatorio = obter_relatorio('compras', 'historico')
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/compras_historico.html',
        modulo_ativo=modulo,
        relatorio_ativo=relatorio,
        query_preview=QUERY_HISTORICO_PEDIDOS if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Histórico de Pedidos')
    )


@app.route('/relatorios/estoque/saldos')
@acesso_relatorio_requerido('estoque', 'saldos')
def pagina_relatorio_estoque_saldos():
    modulo, relatorio = obter_relatorio('estoque', 'saldos')
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
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

# Mapa declarativo: todos os relatórios expostos via OData/Power BI.
# Cada entrada vira: (a) checkbox de escopo na criação de token,
# (b) linha na lista de endpoints disponíveis,
# (c) URL "pronta para copiar" ao gerar um token.
ENDPOINTS_POWER_BI = [
    {'chave': 'compras.pedidos',         'tag': 'Pedidos',          'titulo': 'Pedidos de Compra',     'url_path': '/odata/pedidos'},
    {'chave': 'energy.pedidos',          'tag': 'Energy Pedidos',   'titulo': 'Pedidos Energy',        'url_path': '/odata/energy-pedidos'},
    {'chave': 'compras.historico',       'tag': 'Histórico',        'titulo': 'Histórico de Pedidos',  'url_path': '/odata/historico-pedidos'},
    {'chave': 'estoque.saldos',          'tag': 'Estoque',          'titulo': 'Saldo em Estoque',      'url_path': '/odata/estoque'},
    {'chave': 'financeiro.nf_entrada',   'tag': 'NF Entrada',       'titulo': 'NF de Entrada',         'url_path': '/odata/nf-entrada'},
    {'chave': 'financeiro.nf_saida',     'tag': 'NF Saída',         'titulo': 'NF de Saída',           'url_path': '/odata/nf-saida'},
    {'chave': 'financeiro.contas_receber','tag': 'Contas a Receber','titulo': 'Contas a Receber',      'url_path': '/odata/contas-receber'},
    {'chave': 'financeiro.contas_pagar', 'tag': 'Contas a Pagar',   'titulo': 'Contas a Pagar',        'url_path': '/odata/contas-pagar'},
    {'chave': 'financeiro.mov_bancarios','tag': 'Mov. Bancários',   'titulo': 'Movimentos Bancários',  'url_path': '/odata/mov-bancarios'},
    {'chave': 'energy.contas_pagar',     'tag': 'Energy CP',        'titulo': 'Energy — Contas a Pagar', 'url_path': '/odata/energy-contas-pagar'},
]


def endpoints_power_bi_do_usuario(usuario):
    """Retorna somente os endpoints do catálogo OData que o usuário tem permissão."""
    disponiveis = []
    for endpoint in ENDPOINTS_POWER_BI:
        modulo_id, relatorio_id = endpoint['chave'].split('.', 1)
        if usuario_tem_acesso_relatorio(usuario, modulo_id, relatorio_id):
            disponiveis.append(endpoint)
    return disponiveis


@app.route('/meu-perfil')
@login_requerido
def pagina_perfil():
    usuario = usuario_atual()
    endpoints_pbi = endpoints_power_bi_do_usuario(usuario)
    return render_template(
        'perfil/index.html',
        endpoints_pbi=endpoints_pbi,
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
    escopos = conn.execute(
        'SELECT p.token_id, p.modulo_id, p.relatorio_id '
        'FROM api_token_permissoes p '
        'INNER JOIN api_tokens t ON t.id = p.token_id '
        'WHERE t.usuario_id=? AND t.ativo=1',
        (uid,)
    ).fetchall()
    conn.close()

    escopos_por_token = {}
    for e in escopos:
        escopos_por_token.setdefault(e['token_id'], []).append(
            chave_relatorio(e['modulo_id'], e['relatorio_id'])
        )

    return jsonify({'tokens': [
        {
            'id': t['id'],
            'nome': t['nome'],
            'criado_em': serializar_data(t['criado_em']),
            'ultimo_uso': serializar_data(t['ultimo_uso']) or 'Nunca utilizado',
            'permissoes': sorted(escopos_por_token.get(t['id'], [])),
        }
        for t in tokens
    ]})


@app.route('/api/meu-perfil/tokens', methods=['POST'])
@login_requerido
def api_criar_token():
    dados = request.get_json() or {}
    nome = (dados.get('nome') or '').strip()
    permissoes = set(dados.get('permissoes') or [])

    if not nome:
        return jsonify({'erro': 'Informe um nome para identificar o token.'}), 400
    if not permissoes:
        return jsonify({'erro': 'Selecione pelo menos um relatório para o token.'}), 400

    relatorios_validos = obter_chaves_relatorio_validas()
    if permissoes - relatorios_validos:
        return jsonify({'erro': 'Há relatórios inválidos na seleção.'}), 400

    uid = session['usuario_id']
    usuario = obter_usuario_por_id(uid)

    # Garante que o usuário só pode conceder escopos que ele próprio tem acesso
    permissoes_usuario = obter_relatorios_permitidos(uid) if not usuario['is_admin'] else relatorios_validos
    nao_autorizadas = permissoes - permissoes_usuario
    if nao_autorizadas:
        registrar_auditoria_admin(
            'token_escalada_rejeitada',
            usuario_afetado_id=uid,
            usuario_afetado_login=usuario['usuario'] if usuario else None,
            detalhe=(
                f'Tentativa de criar token "{nome}" com escopos fora das permissões do usuário: '
                f'{sorted(nao_autorizadas)}'
            ),
        )
        registrar_log('token_escalada_rejeitada', uid, session.get('usuario_nome'))
        return jsonify({'erro': 'Você não tem permissão para um ou mais relatórios selecionados.'}), 403

    conn = conectar_users()
    total = conn.execute(
        'SELECT COUNT(*) FROM api_tokens WHERE usuario_id=? AND ativo=1', (uid,)
    ).fetchone()[0]
    if total >= 5:
        conn.close()
        return jsonify({'erro': 'Limite de 5 tokens ativos por usuário atingido. Revogue um antes de criar novo.'}), 409

    token = secrets.token_urlsafe(32)
    cursor = conn.execute(
        'INSERT INTO api_tokens (usuario_id, nome, token, criado_em, ativo) VALUES (?,?,?,?,1)',
        (uid, nome, token, agora())
    )
    novo_token_id = cursor.lastrowid
    if permissoes:
        conn.executemany(
            'INSERT INTO api_token_permissoes (token_id, modulo_id, relatorio_id) VALUES (?,?,?)',
            [(novo_token_id, *chave.split('.', 1)) for chave in permissoes]
        )
    conn.commit()
    conn.close()

    registrar_auditoria_admin(
        'token_criado',
        usuario_afetado_id=uid,
        usuario_afetado_login=usuario['usuario'] if usuario else None,
        detalhe=f'Token OData "{nome}" (id={novo_token_id}) criado com escopos {sorted(permissoes)}.',
    )
    registrar_log('token_criado', uid, session.get('usuario_nome'))

    return jsonify({'mensagem': f'Token "{nome}" criado.', 'token': token}), 201


@app.route('/api/meu-perfil/tokens/<int:token_id>', methods=['DELETE'])
@login_requerido
def api_revogar_token(token_id):
    uid = session['usuario_id']
    conn = conectar_users()
    info = conn.execute(
        'SELECT nome, ativo FROM api_tokens WHERE id=? AND usuario_id=?',
        (token_id, uid)
    ).fetchone()
    if not info:
        conn.close()
        return jsonify({'erro': 'Token não encontrado.'}), 404

    conn.execute(
        'UPDATE api_tokens SET ativo=0 WHERE id=? AND usuario_id=?', (token_id, uid)
    )
    conn.execute(
        'DELETE FROM api_token_permissoes WHERE token_id=? AND token_id IN '
        '(SELECT id FROM api_tokens WHERE usuario_id=?)',
        (token_id, uid)
    )
    conn.commit()
    conn.close()

    usuario = obter_usuario_por_id(uid)
    registrar_auditoria_admin(
        'token_revogado',
        usuario_afetado_id=uid,
        usuario_afetado_login=usuario['usuario'] if usuario else None,
        detalhe=f'Token OData "{info["nome"]}" (id={token_id}) revogado (estava ativo={info["ativo"]}).',
    )
    registrar_log('token_revogado', uid, session.get('usuario_nome'))

    return jsonify({'mensagem': 'Token revogado com sucesso.'}), 200


# ── OData endpoints (Power BI / Excel) ───────────────────────────────────────

# ═════════════════════════════════════════════════════════════════════════════
#                     OData v4 — Integração com Power BI
# ═════════════════════════════════════════════════════════════════════════════
# Todos os endpoints espelham 1:1 as colunas exportadas pelos downloads (CSV/Excel)
# de cada relatório. Paginação server-side via $top, $skip e $count.
# Autenticação: Bearer token (header Authorization ou query ?token=) + escopo
# explícito por relatório na tabela api_token_permissoes (fail-closed).

ODATA_MAX_PAGE_SIZE = 10000  # Power BI segue @odata.nextLink; páginas menores reduzem pico de RAM e latência por request.


_ODATA_METADATA_XML = '''<?xml version="1.0" encoding="utf-8"?>
<edmx:Edmx Version="4.0" xmlns:edmx="http://docs.oasis-open.org/odata/ns/edmx">
  <edmx:DataServices>
    <Schema Namespace="ProtheusData" xmlns="http://docs.oasis-open.org/odata/ns/edm">

      <!-- ─── Compras ─────────────────────────────────────────────────────── -->
      <EntityType Name="Pedido">
        <Key>
          <PropertyRef Name="filial"/>
          <PropertyRef Name="pedido_compra"/>
          <PropertyRef Name="item"/>
          <PropertyRef Name="nivel_aprovacao"/>
        </Key>
        <Property Name="usuario"           Type="Edm.String"/>
        <Property Name="filial"            Type="Edm.String" Nullable="false"/>
        <Property Name="pedido_compra"     Type="Edm.String" Nullable="false"/>
        <Property Name="item"              Type="Edm.String" Nullable="false"/>
        <Property Name="produto"           Type="Edm.String"/>
        <Property Name="unidade"           Type="Edm.String"/>
        <Property Name="descricao_produto" Type="Edm.String"/>
        <Property Name="quantidade"        Type="Edm.String"/>
        <Property Name="preco_unitario"    Type="Edm.String"/>
        <Property Name="preco_total"       Type="Edm.String"/>
        <Property Name="data_entrega"      Type="Edm.String"/>
        <Property Name="numero_sc"         Type="Edm.String"/>
        <Property Name="item_sc"           Type="Edm.String"/>
        <Property Name="observacoes"       Type="Edm.String"/>
        <Property Name="classe_valor"      Type="Edm.String"/>
        <Property Name="qtd_entregue"      Type="Edm.String"/>
        <Property Name="num_cotacao"       Type="Edm.String"/>
        <Property Name="moeda"             Type="Edm.String"/>
        <Property Name="cod_fornecedor"    Type="Edm.String"/>
        <Property Name="fornecedor"        Type="Edm.String"/>
        <Property Name="deposito_estoque"  Type="Edm.String"/>
        <Property Name="data_emissao"      Type="Edm.String"/>
        <Property Name="nivel_aprovacao"   Type="Edm.String" Nullable="false"/>
        <Property Name="aprovador"         Type="Edm.String"/>
        <Property Name="data_aprovacao"    Type="Edm.String"/>
        <Property Name="status_aprovacao"  Type="Edm.String"/>
      </EntityType>

      <EntityType Name="HistoricoPedido">
        <Key>
          <PropertyRef Name="filial"/>
          <PropertyRef Name="pedido_compra"/>
          <PropertyRef Name="item"/>
        </Key>
        <Property Name="usuario"           Type="Edm.String"/>
        <Property Name="filial"            Type="Edm.String" Nullable="false"/>
        <Property Name="pedido_compra"     Type="Edm.String" Nullable="false"/>
        <Property Name="item"              Type="Edm.String" Nullable="false"/>
        <Property Name="produto"           Type="Edm.String"/>
        <Property Name="descricao_produto" Type="Edm.String"/>
        <Property Name="quantidade"        Type="Edm.String"/>
        <Property Name="cod_fornecedor"    Type="Edm.String"/>
        <Property Name="fornecedor"        Type="Edm.String"/>
        <Property Name="deposito_estoque"  Type="Edm.String"/>
        <Property Name="data_emissao"      Type="Edm.String"/>
      </EntityType>

      <!-- ─── Estoque ─────────────────────────────────────────────────────── -->
      <EntityType Name="EstoqueSaldo">
        <Key>
          <PropertyRef Name="filial"/>
          <PropertyRef Name="armazem"/>
          <PropertyRef Name="produto"/>
        </Key>
        <Property Name="produto"             Type="Edm.String" Nullable="false"/>
        <Property Name="filial"              Type="Edm.String" Nullable="false"/>
        <Property Name="armazem"             Type="Edm.String" Nullable="false"/>
        <Property Name="saldo_atual"         Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="qtde_pedidos_venda"  Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="qtde_reserva"        Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="saldo_disponivel"    Type="Edm.Decimal" Precision="18" Scale="4"/>
      </EntityType>

      <!-- ─── Financeiro — NF de Entrada (SD1010) ─────────────────────────── -->
      <EntityType Name="NFEntrada">
        <Key><PropertyRef Name="recno"/></Key>
        <Property Name="recno"      Type="Edm.Int64" Nullable="false"/>
        <Property Name="D1_FILIAL"  Type="Edm.String"/>
        <Property Name="D1_DOC"     Type="Edm.String"/>
        <Property Name="D1_SERIE"   Type="Edm.String"/>
        <Property Name="D1_ITEM"    Type="Edm.String"/>
        <Property Name="D1_FORNECE" Type="Edm.String"/>
        <Property Name="D1_LOJA"    Type="Edm.String"/>
        <Property Name="D1_EMISSAO" Type="Edm.String"/>
        <Property Name="D1_DTDIGIT" Type="Edm.String"/>
        <Property Name="D1_COD"     Type="Edm.String"/>
        <Property Name="D1_DESC"    Type="Edm.String"/>
        <Property Name="D1_UM"      Type="Edm.String"/>
        <Property Name="D1_QUANT"   Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="D1_VUNIT"   Type="Edm.Decimal" Precision="18" Scale="6"/>
        <Property Name="D1_TOTAL"   Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D1_VALIPI"  Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D1_IPI"     Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="D1_VALICM"  Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D1_PICM"    Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="D1_TP"      Type="Edm.String"/>
        <Property Name="D1_TES"     Type="Edm.String"/>
        <Property Name="D1_CF"      Type="Edm.String"/>
        <Property Name="D1_GRUPO"   Type="Edm.String"/>
        <Property Name="D1_LOCAL"   Type="Edm.String"/>
        <Property Name="D1_PEDIDO"  Type="Edm.String"/>
        <Property Name="D1_ITEMPC"  Type="Edm.String"/>
        <Property Name="D1_VALDESC" Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D1_PESO"    Type="Edm.Decimal" Precision="18" Scale="4"/>
      </EntityType>

      <!-- ─── Financeiro — NF de Saída (SD2010) ───────────────────────────── -->
      <EntityType Name="NFSaida">
        <Key><PropertyRef Name="recno"/></Key>
        <Property Name="recno"      Type="Edm.Int64" Nullable="false"/>
        <Property Name="D2_FILIAL"  Type="Edm.String"/>
        <Property Name="D2_DOC"     Type="Edm.String"/>
        <Property Name="D2_SERIE"   Type="Edm.String"/>
        <Property Name="D2_ITEM"    Type="Edm.String"/>
        <Property Name="D2_CLIENTE" Type="Edm.String"/>
        <Property Name="D2_LOJA"    Type="Edm.String"/>
        <Property Name="D2_EMISSAO" Type="Edm.String"/>
        <Property Name="D2_DTDIGIT" Type="Edm.String"/>
        <Property Name="D2_COD"     Type="Edm.String"/>
        <Property Name="D2_DESC"    Type="Edm.String"/>
        <Property Name="D2_UM"      Type="Edm.String"/>
        <Property Name="D2_QUANT"   Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="D2_PRUNIT"  Type="Edm.Decimal" Precision="18" Scale="6"/>
        <Property Name="D2_PRCVEN"  Type="Edm.Decimal" Precision="18" Scale="6"/>
        <Property Name="D2_VALIPI"  Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D2_IPI"     Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="D2_VALICM"  Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D2_PICM"    Type="Edm.Decimal" Precision="18" Scale="4"/>
        <Property Name="D2_TP"      Type="Edm.String"/>
        <Property Name="D2_TES"     Type="Edm.String"/>
        <Property Name="D2_CF"      Type="Edm.String"/>
        <Property Name="D2_GRUPO"   Type="Edm.String"/>
        <Property Name="D2_LOCAL"   Type="Edm.String"/>
        <Property Name="D2_PEDIDO"  Type="Edm.String"/>
        <Property Name="D2_ITEMPV"  Type="Edm.String"/>
        <Property Name="D2_DESCON"  Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="D2_TIPO"    Type="Edm.String"/>
      </EntityType>

      <!-- ─── Financeiro — Contas a Receber (SE1010) ──────────────────────── -->
      <EntityType Name="ContasReceber">
        <Key><PropertyRef Name="recno"/></Key>
        <Property Name="recno"       Type="Edm.Int64" Nullable="false"/>
        <Property Name="E1_FILIAL"   Type="Edm.String"/>
        <Property Name="E1_PREFIXO"  Type="Edm.String"/>
        <Property Name="E1_NUM"      Type="Edm.String"/>
        <Property Name="E1_PARCELA"  Type="Edm.String"/>
        <Property Name="E1_TIPO"     Type="Edm.String"/>
        <Property Name="E1_CLIENTE"  Type="Edm.String"/>
        <Property Name="E1_LOJA"     Type="Edm.String"/>
        <Property Name="E1_NOMCLI"   Type="Edm.String"/>
        <Property Name="E1_EMISSAO"  Type="Edm.String"/>
        <Property Name="E1_VENCTO"   Type="Edm.String"/>
        <Property Name="E1_VENCREA"  Type="Edm.String"/>
        <Property Name="E1_VALOR"    Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="E1_SALDO"    Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="E1_BAIXA"    Type="Edm.String"/>
        <Property Name="E1_NATUREZ"  Type="Edm.String"/>
        <Property Name="E1_HIST"     Type="Edm.String"/>
        <Property Name="E1_STATUS"   Type="Edm.String"/>
        <Property Name="E1_SITUACA"  Type="Edm.String"/>
        <Property Name="E1_MOEDA"    Type="Edm.String"/>
        <Property Name="E1_PORTADO"  Type="Edm.String"/>
        <Property Name="E1_AGEDEP"   Type="Edm.String"/>
        <Property Name="E1_NUMNOTA"  Type="Edm.String"/>
        <Property Name="E1_SERIE"    Type="Edm.String"/>
        <Property Name="E1_MOTIVO"   Type="Edm.String"/>
      </EntityType>

      <!-- ─── Financeiro — Contas a Pagar (SE2010) ────────────────────────── -->
      <EntityType Name="ContasPagar">
        <Key><PropertyRef Name="recno"/></Key>
        <Property Name="recno"       Type="Edm.Int64" Nullable="false"/>
        <Property Name="E2_FILIAL"   Type="Edm.String"/>
        <Property Name="E2_PREFIXO"  Type="Edm.String"/>
        <Property Name="E2_NUM"      Type="Edm.String"/>
        <Property Name="E2_PARCELA"  Type="Edm.String"/>
        <Property Name="E2_TIPO"     Type="Edm.String"/>
        <Property Name="E2_FORNECE"  Type="Edm.String"/>
        <Property Name="E2_LOJA"     Type="Edm.String"/>
        <Property Name="E2_NOMFOR"   Type="Edm.String"/>
        <Property Name="E2_EMISSAO"  Type="Edm.String"/>
        <Property Name="E2_VENCTO"   Type="Edm.String"/>
        <Property Name="E2_VENCREA"  Type="Edm.String"/>
        <Property Name="E2_VALOR"    Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="E2_SALDO"    Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="E2_BAIXA"    Type="Edm.String"/>
        <Property Name="E2_NATUREZ"  Type="Edm.String"/>
        <Property Name="E2_HIST"     Type="Edm.String"/>
        <Property Name="E2_STATUS"   Type="Edm.String"/>
        <Property Name="E2_MOEDA"    Type="Edm.String"/>
        <Property Name="E2_BCOPAG"   Type="Edm.String"/>
        <Property Name="E2_MOTIVO"   Type="Edm.String"/>
        <Property Name="E2_RATEIO"   Type="Edm.String"/>
      </EntityType>

      <!-- ─── Financeiro — Movimentos Bancários (SE5010) ──────────────────── -->
      <EntityType Name="MovBancario">
        <Key><PropertyRef Name="recno"/></Key>
        <Property Name="recno"       Type="Edm.Int64" Nullable="false"/>
        <Property Name="E5_FILIAL"   Type="Edm.String"/>
        <Property Name="E5_BANCO"    Type="Edm.String"/>
        <Property Name="E5_AGENCIA"  Type="Edm.String"/>
        <Property Name="E5_CONTA"    Type="Edm.String"/>
        <Property Name="E5_DATA"     Type="Edm.String"/>
        <Property Name="E5_VALOR"    Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="E5_RECPAG"   Type="Edm.String"/>
        <Property Name="E5_NATUREZ"  Type="Edm.String"/>
        <Property Name="E5_HISTOR"   Type="Edm.String"/>
        <Property Name="E5_DOCUMEN"  Type="Edm.String"/>
        <Property Name="E5_TIPO"     Type="Edm.String"/>
        <Property Name="E5_TIPOLAN"  Type="Edm.String"/>
        <Property Name="E5_NUMCHEQ"  Type="Edm.String"/>
        <Property Name="E5_VENCTO"   Type="Edm.String"/>
        <Property Name="E5_BENEF"    Type="Edm.String"/>
        <Property Name="E5_PREFIXO"  Type="Edm.String"/>
        <Property Name="E5_NUMERO"   Type="Edm.String"/>
        <Property Name="E5_PARCELA"  Type="Edm.String"/>
        <Property Name="E5_CLIFOR"   Type="Edm.String"/>
        <Property Name="E5_LOJA"     Type="Edm.String"/>
        <Property Name="E5_MOTBX"    Type="Edm.String"/>
        <Property Name="E5_TIPODOC"  Type="Edm.String"/>
        <Property Name="E5_DTDIGIT"  Type="Edm.String"/>
      </EntityType>

      <!-- ─── Energy — Contas a Pagar (subset SE2010 do negócio Energy) ───── -->
      <!-- Colunas com nomes amigáveis (Filial, Vencimento, ...) preservando os aliases da query original -->
      <EntityType Name="EnergyContasPagar">
        <Key><PropertyRef Name="recno"/></Key>
        <Property Name="recno"               Type="Edm.Int64" Nullable="false"/>
        <Property Name="Filial"              Type="Edm.String"/>
        <Property Name="Prefixo"             Type="Edm.String"/>
        <Property Name="NumeroTitulo"        Type="Edm.String"/>
        <Property Name="Parcela"             Type="Edm.String"/>
        <Property Name="Tipo"                Type="Edm.String"/>
        <Property Name="Natureza"            Type="Edm.String"/>
        <Property Name="Negocio"             Type="Edm.String"/>
        <Property Name="Rastreamento"        Type="Edm.String"/>
        <Property Name="CentroCusto"         Type="Edm.String"/>
        <Property Name="Fornecedor"          Type="Edm.String"/>
        <Property Name="Loja"                Type="Edm.String"/>
        <Property Name="NomeFornecedor"      Type="Edm.String"/>
        <Property Name="DataEmissao"         Type="Edm.String"/>
        <Property Name="Vencimento"          Type="Edm.String"/>
        <Property Name="VencimentoReal"      Type="Edm.String"/>
        <Property Name="ValorTitulo"         Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="ISS"                 Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="IRRF"                Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="Databaixa"           Type="Edm.String"/>
        <Property Name="BancoPagamento"      Type="Edm.String"/>
        <Property Name="DataContabil"        Type="Edm.String"/>
        <Property Name="Historico"           Type="Edm.String"/>
        <Property Name="Saldo"               Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="Desconto"            Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="Multa"               Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="Juros"               Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="Correcao"            Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="ValorLiquidoBaixado" Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="VencimentoOriginal"  Type="Edm.String"/>
        <Property Name="Moeda"               Type="Edm.String"/>
        <Property Name="VlrEmReal"           Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="Acrescimo"           Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="DataLiberacao"       Type="Edm.String"/>
        <Property Name="TaxaMoeda"           Type="Edm.Decimal" Precision="18" Scale="6"/>
        <Property Name="Decrescimo"          Type="Edm.Decimal" Precision="18" Scale="2"/>
        <Property Name="FilialOrignal"       Type="Edm.String"/>
      </EntityType>

      <EntityType Name="EnergyPedido">
        <Key>
          <PropertyRef Name="filial"/>
          <PropertyRef Name="pedido_compra"/>
          <PropertyRef Name="item"/>
          <PropertyRef Name="nivel_aprovacao"/>
        </Key>
        <Property Name="usuario"           Type="Edm.String"/>
        <Property Name="filial"            Type="Edm.String" Nullable="false"/>
        <Property Name="pedido_compra"     Type="Edm.String" Nullable="false"/>
        <Property Name="item"              Type="Edm.String" Nullable="false"/>
        <Property Name="produto"           Type="Edm.String"/>
        <Property Name="unidade"           Type="Edm.String"/>
        <Property Name="descricao_produto" Type="Edm.String"/>
        <Property Name="quantidade"        Type="Edm.String"/>
        <Property Name="preco_unitario"    Type="Edm.String"/>
        <Property Name="preco_total"       Type="Edm.String"/>
        <Property Name="data_entrega"      Type="Edm.String"/>
        <Property Name="numero_sc"         Type="Edm.String"/>
        <Property Name="item_sc"           Type="Edm.String"/>
        <Property Name="observacoes"       Type="Edm.String"/>
        <Property Name="classe_valor"      Type="Edm.String"/>
        <Property Name="qtd_entregue"      Type="Edm.String"/>
        <Property Name="num_cotacao"       Type="Edm.String"/>
        <Property Name="moeda"             Type="Edm.String"/>
        <Property Name="cod_fornecedor"    Type="Edm.String"/>
        <Property Name="fornecedor"        Type="Edm.String"/>
        <Property Name="deposito_estoque"  Type="Edm.String"/>
        <Property Name="data_emissao"      Type="Edm.String"/>
        <Property Name="nivel_aprovacao"   Type="Edm.String" Nullable="false"/>
        <Property Name="aprovador"         Type="Edm.String"/>
        <Property Name="data_aprovacao"    Type="Edm.String"/>
        <Property Name="status_aprovacao"  Type="Edm.String"/>
      </EntityType>

      <EntityContainer Name="ProtheusDataService">
        <EntitySet Name="Pedidos"           EntityType="ProtheusData.Pedido"/>
        <EntitySet Name="EnergyPedidos"     EntityType="ProtheusData.EnergyPedido"/>
        <EntitySet Name="Estoque"           EntityType="ProtheusData.EstoqueSaldo"/>
        <EntitySet Name="HistoricoPedidos"  EntityType="ProtheusData.HistoricoPedido"/>
        <EntitySet Name="NFEntrada"         EntityType="ProtheusData.NFEntrada"/>
        <EntitySet Name="NFSaida"           EntityType="ProtheusData.NFSaida"/>
        <EntitySet Name="ContasReceber"     EntityType="ProtheusData.ContasReceber"/>
        <EntitySet Name="ContasPagar"       EntityType="ProtheusData.ContasPagar"/>
        <EntitySet Name="MovBancarios"      EntityType="ProtheusData.MovBancario"/>
        <EntitySet Name="EnergyContasPagar" EntityType="ProtheusData.EnergyContasPagar"/>
      </EntityContainer>

    </Schema>
  </edmx:DataServices>
</edmx:Edmx>'''


def _token_da_request():
    auth = request.headers.get('Authorization', '')
    if auth.startswith('Bearer '):
        return auth[7:]
    return request.args.get('token') or ''


def _odata_error(mensagem, status):
    return Response(
        json.dumps({'error': {'code': str(status), 'message': mensagem}}, ensure_ascii=False),
        status=status,
        mimetype='application/json',
        headers={'OData-Version': '4.0'},
    )


def _autorizar_odata(modulo_id, relatorio_id, titulo_relatorio):
    """Retorna (usuario, None) em caso de sucesso ou (None, Response) com erro OData."""
    usuario = validar_api_token(_token_da_request())
    if not usuario:
        _auditar_odata_rejeitada(
            modulo_id, relatorio_id,
            motivo='token_invalido',
            usuario_id=None, usuario_nome=None,
        )
        return None, _odata_error('Token inválido ou expirado.', 401)
    if not usuario_tem_acesso_relatorio(usuario, modulo_id, relatorio_id):
        _auditar_odata_rejeitada(
            modulo_id, relatorio_id,
            motivo='sem_permissao_usuario',
            usuario_id=usuario['id'], usuario_nome=usuario['nome'],
        )
        return None, _odata_error(f'Sem permissão para o relatório de {titulo_relatorio}.', 403)
    if not token_tem_acesso_relatorio(g.api_token_id, modulo_id, relatorio_id):
        _auditar_odata_rejeitada(
            modulo_id, relatorio_id,
            motivo='token_sem_escopo',
            usuario_id=usuario['id'], usuario_nome=usuario['nome'],
        )
        return None, _odata_error(
            f'Este token não tem escopo para o relatório de {titulo_relatorio}.', 403,
        )
    return usuario, None


def _auditar_odata_rejeitada(modulo_id, relatorio_id, motivo, usuario_id=None, usuario_nome=None):
    """Registra tentativas rejeitadas de acesso a endpoints OData.
    Importante para detectar brute force, token vazado, ou permissão revogada."""
    try:
        acao = f'odata_rejeitada_{motivo}_{modulo_id}_{relatorio_id}'
        conn = conectar_users()
        conn.execute(
            'INSERT INTO logs_acesso (usuario_id, usuario_nome, acao, ip, data_hora) '
            'VALUES (?, ?, ?, ?, ?)',
            (usuario_id, usuario_nome, acao, _obter_ip_real(), agora())
        )
        conn.commit()
        conn.close()
    except Exception:
        pass


def _parse_int_param(nome, default=None, minimo=None, maximo=None):
    bruto = request.args.get(nome)
    if bruto is None or bruto == '':
        return default
    try:
        valor = int(bruto)
    except (TypeError, ValueError):
        return default
    if minimo is not None and valor < minimo:
        valor = minimo
    if maximo is not None and valor > maximo:
        valor = maximo
    return valor


def _parse_bool_param(nome, default=False):
    bruto = (request.args.get(nome) or '').strip().lower()
    if not bruto:
        return default
    return bruto in ('true', '1', 'yes')


def _converter_valor_odata(valor):
    """Normaliza o valor para serialização JSON compatível com o EDMX.
    Datas/strings vêm como str; decimais/floats como número; None permanece None.
    """
    if valor is None:
        return None
    if isinstance(valor, (int, float)):
        return valor
    if isinstance(valor, str):
        return valor.strip()
    return str(valor)


_ODATA_OPERADORES = {
    'eq': '=', 'ne': '<>', 'gt': '>', 'ge': '>=', 'lt': '<', 'le': '<=',
}
# Cada cláusula é: identifier OP literal[ ('and'|'or') identifier OP literal]*
# Identifier deve estar na whitelist de colunas. Literal é string ou número.
# Nada de funções, parênteses aninhados ou sub-queries.
_ODATA_COMPARACAO_RE = re.compile(
    r"(?P<col>[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<op>eq|ne|ge|gt|le|lt)\s+"
    r"(?P<lit>'(?:[^']|'')*'|-?\d+(?:\.\d+)?)",
    re.IGNORECASE,
)
_ODATA_LIGADOR_RE = re.compile(r"\s+(and|or)\s+", re.IGNORECASE)


def _parse_odata_filter(filtro_raw, colunas_validas):
    """Converte um $filter OData mínimo em (WHERE-clause, params) seguro.

    Suporte intencional (whitelist):
      - operadores: eq, ne, ge, gt, le, lt
      - combinadores: and, or (sem parênteses)
      - identificadores: apenas os que estão em `colunas_validas`
      - literais: string entre aspas simples ('texto' / 'data''escapada') ou
        número (int/float)

    Tudo o que NÃO casa exatamente com o gramatical é rejeitado com ValueError.
    Os literais sempre vão como bind parameter (`?`); colunas são validadas
    contra a whitelist (não vão por bind, mas estão em set fechado).
    """
    if not filtro_raw:
        return '', []
    filtro = filtro_raw.strip()
    if not filtro:
        return '', []
    if len(filtro) > 1000:
        raise ValueError('$filter muito grande')

    pedacos = []
    posicao = 0
    primeira = True

    while posicao < len(filtro):
        m = _ODATA_COMPARACAO_RE.match(filtro, posicao)
        if not m:
            raise ValueError(f'$filter mal formado em "{filtro[posicao:posicao+40]}"')
        col = m.group('col')
        if col not in colunas_validas:
            raise ValueError(f'$filter: coluna desconhecida "{col}"')
        op_sql = _ODATA_OPERADORES[m.group('op').lower()]
        literal = m.group('lit')
        if literal.startswith("'"):
            valor = literal[1:-1].replace("''", "'")
        else:
            valor = float(literal) if '.' in literal else int(literal)
        if primeira:
            pedacos.append(f'{col} {op_sql} ?')
            primeira = False
        else:
            # Já consumimos um ligador antes desse match
            pedacos[-1] = f'{pedacos[-1]} {col} {op_sql} ?'  # nunca chega aqui
        posicao = m.end()

        # Próximo: ligador and/or, ou fim
        if posicao >= len(filtro):
            break
        m_lig = _ODATA_LIGADOR_RE.match(filtro, posicao)
        if not m_lig:
            raise ValueError(f'$filter: esperado AND/OR após "{filtro[:posicao]}"')
        pedacos.append(m_lig.group(1).upper())
        posicao = m_lig.end()
        primeira = True  # próxima iteração começa um novo termo

    # Reconstrói WHERE: comparações e ligadores intercalados
    # A lista pedacos contém: comp, lig, comp, lig, comp, ...
    where = ' '.join(pedacos)
    # extrai params na mesma ordem das comparações
    params = []
    for m in _ODATA_COMPARACAO_RE.finditer(filtro):
        literal = m.group('lit')
        if literal.startswith("'"):
            params.append(literal[1:-1].replace("''", "'"))
        else:
            params.append(float(literal) if '.' in literal else int(literal))
    return where, params


def _odata_paged_response(
    entity_name,
    conectar_fn,
    tabela,
    colunas,
    order_by,
    url_path,
):
    """Executa SELECT paginado no SQLite e devolve o payload OData v4.

    Parâmetros OData suportados: $top, $skip, $count, $filter (whitelist mínima).
    O limite de página é `ODATA_MAX_PAGE_SIZE`; se `$top` exceder, aplicamos
    `ODATA_MAX_PAGE_SIZE` e retornamos `@odata.nextLink` automaticamente.
    O Power BI segue `@odata.nextLink` sem intervenção do usuário.
    """
    skip = _parse_int_param('$skip', default=0, minimo=0) or 0
    top_solicitado = _parse_int_param('$top', default=None, minimo=1)
    quer_count = _parse_bool_param('$count', default=False)

    filtro_raw = (request.args.get('$filter') or '').strip()
    try:
        where_extra, where_params = _parse_odata_filter(filtro_raw, set(colunas))
    except ValueError as e:
        return Response(
            json.dumps({'error': {'code': 'invalid_filter', 'message': str(e)}}),
            status=400,
            mimetype='application/json',
        )

    page_size = (
        min(top_solicitado, ODATA_MAX_PAGE_SIZE)
        if top_solicitado is not None
        else ODATA_MAX_PAGE_SIZE
    )

    colunas_sql = ', '.join(colunas)
    where_sql = f' WHERE {where_extra}' if where_extra else ''
    sql = f'SELECT {colunas_sql} FROM {tabela}{where_sql} ORDER BY {order_by} LIMIT ? OFFSET ?'

    conn = conectar_fn()
    try:
        rows = conn.execute(sql, (*where_params, page_size, skip)).fetchall()
        total = None
        if quer_count:
            count_sql = f'SELECT COUNT(*) FROM {tabela}{where_sql}'
            total = conn.execute(count_sql, where_params).fetchone()[0]
    finally:
        conn.close()

    dados = [
        {coluna: _converter_valor_odata(linha[coluna]) for coluna in colunas}
        for linha in rows
    ]

    base = request.url_root.rstrip('/')
    payload = {
        '@odata.context': f'{base}/odata/$metadata#{entity_name}',
    }
    if quer_count and total is not None:
        payload['@odata.count'] = total
    payload['value'] = dados

    # Paginação server-side: quando cheia uma página, aponta para a próxima.
    # Respeita o limite máximo solicitado pelo cliente via $top, se houver.
    retornou_cheia = len(rows) == page_size
    ainda_pode_paginar = (
        top_solicitado is None or (skip + len(rows)) < top_solicitado
    )
    if retornou_cheia and ainda_pode_paginar:
        proximo_skip = skip + page_size
        query = request.args.to_dict(flat=True)
        query['$skip'] = str(proximo_skip)
        if top_solicitado is not None:
            # Reduz o $top restante para não ultrapassar o pedido original.
            restante = top_solicitado - (skip + len(rows))
            if restante <= 0:
                restante = None
            if restante is not None:
                query['$top'] = str(restante)
        # Preserva o token só se veio por query string, nunca por header.
        if '$count' in query:
            query.pop('$count', None)  # $count só na primeira página
        qs = '&'.join(f'{k}={v}' for k, v in query.items())
        payload['@odata.nextLink'] = f'{base}{url_path}?{qs}' if qs else f'{base}{url_path}'

    return Response(
        json.dumps(payload, ensure_ascii=False, default=str),
        mimetype='application/json;odata.metadata=minimal',
        headers={'OData-Version': '4.0'},
    )


@app.route('/odata/')
@app.route('/odata')
def odata_service_document():
    """Service document — necessário para o Power BI descobrir os EntitySets."""
    base = request.url_root.rstrip('/')
    payload = {
        '@odata.context': f'{base}/odata/$metadata',
        'value': [
            {'name': 'Pedidos',          'kind': 'EntitySet', 'url': 'pedidos'},
            {'name': 'EnergyPedidos',    'kind': 'EntitySet', 'url': 'energy-pedidos'},
            {'name': 'Estoque',          'kind': 'EntitySet', 'url': 'estoque'},
            {'name': 'HistoricoPedidos', 'kind': 'EntitySet', 'url': 'historico-pedidos'},
            {'name': 'NFEntrada',        'kind': 'EntitySet', 'url': 'nf-entrada'},
            {'name': 'NFSaida',          'kind': 'EntitySet', 'url': 'nf-saida'},
            {'name': 'ContasReceber',    'kind': 'EntitySet', 'url': 'contas-receber'},
            {'name': 'ContasPagar',      'kind': 'EntitySet', 'url': 'contas-pagar'},
            {'name': 'MovBancarios',     'kind': 'EntitySet', 'url': 'mov-bancarios'},
            {'name': 'EnergyContasPagar','kind': 'EntitySet', 'url': 'energy-contas-pagar'},
        ],
    }
    return Response(
        json.dumps(payload, ensure_ascii=False),
        mimetype='application/json;odata.metadata=minimal',
        headers={'OData-Version': '4.0'}
    )


@app.route('/odata/$metadata')
def odata_metadata():
    """Esquema EDMX — o Power BI busca este endpoint antes de carregar os dados."""
    return Response(
        _ODATA_METADATA_XML.strip(),
        mimetype='application/xml',
        headers={'OData-Version': '4.0'}
    )


# ─── Compras ─────────────────────────────────────────────────────────────────

_ODATA_PEDIDOS_COLUNAS = [
    'usuario', 'filial', 'pedido_compra', 'item', 'produto', 'unidade',
    'descricao_produto', 'quantidade', 'preco_unitario', 'preco_total',
    'data_entrega', 'numero_sc', 'item_sc', 'observacoes', 'classe_valor',
    'qtd_entregue', 'num_cotacao', 'moeda', 'cod_fornecedor', 'fornecedor',
    'deposito_estoque', 'data_emissao', 'nivel_aprovacao', 'aprovador',
    'data_aprovacao', 'status_aprovacao',
]


@app.route('/odata/pedidos')
def odata_pedidos():
    _, erro = _autorizar_odata('compras', 'pedidos', 'Pedidos de Compra')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='Pedidos',
        conectar_fn=conectar_pedidos,
        tabela='pedidos',
        colunas=_ODATA_PEDIDOS_COLUNAS,
        order_by='data_emissao DESC, pedido_compra, item, nivel_aprovacao',
        url_path='/odata/pedidos',
    )


_ODATA_ENERGY_PEDIDOS_COLUNAS = [
    'usuario', 'filial', 'pedido_compra', 'item', 'produto', 'unidade',
    'descricao_produto', 'quantidade', 'preco_unitario', 'preco_total',
    'data_entrega', 'numero_sc', 'item_sc', 'observacoes', 'classe_valor',
    'qtd_entregue', 'num_cotacao', 'moeda', 'cod_fornecedor', 'fornecedor',
    'deposito_estoque', 'data_emissao', 'nivel_aprovacao', 'aprovador',
    'data_aprovacao', 'status_aprovacao',
]


@app.route('/odata/energy-pedidos')
def odata_energy_pedidos():
    _, erro = _autorizar_odata('energy', 'pedidos', 'Pedidos Energy')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='EnergyPedidos',
        conectar_fn=conectar_pedidos,
        tabela='pedidos_energy',
        colunas=_ODATA_ENERGY_PEDIDOS_COLUNAS,
        order_by='data_emissao DESC, pedido_compra, item, nivel_aprovacao',
        url_path='/odata/energy-pedidos',
    )


_ODATA_HISTORICO_COLUNAS = [
    'usuario', 'filial', 'pedido_compra', 'item', 'produto',
    'descricao_produto', 'quantidade', 'cod_fornecedor', 'fornecedor',
    'deposito_estoque', 'data_emissao',
]


@app.route('/odata/historico-pedidos')
def odata_historico_pedidos():
    _, erro = _autorizar_odata('compras', 'historico', 'Histórico de Pedidos')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='HistoricoPedidos',
        conectar_fn=conectar_pedidos,
        tabela='pedidos_historico',
        colunas=_ODATA_HISTORICO_COLUNAS,
        order_by='data_emissao DESC, pedido_compra, item',
        url_path='/odata/historico-pedidos',
    )


# ─── Estoque ─────────────────────────────────────────────────────────────────

_ODATA_ESTOQUE_COLUNAS = [
    'produto', 'filial', 'armazem',
    'saldo_atual', 'qtde_pedidos_venda', 'qtde_reserva', 'saldo_disponivel',
]


@app.route('/odata/estoque')
def odata_estoque():
    _, erro = _autorizar_odata('estoque', 'saldos', 'Estoque')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='Estoque',
        conectar_fn=conectar_pedidos,
        tabela='estoque_saldos',
        colunas=_ODATA_ESTOQUE_COLUNAS,
        order_by='filial, armazem, produto',
        url_path='/odata/estoque',
    )


# ─── Financeiro — NF de Entrada (SD1010) ─────────────────────────────────────

_ODATA_NF_ENTRADA_COLUNAS = [
    'recno',
    'D1_FILIAL', 'D1_DOC', 'D1_SERIE', 'D1_ITEM',
    'D1_FORNECE', 'D1_LOJA',
    'D1_EMISSAO', 'D1_DTDIGIT',
    'D1_COD', 'D1_DESC', 'D1_UM',
    'D1_QUANT', 'D1_VUNIT', 'D1_TOTAL',
    'D1_VALIPI', 'D1_IPI', 'D1_VALICM', 'D1_PICM',
    'D1_TP', 'D1_TES', 'D1_CF',
    'D1_GRUPO', 'D1_LOCAL',
    'D1_PEDIDO', 'D1_ITEMPC',
    'D1_VALDESC', 'D1_PESO',
]


@app.route('/odata/nf-entrada')
def odata_nf_entrada():
    _, erro = _autorizar_odata('financeiro', 'nf_entrada', 'NF de Entrada')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='NFEntrada',
        conectar_fn=conectar_financeiro,
        tabela='nf_entrada_itens',
        colunas=_ODATA_NF_ENTRADA_COLUNAS,
        order_by='D1_EMISSAO DESC, recno',
        url_path='/odata/nf-entrada',
    )


# ─── Financeiro — NF de Saída (SD2010) ───────────────────────────────────────

_ODATA_NF_SAIDA_COLUNAS = [
    'recno',
    'D2_FILIAL', 'D2_DOC', 'D2_SERIE', 'D2_ITEM',
    'D2_CLIENTE', 'D2_LOJA',
    'D2_EMISSAO', 'D2_DTDIGIT',
    'D2_COD', 'D2_DESC', 'D2_UM',
    'D2_QUANT', 'D2_PRUNIT', 'D2_PRCVEN',
    'D2_VALIPI', 'D2_IPI', 'D2_VALICM', 'D2_PICM',
    'D2_TP', 'D2_TES', 'D2_CF',
    'D2_GRUPO', 'D2_LOCAL',
    'D2_PEDIDO', 'D2_ITEMPV',
    'D2_DESCON', 'D2_TIPO',
]


@app.route('/odata/nf-saida')
def odata_nf_saida():
    _, erro = _autorizar_odata('financeiro', 'nf_saida', 'NF de Saída')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='NFSaida',
        conectar_fn=conectar_financeiro,
        tabela='nf_saida_itens',
        colunas=_ODATA_NF_SAIDA_COLUNAS,
        order_by='D2_EMISSAO DESC, recno',
        url_path='/odata/nf-saida',
    )


# ─── Financeiro — Contas a Receber (SE1010) ──────────────────────────────────

_ODATA_CONTAS_RECEBER_COLUNAS = [
    'recno',
    'E1_FILIAL', 'E1_PREFIXO', 'E1_NUM', 'E1_PARCELA', 'E1_TIPO',
    'E1_CLIENTE', 'E1_LOJA', 'E1_NOMCLI',
    'E1_EMISSAO', 'E1_VENCTO', 'E1_VENCREA',
    'E1_VALOR', 'E1_SALDO', 'E1_BAIXA',
    'E1_NATUREZ', 'E1_HIST',
    'E1_STATUS', 'E1_SITUACA', 'E1_MOEDA',
    'E1_PORTADO', 'E1_AGEDEP',
    'E1_NUMNOTA', 'E1_SERIE', 'E1_MOTIVO',
]


@app.route('/odata/contas-receber')
def odata_contas_receber():
    _, erro = _autorizar_odata('financeiro', 'contas_receber', 'Contas a Receber')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='ContasReceber',
        conectar_fn=conectar_financeiro,
        tabela='contas_receber',
        colunas=_ODATA_CONTAS_RECEBER_COLUNAS,
        order_by='E1_VENCTO DESC, recno',
        url_path='/odata/contas-receber',
    )


# ─── Financeiro — Contas a Pagar (SE2010) ────────────────────────────────────

_ODATA_CONTAS_PAGAR_COLUNAS = [
    'recno',
    'E2_FILIAL', 'E2_PREFIXO', 'E2_NUM', 'E2_PARCELA', 'E2_TIPO',
    'E2_FORNECE', 'E2_LOJA', 'E2_NOMFOR',
    'E2_EMISSAO', 'E2_VENCTO', 'E2_VENCREA',
    'E2_VALOR', 'E2_SALDO', 'E2_BAIXA',
    'E2_NATUREZ', 'E2_HIST',
    'E2_STATUS', 'E2_MOEDA',
    'E2_BCOPAG', 'E2_MOTIVO', 'E2_RATEIO',
]


@app.route('/odata/contas-pagar')
def odata_contas_pagar():
    _, erro = _autorizar_odata('financeiro', 'contas_pagar', 'Contas a Pagar')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='ContasPagar',
        conectar_fn=conectar_financeiro,
        tabela='contas_pagar',
        colunas=_ODATA_CONTAS_PAGAR_COLUNAS,
        order_by='E2_VENCTO DESC, recno',
        url_path='/odata/contas-pagar',
    )


# ─── Financeiro — Movimentos Bancários (SE5010) ──────────────────────────────

_ODATA_MOV_BANCARIOS_COLUNAS = [
    'recno',
    'E5_FILIAL', 'E5_BANCO', 'E5_AGENCIA', 'E5_CONTA',
    'E5_DATA', 'E5_VALOR', 'E5_RECPAG',
    'E5_NATUREZ', 'E5_HISTOR', 'E5_DOCUMEN',
    'E5_TIPO', 'E5_TIPOLAN', 'E5_NUMCHEQ',
    'E5_VENCTO', 'E5_BENEF',
    'E5_PREFIXO', 'E5_NUMERO', 'E5_PARCELA',
    'E5_CLIFOR', 'E5_LOJA',
    'E5_MOTBX', 'E5_TIPODOC', 'E5_DTDIGIT',
]


@app.route('/odata/mov-bancarios')
def odata_mov_bancarios():
    _, erro = _autorizar_odata('financeiro', 'mov_bancarios', 'Movimentos Bancários')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='MovBancarios',
        conectar_fn=conectar_financeiro,
        tabela='mov_bancarios',
        colunas=_ODATA_MOV_BANCARIOS_COLUNAS,
        order_by='E5_DATA DESC, recno',
        url_path='/odata/mov-bancarios',
    )


# ─── Energy — Contas a Pagar (subset SE2010 do negócio Energy) ──────────────

_ODATA_ENERGY_CONTAS_PAGAR_COLUNAS = [
    'recno',
    'Filial', 'Prefixo', 'NumeroTitulo', 'Parcela', 'Tipo',
    'Natureza', 'Negocio', 'Rastreamento', 'CentroCusto',
    'Fornecedor', 'Loja', 'NomeFornecedor',
    'DataEmissao', 'Vencimento', 'VencimentoReal',
    'ValorTitulo', 'ISS', 'IRRF', 'Databaixa',
    'BancoPagamento', 'DataContabil', 'Historico',
    'Saldo', 'Desconto', 'Multa', 'Juros', 'Correcao',
    'ValorLiquidoBaixado', 'VencimentoOriginal', 'Moeda', 'VlrEmReal',
    'Acrescimo', 'DataLiberacao', 'TaxaMoeda', 'Decrescimo', 'FilialOrignal',
]


@app.route('/odata/energy-contas-pagar')
def odata_energy_contas_pagar():
    _, erro = _autorizar_odata('energy', 'contas_pagar', 'Energy — Contas a Pagar')
    if erro:
        return erro
    return _odata_paged_response(
        entity_name='EnergyContasPagar',
        conectar_fn=conectar_financeiro,
        tabela='energy_contas_pagar',
        colunas=_ODATA_ENERGY_CONTAS_PAGAR_COLUNAS,
        order_by='Vencimento DESC, recno',
        url_path='/odata/energy-contas-pagar',
    )


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
    invalidar_cache_permissoes()
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
        '''SELECT usuario_id, modulo_id, relatorio_id
           FROM usuario_permissoes_relatorio
           WHERE COALESCE(permitido, 1) = 1
             AND usuario_id IN (
               SELECT id FROM usuarios WHERE setor_id=? AND COALESCE(is_admin,0)=0
             )''',
        (setor_id,)
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

    perms_antes = obter_relatorios_permitidos(usuario_id)

    conn = conectar_users()
    salvar_permissoes_usuario(conn, usuario_id, permissoes)
    conn.commit()
    conn.close()

    adicionadas = sorted(permissoes - perms_antes)
    removidas   = sorted(perms_antes - permissoes)
    registrar_auditoria_admin(
        'gerente_atualizou_permissoes',
        usuario_afetado_id=usuario_id,
        usuario_afetado_login=alvo['usuario'],
        antes={'permissoes': sorted(perms_antes)},
        depois={'permissoes': sorted(permissoes)},
        detalhe=(
            f'Permissões ajustadas pelo gerente. '
            f'Adicionadas: {adicionadas or "[]"} | Removidas: {removidas or "[]"}.'
        ),
    )
    return jsonify({'mensagem': 'Permissões atualizadas.'}), 200



@app.route('/cadastro')
def pagina_cadastro():
    return redirect('/login')


@app.route('/api/login', methods=['POST'])
def api_login():
    ip = _obter_ip_real()

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


def _historico_sync_response(historico_fn):
    """Helper compartilhado para rotas de histórico de sync com paginação."""
    try:
        limite = min(max(int(request.args.get('limit', 10)), 1), 50)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (TypeError, ValueError):
        limite, offset = 10, 0
    try:
        linhas = historico_fn(limit=limite + 1, offset=offset)
        tem_mais = len(linhas) > limite
        if tem_mais:
            linhas = linhas[:limite]
        historico = []
        for linha in linhas:
            executado_em = linha['executado_em']
            if executado_em:
                executado_em = parse_db_datetime(executado_em).strftime('%d/%m/%Y %H:%M')
            historico.append({
                'executado_em': executado_em or '--',
                'registros_novos': linha['registros_novos'],
            })
        return jsonify({'historico': historico, 'tem_mais': tem_mais})
    except Exception:
        return jsonify({'erro': 'Falha ao carregar histórico de sincronização.'}), 500


@app.route('/api/relatorios/compras/pedidos/historico-sync', methods=['GET'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_historico_sync():
    return _historico_sync_response(historico_sync_pedidos)


@app.route('/api/relatorios/estoque/saldos/historico-sync', methods=['GET'])
@acesso_relatorio_requerido('estoque', 'saldos')
def api_historico_sync_estoque():
    return _historico_sync_response(historico_sync_estoque)


@app.route('/api/relatorios/compras/pedidos/download', methods=['GET'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_relatorio_download():
    formato = request.args.get('formato', 'csv').lower()
    data_inicio = _iso_para_protheus(request.args.get('data_inicio'))
    data_fim = _iso_para_protheus(request.args.get('data_fim'))

    try:
        if formato == 'excel':
            dados, total = gerar_excel_pedidos(data_inicio=data_inicio, data_fim=data_fim)
            registrar_log('download_excel', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download(formato, total)
            return Response(
                dados,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment; filename=pedidos_compra.xlsx'}
            )
        else:
            dados, total = gerar_csv_pedidos(data_inicio=data_inicio, data_fim=data_fim)
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


@app.route('/api/relatorios/compras/pedidos/sync', methods=['POST'])
@acesso_relatorio_requerido('compras', 'pedidos')
def api_relatorio_sync():
    global ultimo_sync_dt
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Já existe uma sincronização em andamento.'}), 409
    t0 = time.monotonic()
    try:
        novos = sincronizar_pedidos()
        duracao = round(time.monotonic() - t0)
        ultimo_sync_dt = agora_sp()
        criar_backup_diario()
        limpar_logs_antigos()
        registrar_log('sync_manual', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {novos} registro(s) novo(s).',
            'registros_novos': novos,
            'duracao_segundos': duracao,
        })
    except Exception as e:
        registrar_sync_event_pedidos(0, 'erro', str(e)[:180])
        return jsonify({'erro': _classificar_erro_sync(e)}), 500
    finally:
        sync_lock.release()


@app.route('/api/relatorios/estoque/saldos/sync', methods=['POST'])
@acesso_relatorio_requerido('estoque', 'saldos')
def api_relatorio_estoque_sync():
    global ultimo_sync_dt
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Já existe uma sincronização em andamento.'}), 409
    t0 = time.monotonic()
    try:
        alterados = sincronizar_estoque()
        duracao = round(time.monotonic() - t0)
        ultimo_sync_dt = agora_sp()
        criar_backup_diario()
        limpar_logs_antigos()
        registrar_log('sync_manual_estoque', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {alterados} registro(s) alterado(s).',
            'registros_novos': alterados,
            'duracao_segundos': duracao,
        })
    except Exception as e:
        registrar_sync_event_estoque(0, 'erro', str(e)[:180])
        return jsonify({'erro': _classificar_erro_sync(e)}), 500
    finally:
        sync_lock.release()


@app.route('/api/relatorios/energy/pedidos/info', methods=['GET'])
@acesso_relatorio_requerido('energy', 'pedidos')
def api_relatorio_energy_pedidos_info():
    try:
        total, ultimo_sync, ultimo_sync_status, ultimo_sync_erro = info_relatorio_pedidos_energy()
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
            'alerta': 'Divergência detectada',
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


@app.route('/api/relatorios/energy/pedidos/historico-sync', methods=['GET'])
@acesso_relatorio_requerido('energy', 'pedidos')
def api_historico_sync_energy_pedidos():
    return _historico_sync_response(historico_sync_pedidos_energy)


@app.route('/api/relatorios/energy/pedidos/download', methods=['GET'])
@acesso_relatorio_requerido('energy', 'pedidos')
def api_relatorio_energy_pedidos_download():
    formato = request.args.get('formato', 'csv').lower()
    data_inicio = _iso_para_protheus(request.args.get('data_inicio'))
    data_fim    = _iso_para_protheus(request.args.get('data_fim'))

    try:
        if formato == 'excel':
            dados, total = gerar_excel_pedidos_energy(data_inicio=data_inicio, data_fim=data_fim)
            registrar_log('download_energy_pedidos_excel', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download(formato, total)
            return Response(
                dados,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment; filename=pedidos_energy.xlsx'}
            )
        else:
            dados, total = gerar_csv_pedidos_energy(data_inicio=data_inicio, data_fim=data_fim)
            registrar_log('download_energy_pedidos_csv', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download(formato, total)
            return Response(
                dados,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=pedidos_energy.csv'}
            )
    except Exception:
        return jsonify({'erro': 'Falha ao gerar relatório.'}), 500


@app.route('/api/relatorios/energy/pedidos/sync', methods=['POST'])
@acesso_relatorio_requerido('energy', 'pedidos')
def api_relatorio_energy_pedidos_sync():
    global ultimo_sync_dt
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Já existe uma sincronização em andamento.'}), 409
    t0 = time.monotonic()
    try:
        novos = sincronizar_pedidos_energy()
        duracao = round(time.monotonic() - t0)
        ultimo_sync_dt = agora_sp()
        criar_backup_diario()
        limpar_logs_antigos()
        registrar_log('sync_manual_energy_pedidos', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {novos} registro(s) novo(s).',
            'registros_novos': novos,
            'duracao_segundos': duracao,
        })
    except Exception as e:
        registrar_sync_event_pedidos_energy(0, 'erro', str(e)[:180])
        return jsonify({'erro': _classificar_erro_sync(e)}), 500
    finally:
        sync_lock.release()


@app.route('/api/relatorios/compras/historico/info', methods=['GET'])
@acesso_relatorio_requerido('compras', 'historico')
def api_relatorio_historico_info():
    try:
        total, ultimo_sync, ultimo_sync_status, ultimo_sync_erro = info_relatorio_historico()
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
            'alerta': 'Divergência detectada',
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


@app.route('/api/relatorios/compras/historico/historico-sync', methods=['GET'])
@acesso_relatorio_requerido('compras', 'historico')
def api_historico_sync_historico():
    return _historico_sync_response(historico_sync_historico)


@app.route('/api/relatorios/compras/historico/download', methods=['GET'])
@acesso_relatorio_requerido('compras', 'historico')
def api_relatorio_historico_download():
    formato = request.args.get('formato', 'csv').lower()
    data_inicio = _iso_para_protheus(request.args.get('data_inicio'))
    data_fim = _iso_para_protheus(request.args.get('data_fim'))

    try:
        if formato == 'excel':
            dados, total = gerar_excel_historico(data_inicio=data_inicio, data_fim=data_fim)
            registrar_log('download_historico_excel', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download_historico(formato, total)
            return Response(
                dados,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': 'attachment; filename=historico_pedidos.xlsx'}
            )
        else:
            dados, total = gerar_csv_historico(data_inicio=data_inicio, data_fim=data_fim)
            registrar_log('download_historico_csv', session.get('usuario_id'), session.get('usuario_nome'))
            registrar_download_historico(formato, total)
            return Response(
                dados,
                mimetype='text/csv',
                headers={'Content-Disposition': 'attachment; filename=historico_pedidos.csv'}
            )
    except Exception:
        return jsonify({'erro': 'Falha ao gerar relatório.'}), 500


@app.route('/api/relatorios/compras/historico/sync', methods=['POST'])
@acesso_relatorio_requerido('compras', 'historico')
def api_relatorio_historico_sync():
    global ultimo_sync_dt
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Já existe uma sincronização em andamento.'}), 409
    t0 = time.monotonic()
    try:
        novos = sincronizar_historico()
        duracao = round(time.monotonic() - t0)
        ultimo_sync_dt = agora_sp()
        criar_backup_diario()
        limpar_logs_antigos()
        registrar_log('sync_manual_historico', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {novos} registro(s) novo(s).',
            'registros_novos': novos,
            'duracao_segundos': duracao,
        })
    except Exception as e:
        registrar_sync_event_historico(0, 'erro', str(e)[:180])
        return jsonify({'erro': _classificar_erro_sync(e)}), 500
    finally:
        sync_lock.release()


# ══════════════════════════════════════════════════════════════════════════════
# MÓDULO FINANCEIRO — 5 relatórios (NF Entrada, NF Saída, CR, CP, MB)
# ══════════════════════════════════════════════════════════════════════════════

def _financeiro_info_response(info_fn, proximo_sync_fn=None):
    total, ultima, status, erro = info_fn()
    LABELS = {'sucesso': 'Atualizado', 'sem_novos': 'Sem novos registros',
               'erro': 'Erro no último sync', 'nunca': 'Nunca sincronizado'}
    return jsonify({
        'total_registros':       total,
        'ultima_atualizacao':    ultima or '--',
        'proximo_sync':          calcular_proximo_sync(),
        'ultimo_sync_status':    status or 'nunca',
        'ultimo_sync_status_label': LABELS.get(status or 'nunca', status or '--'),
        'erro_resumo':           erro,
    })


def _financeiro_historico_response(historico_fn):
    try:
        limite = min(max(int(request.args.get('limit', 10)), 1), 50)
        offset = max(int(request.args.get('offset', 0)), 0)
    except (TypeError, ValueError):
        limite, offset = 10, 0
    linhas = historico_fn(limit=limite + 1, offset=offset)
    tem_mais = len(linhas) > limite
    if tem_mais:
        linhas = linhas[:limite]
    return jsonify({
        'historico': [
            {
                'executado_em':   r['executado_em'],
                'registros_novos': r['registros_novos'],
                'status':         r['status'] if 'status' in r.keys() else None,
                'erro_resumo':    r['erro_resumo'] if 'erro_resumo' in r.keys() else None,
            }
            for r in linhas
        ],
        'tem_mais': tem_mais,
    })


def _classificar_erro_sync(e: Exception) -> str:
    """Traduz exceções técnicas de sync em mensagens acionáveis para o usuário.

    Classifica pelo texto da exceção em três categorias principais:
    - Timeout/rede  → orienta tentar novamente em minutos
    - Permissão     → orienta contatar TI
    - Indisponível  → orienta aguardar
    - Genérico      → exibe tipo e trecho da mensagem para diagnóstico
    """
    msg = str(e).lower()

    if any(t in msg for t in ('timeout', 'timed out', 'query timeout', 'login timeout')):
        return 'O ERP não respondeu no tempo esperado. Tente novamente em alguns minutos.'

    if any(t in msg for t in ('network', 'connection reset', 'connection refused',
                               'broken pipe', 'unable to connect', 'communication link',
                               'server has gone away', '08001', '08s01')):
        return 'O ERP está temporariamente indisponível. Tente novamente mais tarde.'

    if any(t in msg for t in ('permission', 'access denied', 'login failed',
                               'cannot open database', '28000', '42000')):
        return 'Sem permissão de acesso ao ERP. Contate o administrador de TI.'

    # Erro não classificado — inclui tipo e trecho da mensagem para diagnóstico
    tipo = type(e).__name__
    trecho = str(e)[:100].strip()
    return f'Falha ao sincronizar com o Protheus. ({tipo}: {trecho})'


def _financeiro_sync_response(sincronizar_fn, nome):
    if not sync_lock.acquire(blocking=False):
        return jsonify({'erro': 'Sync já em progresso. Tente novamente em instantes.'}), 409
    t0 = time.monotonic()
    try:
        novos = sincronizar_fn()
        duracao = round(time.monotonic() - t0)
        registrar_log(f'sync_manual_{nome}', session.get('usuario_id'), session.get('usuario_nome'))
        return jsonify({
            'mensagem': f'Sincronização concluída. {novos} registro(s) processado(s).',
            'registros_novos': novos,
            'duracao_segundos': duracao,
        })
    except Exception as e:
        return jsonify({'erro': _classificar_erro_sync(e)}), 500
    finally:
        sync_lock.release()


def _financeiro_download_response(gerar_csv_fn, gerar_excel_fn, nome_arquivo, formato,
                                   data_inicio=None, data_fim=None):
    """Responde download de relatório financeiro.

    - Excel: gerado em buffer (write_only) e devolvido como bytes.
    - CSV: STREAMING via generator (footprint constante, primeira linha chega
      antes da query terminar). A auditoria registra o total ao final do stream.
    """
    try:
        if formato == 'excel':
            conteudo, total = gerar_excel_fn(data_inicio, data_fim)
            _auditar_download_financeiro_seguro(nome_arquivo, 'excel', total)
            return Response(
                conteudo,
                mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                headers={'Content-Disposition': f'attachment; filename={nome_arquivo}.xlsx'},
            )

        gerador, total_callable = gerar_csv_fn(data_inicio, data_fim)

        def stream_com_auditoria():
            try:
                for chunk in gerador:
                    yield chunk
            finally:
                # registra apenas após o stream terminar (sucesso ou abort)
                try:
                    _auditar_download_financeiro_seguro(nome_arquivo, 'csv', total_callable())
                except Exception:
                    pass

        return Response(
            stream_com_auditoria(),
            mimetype='text/csv; charset=utf-8',
            headers={'Content-Disposition': f'attachment; filename={nome_arquivo}.csv'},
        )
    except Exception as e:
        return jsonify({'erro': f'Erro ao gerar relatório: {str(e)[:120]}'}), 500


def _auditar_download_financeiro_seguro(relatorio, formato, total):
    """Best-effort: nunca pode falhar a ponto de quebrar o download para o usuário."""
    try:
        registrar_log(
            f'download_financeiro_{relatorio}_{formato}',
            session.get('usuario_id'),
            session.get('usuario_nome'),
        )
    except Exception:
        app.logger.exception('Falha ao registrar logs_acesso de download financeiro')
    try:
        registrar_download_financeiro(relatorio, formato, total)
    except Exception:
        app.logger.exception('Falha ao registrar financeiro_downloads_log')


# ── NF de Entrada ─────────────────────────────────────────────────────────────

@app.route('/relatorios/financeiro/nf-entrada')
@acesso_relatorio_requerido('financeiro', 'nf_entrada')
def pagina_financeiro_nf_entrada():
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/financeiro_nf_entrada.html',
        query_preview=QUERY_NF_ENTRADA if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - NF Entrada'),
    )

@app.route('/api/relatorios/financeiro/nf-entrada/info')
@acesso_relatorio_requerido('financeiro', 'nf_entrada')
def api_financeiro_nf_entrada_info():
    return _financeiro_info_response(info_relatorio_nf_entrada)

@app.route('/api/relatorios/financeiro/nf-entrada/historico-sync')
@acesso_relatorio_requerido('financeiro', 'nf_entrada')
def api_financeiro_nf_entrada_historico():
    return _financeiro_historico_response(historico_sync_nf_entrada)

@app.route('/api/relatorios/financeiro/nf-entrada/sync', methods=['POST'])
@acesso_relatorio_requerido('financeiro', 'nf_entrada')
def api_financeiro_nf_entrada_sync():
    return _financeiro_sync_response(sincronizar_nf_entrada, 'nf_entrada')

@app.route('/api/relatorios/financeiro/nf-entrada/download')
@acesso_relatorio_requerido('financeiro', 'nf_entrada')
def api_financeiro_nf_entrada_download():
    fmt = request.args.get('formato', 'csv')
    di  = _iso_para_protheus(request.args.get('data_inicio'))
    df  = _iso_para_protheus(request.args.get('data_fim'))
    return _financeiro_download_response(
        gerar_csv_nf_entrada, gerar_excel_nf_entrada, 'nf_entrada', fmt, di, df
    )

# ── NF de Saída ───────────────────────────────────────────────────────────────

@app.route('/relatorios/financeiro/nf-saida')
@acesso_relatorio_requerido('financeiro', 'nf_saida')
def pagina_financeiro_nf_saida():
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/financeiro_nf_saida.html',
        query_preview=QUERY_NF_SAIDA if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - NF Saída'),
    )

@app.route('/api/relatorios/financeiro/nf-saida/info')
@acesso_relatorio_requerido('financeiro', 'nf_saida')
def api_financeiro_nf_saida_info():
    return _financeiro_info_response(info_relatorio_nf_saida)

@app.route('/api/relatorios/financeiro/nf-saida/historico-sync')
@acesso_relatorio_requerido('financeiro', 'nf_saida')
def api_financeiro_nf_saida_historico():
    return _financeiro_historico_response(historico_sync_nf_saida)

@app.route('/api/relatorios/financeiro/nf-saida/sync', methods=['POST'])
@acesso_relatorio_requerido('financeiro', 'nf_saida')
def api_financeiro_nf_saida_sync():
    return _financeiro_sync_response(sincronizar_nf_saida, 'nf_saida')

@app.route('/api/relatorios/financeiro/nf-saida/download')
@acesso_relatorio_requerido('financeiro', 'nf_saida')
def api_financeiro_nf_saida_download():
    fmt = request.args.get('formato', 'csv')
    di  = _iso_para_protheus(request.args.get('data_inicio'))
    df  = _iso_para_protheus(request.args.get('data_fim'))
    return _financeiro_download_response(
        gerar_csv_nf_saida, gerar_excel_nf_saida, 'nf_saida', fmt, di, df
    )

# ── Contas a Receber ──────────────────────────────────────────────────────────

@app.route('/relatorios/financeiro/contas-receber')
@acesso_relatorio_requerido('financeiro', 'contas_receber')
def pagina_financeiro_contas_receber():
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/financeiro_contas_receber.html',
        query_preview=QUERY_CONTAS_RECEBER if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Contas a Receber'),
    )

@app.route('/api/relatorios/financeiro/contas-receber/info')
@acesso_relatorio_requerido('financeiro', 'contas_receber')
def api_financeiro_contas_receber_info():
    return _financeiro_info_response(info_relatorio_contas_receber)

@app.route('/api/relatorios/financeiro/contas-receber/historico-sync')
@acesso_relatorio_requerido('financeiro', 'contas_receber')
def api_financeiro_contas_receber_historico():
    return _financeiro_historico_response(historico_sync_contas_receber)

@app.route('/api/relatorios/financeiro/contas-receber/sync', methods=['POST'])
@acesso_relatorio_requerido('financeiro', 'contas_receber')
def api_financeiro_contas_receber_sync():
    return _financeiro_sync_response(sincronizar_contas_receber, 'contas_receber')

@app.route('/api/relatorios/financeiro/contas-receber/download')
@acesso_relatorio_requerido('financeiro', 'contas_receber')
def api_financeiro_contas_receber_download():
    fmt = request.args.get('formato', 'csv')
    di  = _iso_para_protheus(request.args.get('data_inicio'))
    df  = _iso_para_protheus(request.args.get('data_fim'))
    return _financeiro_download_response(
        gerar_csv_contas_receber, gerar_excel_contas_receber, 'contas_receber', fmt, di, df
    )

# ── Contas a Pagar ────────────────────────────────────────────────────────────

@app.route('/relatorios/financeiro/contas-pagar')
@acesso_relatorio_requerido('financeiro', 'contas_pagar')
def pagina_financeiro_contas_pagar():
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/financeiro_contas_pagar.html',
        query_preview=QUERY_CONTAS_PAGAR if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Contas a Pagar'),
    )

@app.route('/api/relatorios/financeiro/contas-pagar/info')
@acesso_relatorio_requerido('financeiro', 'contas_pagar')
def api_financeiro_contas_pagar_info():
    return _financeiro_info_response(info_relatorio_contas_pagar)

@app.route('/api/relatorios/financeiro/contas-pagar/historico-sync')
@acesso_relatorio_requerido('financeiro', 'contas_pagar')
def api_financeiro_contas_pagar_historico():
    return _financeiro_historico_response(historico_sync_contas_pagar)

@app.route('/api/relatorios/financeiro/contas-pagar/sync', methods=['POST'])
@acesso_relatorio_requerido('financeiro', 'contas_pagar')
def api_financeiro_contas_pagar_sync():
    return _financeiro_sync_response(sincronizar_contas_pagar, 'contas_pagar')

@app.route('/api/relatorios/financeiro/contas-pagar/download')
@acesso_relatorio_requerido('financeiro', 'contas_pagar')
def api_financeiro_contas_pagar_download():
    fmt = request.args.get('formato', 'csv')
    di  = _iso_para_protheus(request.args.get('data_inicio'))
    df  = _iso_para_protheus(request.args.get('data_fim'))
    return _financeiro_download_response(
        gerar_csv_contas_pagar, gerar_excel_contas_pagar, 'contas_pagar', fmt, di, df
    )

# ── Movimentos Bancários ──────────────────────────────────────────────────────

@app.route('/relatorios/financeiro/mov-bancarios')
@acesso_relatorio_requerido('financeiro', 'mov_bancarios')
def pagina_financeiro_mov_bancarios():
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/financeiro_mov_bancarios.html',
        query_preview=QUERY_MOV_BANCARIOS if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Movimentos Bancários'),
    )

@app.route('/api/relatorios/financeiro/mov-bancarios/info')
@acesso_relatorio_requerido('financeiro', 'mov_bancarios')
def api_financeiro_mov_bancarios_info():
    return _financeiro_info_response(info_relatorio_mov_bancarios)

@app.route('/api/relatorios/financeiro/mov-bancarios/historico-sync')
@acesso_relatorio_requerido('financeiro', 'mov_bancarios')
def api_financeiro_mov_bancarios_historico():
    return _financeiro_historico_response(historico_sync_mov_bancarios)

@app.route('/api/relatorios/financeiro/mov-bancarios/sync', methods=['POST'])
@acesso_relatorio_requerido('financeiro', 'mov_bancarios')
def api_financeiro_mov_bancarios_sync():
    return _financeiro_sync_response(sincronizar_mov_bancarios, 'mov_bancarios')

@app.route('/api/relatorios/financeiro/mov-bancarios/download')
@acesso_relatorio_requerido('financeiro', 'mov_bancarios')
def api_financeiro_mov_bancarios_download():
    fmt = request.args.get('formato', 'csv')
    di  = _iso_para_protheus(request.args.get('data_inicio'))
    df  = _iso_para_protheus(request.args.get('data_fim'))
    return _financeiro_download_response(
        gerar_csv_mov_bancarios, gerar_excel_mov_bancarios, 'mov_bancarios', fmt, di, df
    )


# ── Energy — Contas a Pagar ──────────────────────────────────────────────────

@app.route('/relatorios/energy/contas-pagar')
@acesso_relatorio_requerido('energy', 'contas_pagar')
def pagina_energy_contas_pagar():
    usuario = usuario_atual()
    pode_ver_query = bool(usuario and usuario['is_admin'] and usuario['pode_ver_query'])
    return render_template(
        'relatorios/energy_contas_pagar.html',
        query_preview=QUERY_ENERGY_CONTAS_PAGAR if pode_ver_query else '',
        pode_ver_query=pode_ver_query,
        **contexto_auth('ProtheusData - Energy Contas a Pagar'),
    )

@app.route('/api/relatorios/energy/contas-pagar/info')
@acesso_relatorio_requerido('energy', 'contas_pagar')
def api_energy_contas_pagar_info():
    return _financeiro_info_response(info_relatorio_energy_contas_pagar)

@app.route('/api/relatorios/energy/contas-pagar/historico-sync')
@acesso_relatorio_requerido('energy', 'contas_pagar')
def api_energy_contas_pagar_historico():
    return _financeiro_historico_response(historico_sync_energy_contas_pagar)

@app.route('/api/relatorios/energy/contas-pagar/sync', methods=['POST'])
@acesso_relatorio_requerido('energy', 'contas_pagar')
def api_energy_contas_pagar_sync():
    return _financeiro_sync_response(sincronizar_energy_contas_pagar, 'energy_contas_pagar')

@app.route('/api/relatorios/energy/contas-pagar/download')
@acesso_relatorio_requerido('energy', 'contas_pagar')
def api_energy_contas_pagar_download():
    fmt = request.args.get('formato', 'csv')
    di  = _iso_para_protheus(request.args.get('data_inicio'))
    df  = _iso_para_protheus(request.args.get('data_fim'))
    return _financeiro_download_response(
        gerar_csv_energy_contas_pagar, gerar_excel_energy_contas_pagar,
        'energy_contas_pagar', fmt, di, df,
    )


def _iso_para_protheus(data_iso):
    """Converte '2024-01-15' (HTML date input) para '20240115' (formato Protheus/SQLite).
    Valida formato E calendário (ex: 2024-13-45 → None). Retorna None se inválida."""
    if not data_iso:
        return None
    from datetime import datetime
    try:
        return datetime.strptime(data_iso.strip(), '%Y-%m-%d').strftime('%Y%m%d')
    except ValueError:
        return None


def registrar_download(formato, registros):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO downloads_log (usuario_id, usuario_nome, formato, registros, data_hora) VALUES (?, ?, ?, ?, ?)',
        (session.get('usuario_id'), session.get('usuario_nome'), formato, registros, agora())
    )
    conn.commit()
    conn.close()


def registrar_download_historico(formato, registros):
    conn = conectar_pedidos()
    conn.execute(
        'INSERT INTO historico_downloads_log (usuario_id, usuario_nome, formato, registros, data_hora) VALUES (?, ?, ?, ?, ?)',
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


def registrar_download_financeiro(relatorio, formato, registros):
    """Registra download de relatório financeiro (CSV/Excel) para auditoria."""
    payload = (
        session.get('usuario_id'),
        session.get('usuario_nome'),
        relatorio,
        formato,
        registros,
        _obter_ip_real() if request else None,
        agora(),
    )
    conn = conectar_financeiro()
    try:
        conn.execute(
            'INSERT INTO financeiro_downloads_log '
            '(usuario_id, usuario_nome, relatorio, formato, registros, ip, data_hora) '
            'VALUES (?, ?, ?, ?, ?, ?, ?)',
            payload,
        )
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


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
    usuario_id  = request.args.get('usuario_id', type=int)
    acao        = request.args.get('acao', '').strip() or None
    busca       = request.args.get('busca', '').strip() or None
    data_inicio = request.args.get('data_inicio', '').strip() or None
    data_fim    = request.args.get('data_fim', '').strip() or None
    pagina      = max(1, request.args.get('pagina', 1, type=int))
    por_pagina  = 25
    offset      = (pagina - 1) * por_pagina

    auditoria = listar_auditoria_admin(
        limit=por_pagina, offset=offset,
        usuario_id=usuario_id, acao=acao,
        busca=busca, data_inicio=data_inicio, data_fim=data_fim,
    )
    acesso = listar_logs_acesso(
        limit=por_pagina, offset=offset,
        busca=busca, acao=acao,
        data_inicio=data_inicio, data_fim=data_fim,
    )
    return jsonify({
        'auditoria':    auditoria['itens'],
        'logs_acesso':  acesso['itens'],
        'total_auditoria': auditoria['total'],
        'total_acesso':    acesso['total'],
        'pagina':          pagina,
        'por_pagina':      por_pagina,
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
        'banco_financeiro': 'ok',
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
        conn = conectar_financeiro()
        conn.execute('SELECT 1').fetchone()
        conn.close()
    except Exception:
        status['banco_financeiro'] = 'erro'
        status['status'] = 'degradado'

    try:
        _, ultimo_pedidos, _, _ = info_relatorio_pedidos()
        _, ultimo_estoque, _, _ = info_relatorio_estoque()
        status['ultimo_sync'] = ultimo_pedidos or 'Nunca'
        status['ultimo_sync_estoque'] = ultimo_estoque or 'Nunca'
    except Exception:
        status['ultimo_sync'] = 'Erro'
        status['ultimo_sync_estoque'] = 'Erro'

    # Scheduler vivo apenas no worker SCHEDULER_OWNER
    if sync_timer is not None:
        status['scheduler'] = 'ativo' if sync_timer.is_alive() else 'morto'
    else:
        status['scheduler'] = 'ausente'

    if status['scheduler'] == 'morto':
        status['status'] = 'degradado'

    return jsonify(status)


def garantir_schemas():
    """Cria/migra todas as tabelas. Idempotente, executado por TODOS os workers
    (no post_fork) para garantir que cada processo abra conexões válidas."""
    criar_tabelas()
    consolidar_sync_log_pedidos()
    consolidar_sync_log_estoque()


def inicializar():
    """Worker designado como scheduler-owner.

    Executa uma vez no post_fork do primeiro worker:
      1) garante schemas
      2) limpa logs antigos
      3) faz cargas iniciais (idempotentes — pulam se já há dados)
      4) cria backup diário
      5) agenda próximo sync (Timer no processo do worker)

    Outros workers chamam apenas garantir_schemas() — sem Timer, sem carga,
    sem backup — para não duplicar tarefas.
    """
    global ultimo_sync_dt
    garantir_schemas()
    limpar_logs_antigos()
    print('[STARTUP] Verificando carga inicial...')
    try:
        total_pedidos = carga_inicial_pedidos()
        total_estoque   = carga_inicial_estoque()
        total_historico = carga_inicial_historico()
        if total_pedidos > 0:
            print(f'[STARTUP] Carga inicial de pedidos concluída. {total_pedidos} registros importados.')
        else:
            print('[STARTUP] Dados de pedidos já existem no banco local.')

        if total_estoque > 0:
            print(f'[STARTUP] Carga inicial de estoque concluída. {total_estoque} registros importados.')
        else:
            print('[STARTUP] Dados de estoque já existem no banco local.')

        if total_historico > 0:
            print(f'[STARTUP] Carga inicial do histórico concluída. {total_historico} registros importados.')
        else:
            print('[STARTUP] Dados do histórico de pedidos já existem no banco local.')

        # ── Módulo Financeiro ─────────────────────────────────────────────────
        _financeiro_cargas_iniciais = [
            ('NF Entrada',           carga_inicial_nf_entrada),
            ('NF Saída',             carga_inicial_nf_saida),
            ('Contas a Receber',     carga_inicial_contas_receber),
            ('Contas a Pagar',       carga_inicial_contas_pagar),
            ('Movimentos Bancários', carga_inicial_mov_bancarios),
            ('Energy — Contas a Pagar', carga_inicial_energy_contas_pagar),
        ]
        for nome_fin, fn_fin in _financeiro_cargas_iniciais:
            try:
                tot = fn_fin()
                if tot > 0:
                    print(f'[STARTUP] Financeiro — {nome_fin}: {tot} registros importados.')
                else:
                    print(f'[STARTUP] Financeiro — {nome_fin}: dados já existem.')
            except Exception as e_fin:
                print(f'[STARTUP] Financeiro — {nome_fin}: erro na carga inicial: {e_fin}')

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


# ─── Bootstrap por worker ────────────────────────────────────────────────────
# - Sob Gunicorn (>=1 worker): gunicorn_conf.py chama garantir_schemas() em
#   todos os workers via post_fork e inicializar() apenas no worker designado
#   como SCHEDULER_OWNER (worker.age == 0).
# - Sob Flask dev server / execução direta: rodamos inicializar() aqui mesmo.
if not os.getenv('GUNICORN_WORKER_BOOT'):
    inicializar()

if __name__ == '__main__':
    app.run(debug=False, port=5000, use_reloader=False)
