from werkzeug.security import generate_password_hash
from catalogo_relatorios import listar_relatorios_flat
from database import conectar_users, criar_tabelas, agora

criar_tabelas()

print('=== Criar Usuário ===')
nome = input('Nome: ').strip()
usuario = input('Usuário: ').strip()
senha = input('Senha: ').strip()

if not nome or not usuario or not senha:
    print('Erro: todos os campos são obrigatórios.')
    exit(1)

senha_hash = generate_password_hash(senha)

conn = conectar_users()
try:
    cursor = conn.execute(
        '''
        INSERT INTO usuarios (
            usuario, senha, nome, criado_em, ativo, is_admin, deve_trocar_senha, atualizado_em
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''',
        (usuario, senha_hash, nome, agora(), 1, 0, 0, agora())
    )

    permissoes = [
        (cursor.lastrowid, relatorio['modulo_id'], relatorio['relatorio_id'], 1, agora(), agora())
        for relatorio in listar_relatorios_flat()
    ]
    conn.executemany(
        '''
        INSERT INTO usuario_permissoes_relatorio
        (usuario_id, modulo_id, relatorio_id, permitido, criado_em, atualizado_em)
        VALUES (?, ?, ?, ?, ?, ?)
        ''',
        permissoes
    )
    conn.commit()
    print(f'Usuário "{usuario}" cadastrado com sucesso!')
except Exception:
    print(f'Erro: usuário "{usuario}" já existe.')
conn.close()
