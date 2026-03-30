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


def montar_email_acesso(nome, email_destino, login, app_base_url=None):
    app_base_url = (app_base_url or configuracao_email()['app_base_url']).rstrip('/')
    assunto = 'Acesso liberado - Central de Relatórios HBR'
    corpo = (
        f'Olá, {nome}.\n\n'
        'Seu acesso à Central de Relatórios HBR foi criado com sucesso.\n\n'
        f'Endereço de acesso: {app_base_url}/login\n'
        f'Login: {login}\n'
        f'Senha inicial: {login}\n\n'
        'No primeiro acesso, o sistema solicitará a troca obrigatória da senha.\n\n'
        'Se você tiver qualquer dificuldade, entre em contato com o TI.\n'
    )
    return {
        'to': email_destino,
        'subject': assunto,
        'body': corpo,
        'login': login,
        'url': f'{app_base_url}/login',
    }


def enviar_email(payload):
    valido, erro = configuracao_email_valida()
    if not valido:
        return {
            'ok': False,
            'error': erro,
        }

    config = configuracao_email()
    mensagem = EmailMessage()
    mensagem['Subject'] = payload['subject']
    mensagem['From'] = config['from']
    mensagem['To'] = payload['to']
    mensagem.set_content(payload['body'])

    try:
        with smtplib.SMTP(config['smtp_host'], config['smtp_port'], timeout=20) as servidor:
            if config['smtp_use_tls']:
                servidor.starttls()
            servidor.login(config['smtp_username'], config['smtp_password'])
            servidor.send_message(mensagem)
        return {'ok': True, 'error': None}
    except Exception as exc:
        return {
            'ok': False,
            'error': str(exc),
        }
