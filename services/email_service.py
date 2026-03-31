import os
import smtplib
from email.message import EmailMessage

def _bool_env(nome, default=False):
    valor = os.getenv(nome, 'true' if default else 'false').strip().lower()
    return valor in {'1', 'true', 'yes', 'on'}


def _str_env(nome, default=''):
    return os.getenv(nome, default).strip()


def _provider_label(provider):
    if provider == 'gmail':
        return 'Gmail'
    if provider in {'outlook', 'office365', 'm365'}:
        return 'Outlook'
    return 'e-mail'


def configuracao_email():
    provider = _str_env('EMAIL_PROVIDER', '').lower() or 'gmail'
    smtp_host = _str_env('SMTP_HOST', '')
    smtp_port = _str_env('SMTP_PORT', '587') or '587'

    if provider == 'gmail':
        smtp_host = smtp_host or 'smtp.gmail.com'
        smtp_port = smtp_port or '587'

    if provider in {'outlook', 'office365', 'm365'}:
        smtp_host = smtp_host or 'smtp.office365.com'
        smtp_port = smtp_port or '587'

    return {
        'enabled': _bool_env('EMAIL_ENABLED', False),
        'provider': provider,
        'from': _str_env('EMAIL_FROM', ''),
        'smtp_host': smtp_host,
        'smtp_port': int(smtp_port),
        'smtp_username': _str_env('SMTP_USERNAME', ''),
        'smtp_password': _str_env('SMTP_PASSWORD', ''),
        'smtp_use_tls': _bool_env('SMTP_USE_TLS', True),
        'app_base_url': _str_env('APP_BASE_URL', 'http://127.0.0.1:5000').rstrip('/'),
    }


def configuracao_email_valida():
    config = configuracao_email()
    provider_label = _provider_label(config['provider'])

    if not config['enabled']:
        return False, f'Envio de e-mail via {provider_label} ainda não configurado.'
    campos_obrigatorios = ('from', 'smtp_host', 'smtp_username')
    for campo in campos_obrigatorios:
        if not config[campo]:
            return False, f'Configuração incompleta do {provider_label}: {campo}.'
    if not config['smtp_password']:
        return False, f'Configuração incompleta do {provider_label}: smtp_password.'
    return True, None


CHAMADOS_URL = 'http://10.0.253.100:5000/ir-para-chamados'


def montar_email_acesso(nome, email_destino, login, app_base_url=None):
    app_base_url = (app_base_url or configuracao_email()['app_base_url']).rstrip('/')
    login_url = f'{app_base_url}/login'
    assunto = 'Seu acesso foi criado — ProtheusData HBR'

    primeiro_nome = nome.split()[0] if nome else nome

    corpo_texto = (
        f'Olá, {primeiro_nome}.\n\n'
        'Seu acesso à ProtheusData HBR foi criado.\n\n'
        f'  Endereço : {login_url}\n'
        f'  Login    : {login}\n'
        f'  Senha    : {login}\n\n'
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
              Central de Relatórios HBR Aviação
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
              Sua conta na <strong>ProtheusData HBR</strong> foi criada.
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
                            font-weight:600;font-family:monospace;">{login}</p>
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
                    ⚠ Não responda este e-mail
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
              ProtheusData · HBR Aviação · Mensagem automática
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""

    return {
        'to': email_destino,
        'subject': assunto,
        'body': corpo_texto,
        'html': corpo_html,
        'login': login,
        'url': login_url,
    }


def enviar_email(payload):
    valido, erro = configuracao_email_valida()
    if not valido:
        return {'ok': False, 'error': erro}

    config = configuracao_email()
    mensagem = EmailMessage()
    mensagem['Subject'] = payload['subject']
    mensagem['From']    = config['from']
    mensagem['To']      = payload['to']

    mensagem.set_content(payload['body'])

    if payload.get('html'):
        mensagem.add_alternative(payload['html'], subtype='html')

    try:
        with smtplib.SMTP(config['smtp_host'], config['smtp_port'], timeout=20) as servidor:
            if config['smtp_use_tls']:
                servidor.starttls()
            servidor.login(config['smtp_username'], config['smtp_password'])
            servidor.send_message(mensagem)
        return {'ok': True, 'error': None}
    except Exception as exc:
        return {'ok': False, 'error': str(exc)}
