"""
Wrapper thread-safe para o webservice SOAP WSHBPEDC (Protheus).

Responsabilidades:
  - Carregar o WSDL uma única vez (inicialização lazy, com double-checked lock)
  - Expor incluir_pedido(pedido_dict) → C7_NUM string
  - Traduzir SOAP Fault e erros de conexão em RuntimeError com mensagem legível
  - Aplicar timeout de 60 s por chamada (conforme benchmark: pico real ~19 s)

O cliente zeep compartilhado entre threads é seguro porque o urllib3 PoolManager
(usado internamente pelo requests) é thread-safe. Confirmado em benchmark real
com pool de 3 workers sem colisão (ver integracao_pedcom/docs/benchmark.txt).

Configuração via variáveis de ambiente (.env):
  WS_PEDCOM_HOST     host do appserver Protheus
  WS_PEDCOM_PORTA    porta do job IWS (default 9199)
  WS_PEDCOM_USUARIO  usuário HTTP Basic Auth
  WS_PEDCOM_SENHA    senha HTTP Basic Auth
  WS_PEDCOM_CHAVE    chave de operação validada pelo U_HBWOPEOK no .prw
"""
import os
import threading

from requests import Session
from requests.auth import HTTPBasicAuth
from zeep import Client
from zeep.exceptions import Fault
from zeep.transports import Transport

_lock = threading.Lock()
_client: Client | None = None


def _get_client() -> Client:
    """Retorna o cliente zeep, inicializando-o na primeira chamada."""
    global _client
    if _client is not None:
        return _client
    with _lock:
        if _client is not None:
            return _client

        host = os.getenv('WS_PEDCOM_HOST', '').strip()
        porta = os.getenv('WS_PEDCOM_PORTA', '9199').strip()
        usuario = os.getenv('WS_PEDCOM_USUARIO', '').strip()
        senha = os.getenv('WS_PEDCOM_SENHA', '').strip()

        if not host:
            raise RuntimeError(
                'WS_PEDCOM_HOST não configurado. Verifique o .env.'
            )

        wsdl_url = f'http://{host}:{porta}/WSHBPEDC.apw?WSDL'

        session = Session()
        session.auth = HTTPBasicAuth(usuario, senha)
        transport = Transport(session=session, timeout=60)

        _client = Client(wsdl_url, transport=transport)

    return _client


def incluir_pedido(pedido: dict) -> str:
    """Chama WSHBPEDC.INCLUIR e retorna o C7_NUM gerado.

    Parâmetros
    ----------
    pedido : dict
        Estrutura montada conforme o WSDL:
        {
            'CODFORNECEDOR': '005087',
            'LOJAFORNEC':    '01',
            'CODIGOCOND':    '006',
            'CODCC':         '006.00027',
            'CODCLVL':       '999999999',
            'CODIGOPRODUTO': 'SV000036',
            'MESINICIAL':    '8',
            'ANOREFERENCIA': '2026',
            'QTDMESES':      '5',
            'RATEIOS': {
                'WSHBPEDC_RATEIO': [
                    {'CODITEMCTA': '99.001', 'VALORMENSAL': '5000.00'},
                    {'CODITEMCTA': '99.003', 'VALORMENSAL': '5000.00'},
                ]
            }
        }

    Retorno
    -------
    str : C7_NUM do pedido criado (ex: '097954')

    Exceções
    --------
    RuntimeError : qualquer falha — SOAP Fault, erro de conexão ou resultado vazio.
                   A mensagem já está em português e pode ser exibida ao usuário.
    """
    chave = os.getenv('WS_PEDCOM_CHAVE', '').strip()
    if not chave:
        raise RuntimeError('WS_PEDCOM_CHAVE não configurado. Verifique o .env.')

    cliente = _get_client()

    try:
        resultado = cliente.service.INCLUIR(CHAVE=chave, PEDIDO=pedido)
    except Fault as e:
        # SOAP Fault = erro de negócio retornado pelo Protheus (STRC* ou Mata120)
        mensagem = str(e.message) if hasattr(e, 'message') else str(e)
        raise RuntimeError(f'Protheus rejeitou o pedido: {mensagem}') from e
    except Exception as e:
        raise RuntimeError(f'Erro na comunicação com o Protheus: {e}') from e

    numero = str(resultado).strip() if resultado else ''
    if not numero:
        raise RuntimeError(
            'Webservice retornou resultado vazio — pedido pode não ter sido criado. '
            'Verifique o log do appserver Protheus.'
        )

    return numero


def resetar_cliente() -> None:
    """Descarta o cliente cached, forçando reinicialização na próxima chamada.

    Útil em testes ou quando as variáveis de ambiente forem alteradas em runtime.
    """
    global _client
    with _lock:
        _client = None
