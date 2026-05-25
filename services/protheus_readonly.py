import os
import re
import time

import pyodbc


DB_SERVER   = os.getenv('DB_SERVER')
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USERNAME = os.getenv('DB_USERNAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')

# Timeout de conexão (estabelecer o socket TCP + login SQL Server).
# Configurável via .env; padrão conservador de 10s.
PROTHEUS_CONNECT_TIMEOUT = int(os.getenv('PROTHEUS_CONNECT_TIMEOUT', '10'))

# Timeout de execução de query (tempo máximo que um SELECT pode rodar).
# Queries complexas no Protheus costumam terminar em <30s; 60s é margem segura.
PROTHEUS_QUERY_TIMEOUT = int(os.getenv('PROTHEUS_QUERY_TIMEOUT', '60'))

# Quantas vezes tentar novamente em caso de erro transiente (rede, timeout).
# Erros permanentes (permissão, tabela inexistente) não geram retry.
PROTHEUS_MAX_RETRIES = int(os.getenv('PROTHEUS_MAX_RETRIES', '2'))

PALAVRAS_BLOQUEADAS = (
    'INSERT',
    'UPDATE',
    'DELETE',
    'MERGE',
    'ALTER',
    'DROP',
    'TRUNCATE',
    'CREATE',
    'EXEC',
    'EXECUTE',
    'GRANT',
    'REVOKE',
)

# Fragmentos de mensagem que indicam erro de rede/timeout — passíveis de retry.
_ERROS_TRANSIENTES = (
    'timeout',
    'timed out',
    'connection reset',
    'connection refused',
    'server has gone away',
    'broken pipe',
    'network',
    'communication link failure',
    'unable to connect',
    'sql server is unavailable',
    '08001',   # SQLSTATE: client unable to establish connection
    '08s01',   # SQLSTATE: communication link failure
    'ht000',   # SQLSTATE: general error (pyodbc genérico de rede)
)


def _e_erro_transiente(e: Exception) -> bool:
    """Retorna True se o erro é de rede/timeout e pode ser tentado novamente."""
    msg = str(e).lower()
    return any(trecho in msg for trecho in _ERROS_TRANSIENTES)


def validar_query_somente_leitura(query):
    query_limpa = query.strip()
    if not query_limpa.upper().startswith('SELECT'):
        raise ValueError('Apenas consultas SELECT são permitidas no Protheus.')

    for palavra in PALAVRAS_BLOQUEADAS:
        if re.search(r'\b' + palavra + r'\b', query_limpa, flags=re.IGNORECASE):
            raise ValueError(f'Comando não permitido em produção do Protheus: {palavra}')


def conectar_protheus_readonly():
    """Abre conexão com o SQL Server Protheus com timeout de conexão configurável.

    LoginTimeout na connection string controla o tempo máximo para estabelecer
    o socket TCP + autenticar. O pyodbc timeout= repete essa configuração para
    garantir cobertura independente do driver ODBC.
    """
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_DATABASE};"
        f"UID={DB_USERNAME};"
        f"PWD={DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
        f"ApplicationIntent=ReadOnly;"
        f"LoginTimeout={PROTHEUS_CONNECT_TIMEOUT};"
    )
    conn = pyodbc.connect(conn_str, timeout=PROTHEUS_CONNECT_TIMEOUT)
    # conn.timeout define o limite para cada cursor.execute() subsequente.
    conn.timeout = PROTHEUS_QUERY_TIMEOUT
    conn.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
    return conn


def executar_select(query, params=None):
    """Executa SELECT no Protheus com timeout e retry em erros transientes.

    - Erros de rede/timeout: retenta até PROTHEUS_MAX_RETRIES vezes com
      backoff linear de 5s entre tentativas.
    - Erros permanentes (permissão, objeto inexistente): propaga imediatamente
      sem retry para não desperdiçar tempo.
    - Conexão sempre fechada no bloco finally, mesmo em caso de exceção.
    """
    validar_query_somente_leitura(query)

    ultimo_erro = None
    for tentativa in range(1, PROTHEUS_MAX_RETRIES + 1):
        conn = None
        try:
            conn = conectar_protheus_readonly()
            cursor = conn.cursor()
            if params:
                cursor.execute(query, params)
            else:
                cursor.execute(query)
            linhas = cursor.fetchall()
            cursor.close()
            return linhas
        except Exception as e:
            ultimo_erro = e
            if tentativa < PROTHEUS_MAX_RETRIES and _e_erro_transiente(e):
                espera = tentativa * 5
                print(
                    f'[PROTHEUS] Tentativa {tentativa}/{PROTHEUS_MAX_RETRIES} falhou '
                    f'({type(e).__name__}: {str(e)[:120]}). '
                    f'Aguardando {espera}s antes de tentar novamente.'
                )
                time.sleep(espera)
            else:
                # Erro permanente ou esgotadas as tentativas — propaga imediatamente.
                break
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    raise ultimo_erro
