import os
import re

import pyodbc


DB_SERVER = os.getenv('DB_SERVER')
DB_DATABASE = os.getenv('DB_DATABASE')
DB_USERNAME = os.getenv('DB_USERNAME')
DB_PASSWORD = os.getenv('DB_PASSWORD')

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


def validar_query_somente_leitura(query):
    query_limpa = query.strip()
    if not query_limpa.upper().startswith('SELECT'):
        raise ValueError('Apenas consultas SELECT são permitidas no Protheus.')

    for palavra in PALAVRAS_BLOQUEADAS:
        if re.search(r'\b' + palavra + r'\b', query_limpa, flags=re.IGNORECASE):
            raise ValueError(f'Comando não permitido em produção do Protheus: {palavra}')


def conectar_protheus_readonly():
    conn_str = (
        f"DRIVER={{ODBC Driver 17 for SQL Server}};"
        f"SERVER={DB_SERVER};"
        f"DATABASE={DB_DATABASE};"
        f"UID={DB_USERNAME};"
        f"PWD={DB_PASSWORD};"
        f"TrustServerCertificate=yes;"
        f"ApplicationIntent=ReadOnly;"
    )
    conn = pyodbc.connect(conn_str, autocommit=False)
    conn.execute("SET TRANSACTION ISOLATION LEVEL READ UNCOMMITTED")
    return conn


def executar_select(query, params=None):
    validar_query_somente_leitura(query)
    conn = conectar_protheus_readonly()
    cursor = conn.cursor()
    if params:
        cursor.execute(query, params)
    else:
        cursor.execute(query)
    linhas = cursor.fetchall()
    cursor.close()
    conn.close()
    return linhas
