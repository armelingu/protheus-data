"""
Serviço de e-mail via Microsoft Graph API (OAuth2 client_credentials).

Fluxo:
  1. Obtém token de acesso em /oauth2/v2.0/token (client_credentials)
  2. Chama POST /v1.0/users/{sender}/sendMail com o token Bearer
  3. Token é cacheado em memória por até 55 min (expira em 60 min por padrão)

Permissão necessária no Entra:
  Aplicativo → Permissões de API → Microsoft Graph → Mail.Send (Application)
  + consentimento de administrador concedido
"""
from __future__ import annotations

import os
import time

import requests


# ─── Utilitários de ambiente ─────────────────────────────────────────────────

def _str_env(nome: str, default: str = '') -> str:
    return os.getenv(nome, default).strip()


def _bool_env(nome: str, default: bool = False) -> bool:
    valor = os.getenv(nome, 'true' if default else 'false').strip().lower()
    return valor in {'1', 'true', 'yes', 'on'}


# ─── Cache de token OAuth2 ───────────────────────────────────────────────────

_token_cache: tuple[str, float] | None = None   # (access_token, expires_at)


def _obter_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Obtém (ou reutiliza do cache) um token OAuth2 client_credentials."""
    global _token_cache
    agora = time.monotonic()

    if _token_cache and agora < _token_cache[1]:
        return _token_cache[0]

    url  = f'https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token'
    resp = requests.post(
        url,
        data={
            'grant_type':    'client_credentials',
            'client_id':     client_id,
            'client_secret': client_secret,
            'scope':         'https://graph.microsoft.com/.default',
        },
        timeout=15,
    )

    if not resp.ok:
        raise RuntimeError(
            f'Falha ao obter token OAuth2 ({resp.status_code}): {resp.text[:300]}'
        )

    dados       = resp.json()
    token       = dados['access_token']
    expires_in  = int(dados.get('expires_in', 3600))
    _token_cache = (token, agora + expires_in - 300)   # renova 5 min antes
    return token


def _invalidar_token() -> None:
    global _token_cache
    _token_cache = None


# ─── Configuração ─────────────────────────────────────────────────────────────

def configuracao_email() -> dict:
    return {
        'enabled':       _bool_env('EMAIL_ENABLED', False),
        'provider':      _str_env('EMAIL_PROVIDER', 'msgraph').lower(),
        'from':          _str_env('EMAIL_FROM', ''),
        'tenant_id':     _str_env('MS_TENANT_ID', ''),
        'client_id':     _str_env('MS_CLIENT_ID', ''),
        'client_secret': _str_env('MS_CLIENT_SECRET', ''),
        'app_base_url':  _str_env('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/'),
    }


def configuracao_email_valida() -> tuple[bool, str | None]:
    cfg = configuracao_email()
    if not cfg['enabled']:
        return False, 'Envio de e-mail não está habilitado (EMAIL_ENABLED).'
    for campo in ('from', 'tenant_id', 'client_id', 'client_secret'):
        if not cfg[campo]:
            return False, f'Configuração incompleta do e-mail: {campo}.'
    return True, None


# ─── Montagem do e-mail de acesso ────────────────────────────────────────────

CHAMADOS_URL = 'http://10.0.253.100:5000/ir-para-chamados'


def montar_email_acesso(
    nome: str,
    email_destino: str,
    login: str,
    app_base_url: str | None = None,
    senha: str | None = None,
) -> dict:
    app_base_url  = (app_base_url or configuracao_email()['app_base_url']).rstrip('/')
    login_url     = f'{app_base_url}/login'
    assunto       = 'Seu acesso foi criado — ProtheusData'
    senha_exibida = senha if senha else login   # fallback para legados sem senha gerada

    primeiro_nome = nome.split()[0] if nome else nome

    corpo_texto = (
        f'Olá, {primeiro_nome}.\n\n'
        'Seu acesso à ProtheusData foi criado.\n\n'
        f'  Endereço : {login_url}\n'
        f'  Login    : {login}\n'
        f'  Senha    : {senha_exibida}\n\n'
        'Na primeira entrada o sistema pedirá a troca obrigatória da senha.\n\n'
        '---\n'
        'Este é um e-mail automático. Não responda esta mensagem.\n'
        f'Em caso de dúvidas, abra um chamado em: {CHAMADOS_URL}\n'
    )

    corpo_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0"
             style="max-width:560px;background:#ffffff;border:1px solid #e0e0e0;">

        <!-- cabeçalho -->
        <tr>
          <td style="background:#1a1a1a;padding:28px 32px;">
            <p style="margin:0;color:#ffffff;font-size:11px;font-weight:700;
                      letter-spacing:2px;text-transform:uppercase;">ProtheusData</p>
            <p style="margin:6px 0 0;color:#cccccc;font-size:13px;">
              Central de Relatórios
            </p>
          </td>
        </tr>

        <!-- corpo -->
        <tr>
          <td style="padding:32px 32px 24px;">
            <p style="margin:0 0 6px;color:#8a8a8a;font-size:11px;
                      font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">
              Novo acesso
            </p>
            <h1 style="margin:0 0 20px;color:#1a1a1a;font-size:22px;
                       font-weight:700;letter-spacing:-0.5px;line-height:1.3;">
              Olá, {primeiro_nome}!<br>Seu acesso está pronto.
            </h1>
            <p style="margin:0 0 24px;color:#555555;font-size:14px;line-height:1.7;">
              Sua conta na <strong>ProtheusData</strong> foi criada.
              Use as credenciais abaixo para entrar. Na primeira vez, o sistema
              pedirá que você crie uma nova senha pessoal.
            </p>

            <!-- credenciais -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f7f7f7;border:1px solid #e8e8e8;
                          margin-bottom:24px;">
              <tr>
                <td style="padding:14px 18px;border-bottom:1px solid #eeeeee;">
                  <p style="margin:0;color:#9a9a9a;font-size:10px;font-weight:700;
                            letter-spacing:1px;text-transform:uppercase;">Login</p>
                  <p style="margin:4px 0 0;color:#1a1a1a;font-size:15px;
                            font-weight:600;font-family:monospace;">{login}</p>
                </td>
              </tr>
              <tr>
                <td style="padding:14px 18px;">
                  <p style="margin:0;color:#9a9a9a;font-size:10px;font-weight:700;
                            letter-spacing:1px;text-transform:uppercase;">Senha inicial</p>
                  <p style="margin:4px 0 0;color:#1a1a1a;font-size:15px;
                            font-weight:600;font-family:monospace;">{senha_exibida}</p>
                </td>
              </tr>
            </table>

            <!-- botão -->
            <table cellpadding="0" cellspacing="0" style="margin-bottom:28px;">
              <tr>
                <td style="background:#1a1a1a;">
                  <a href="{login_url}"
                     style="display:inline-block;padding:14px 28px;
                            color:#ffffff;font-size:12px;font-weight:700;
                            letter-spacing:1px;text-transform:uppercase;
                            text-decoration:none;">
                    Acessar o sistema →
                  </a>
                </td>
              </tr>
            </table>

            <p style="margin:0;color:#9a9a9a;font-size:11px;line-height:1.6;">
              Se o botão não funcionar, copie e cole este endereço no navegador:<br>
              <a href="{login_url}"
                 style="color:#555555;word-break:break-all;">{login_url}</a>
            </p>
          </td>
        </tr>

        <!-- rodapé -->
        <tr>
          <td style="padding:18px 32px 24px;border-top:1px solid #f0f0f0;
                     background:#fafafa;">
            <table width="100%" cellpadding="0" cellspacing="0">
              <tr>
                <td style="padding:12px 14px;background:#fff8e6;
                           border-left:3px solid #e0a800;">
                  <p style="margin:0;color:#7a5510;font-size:11px;
                            font-weight:700;letter-spacing:0.5px;">
                    Nao responda este e-mail
                  </p>
                  <p style="margin:4px 0 0;color:#8a6520;font-size:11px;
                            line-height:1.6;">
                    Esta caixa não é monitorada. Em caso de dúvidas ou
                    problemas de acesso, abra um chamado pelo nosso canal oficial:
                  </p>
                  <p style="margin:6px 0 0;">
                    <a href="{CHAMADOS_URL}"
                       style="color:#1a1a1a;font-size:11px;font-weight:700;">
                      Yellow Tickets →
                    </a>
                  </p>
                </td>
              </tr>
            </table>
            <p style="margin:14px 0 0;color:#bbbbbb;font-size:10px;">
              ProtheusData · Mensagem automática
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {
        'to':      email_destino,
        'subject': assunto,
        'body':    corpo_texto,
        'html':    corpo_html,
        'login':   login,
        'url':     login_url,
    }


# ─── Montagem do e-mail de recuperação de senha ──────────────────────────────

def montar_email_recuperacao_senha(
    nome: str,
    email_destino: str,
    reset_url: str,
) -> dict:
    assunto      = 'Recuperacao de senha — ProtheusData'
    primeiro_nome = nome.split()[0] if nome else nome

    corpo_texto = (
        f'Ola, {primeiro_nome}.\n\n'
        'Recebemos uma solicitacao de recuperacao de senha para sua conta.\n\n'
        f'  Clique no link abaixo para redefinir sua senha:\n'
        f'  {reset_url}\n\n'
        'O link expira em 1 hora.\n\n'
        'Se voce nao solicitou a recuperacao de senha, ignore este e-mail.\n'
        'Sua senha nao sera alterada.\n\n'
        '---\n'
        'Este e um e-mail automatico. Nao responda esta mensagem.\n'
        f'Em caso de duvidas, abra um chamado em: {CHAMADOS_URL}\n'
    )

    corpo_html = f"""<!DOCTYPE html>
<html lang="pt-BR">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1"></head>
<body style="margin:0;padding:0;background:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f4f4f4;padding:32px 16px;">
    <tr><td align="center">
      <table width="100%" cellpadding="0" cellspacing="0"
             style="max-width:560px;background:#ffffff;border:1px solid #e0e0e0;">

        <!-- cabeçalho -->
        <tr>
          <td style="background:#1a1a1a;padding:28px 32px;">
            <p style="margin:0;color:#ffffff;font-size:11px;font-weight:700;
                      letter-spacing:2px;text-transform:uppercase;">ProtheusData</p>
            <p style="margin:6px 0 0;color:#cccccc;font-size:13px;">
              Central de Relatorios
            </p>
          </td>
        </tr>

        <!-- corpo -->
        <tr>
          <td style="padding:32px 32px 24px;">
            <p style="margin:0 0 6px;color:#8a8a8a;font-size:11px;
                      font-weight:700;letter-spacing:1.5px;text-transform:uppercase;">
              Recuperacao de senha
            </p>
            <h1 style="margin:0 0 20px;color:#1a1a1a;font-size:22px;
                       font-weight:700;letter-spacing:-0.5px;line-height:1.3;">
              Ola, {primeiro_nome}!<br>Redefina sua senha.
            </h1>
            <p style="margin:0 0 24px;color:#555555;font-size:14px;line-height:1.7;">
              Recebemos uma solicitacao de recuperacao de senha para sua conta
              na <strong>ProtheusData</strong>.
              Clique no botao abaixo para criar uma nova senha.
            </p>

            <!-- botão -->
            <table cellpadding="0" cellspacing="0" style="margin-bottom:24px;">
              <tr>
                <td style="background:#1a1a1a;">
                  <a href="{reset_url}"
                     style="display:inline-block;padding:14px 28px;
                            color:#ffffff;font-size:12px;font-weight:700;
                            letter-spacing:1px;text-transform:uppercase;
                            text-decoration:none;">
                    Redefinir minha senha &rarr;
                  </a>
                </td>
              </tr>
            </table>

            <!-- aviso de expiração -->
            <table width="100%" cellpadding="0" cellspacing="0"
                   style="background:#f7f7f7;border:1px solid #e8e8e8;margin-bottom:20px;">
              <tr>
                <td style="padding:12px 16px;">
                  <p style="margin:0;color:#8a8a8a;font-size:11px;line-height:1.6;">
                    Este link expira em <strong>1 hora</strong>.
                    Apos expirar, sera necessario solicitar um novo link.
                  </p>
                </td>
              </tr>
            </table>

            <p style="margin:0 0 8px;color:#9a9a9a;font-size:11px;line-height:1.6;">
              Se voce nao solicitou a recuperacao de senha,
              <strong>ignore este e-mail</strong>. Sua senha nao sera alterada.
            </p>
            <p style="margin:0;color:#9a9a9a;font-size:11px;line-height:1.6;">
              Se o botao nao funcionar, copie e cole este endereco no navegador:<br>
              <a href="{reset_url}"
                 style="color:#555555;word-break:break-all;">{reset_url}</a>
            </p>
          </td>
        </tr>

        <!-- rodapé -->
        <tr>
          <td style="padding:20px 32px;border-top:1px solid #eeeeee;background:#fafafa;">
            <p style="margin:0 0 6px;color:#9a9a9a;font-size:11px;">
              Precisa de ajuda?
              <a href="{CHAMADOS_URL}"
                 style="color:#1a1a1a;font-size:11px;font-weight:700;">
                Yellow Tickets &rarr;
              </a>
            </p>
            <p style="margin:0;color:#bbbbbb;font-size:10px;">
              ProtheusData &middot; Mensagem automatica
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {
        'to':      email_destino,
        'subject': assunto,
        'body':    corpo_texto,
        'html':    corpo_html,
        'url':     reset_url,
    }


# ─── Envio via Graph API ──────────────────────────────────────────────────────

def enviar_email(payload: dict) -> dict:
    """Envia o e-mail usando Microsoft Graph API.

    Parâmetros
    ----------
    payload : dict com chaves 'to', 'subject', 'body' (texto plano) e
              opcionalmente 'html' (corpo HTML — preferido quando presente).

    Retorno
    -------
    dict com 'ok' (bool) e 'error' (str | None).
    """
    valido, erro = configuracao_email_valida()
    if not valido:
        return {'ok': False, 'error': erro}

    cfg = configuracao_email()

    try:
        token = _obter_token(cfg['tenant_id'], cfg['client_id'], cfg['client_secret'])
    except Exception as exc:
        return {'ok': False, 'error': f'Erro ao obter token OAuth2: {exc}'}

    conteudo = payload.get('html') or payload.get('body', '')
    tipo     = 'HTML' if payload.get('html') else 'Text'

    graph_payload = {
        'message': {
            'subject': payload['subject'],
            'body': {
                'contentType': tipo,
                'content':     conteudo,
            },
            'toRecipients': [
                {'emailAddress': {'address': payload['to']}}
            ],
            'from': {
                'emailAddress': {'address': cfg['from']}
            },
        },
        'saveToSentItems': True,
    }

    url = f'https://graph.microsoft.com/v1.0/users/{cfg["from"]}/sendMail'

    try:
        resp = requests.post(
            url,
            json=graph_payload,
            headers={
                'Authorization': f'Bearer {token}',
                'Content-Type':  'application/json',
            },
            timeout=30,
        )

        if resp.status_code == 202:
            return {'ok': True, 'error': None}

        # Token expirado ou revogado — invalida cache e informa
        if resp.status_code in (401, 403):
            _invalidar_token()
            return {
                'ok':    False,
                'error': f'Acesso negado pela Graph API ({resp.status_code}). '
                         f'Verifique as permissões Mail.Send no Entra. '
                         f'Detalhe: {resp.text[:300]}',
            }

        return {
            'ok':    False,
            'error': f'Graph API retornou {resp.status_code}: {resp.text[:300]}',
        }

    except requests.exceptions.Timeout:
        return {'ok': False, 'error': 'Timeout ao conectar à Graph API (30 s).'}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
