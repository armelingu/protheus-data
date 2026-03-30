RELATORIOS_CATALOGO = [
    {
        'id': 'compras',
        'titulo': 'Compras',
        'descricao': 'Relatórios de pedidos, fornecedores e processos de compra.',
        'relatorios': [
            {
                'id': 'pedidos',
                'titulo': 'Pedidos de Compra',
                'descricao': 'Consulta, sincronização e exportação de pedidos de compra.',
                'path': '/relatorios/compras/pedidos',
                'api_base': '/api/relatorios/compras/pedidos',
                'ativo': True,
            }
        ],
    },
    {
        'id': 'estoque',
        'titulo': 'Estoque',
        'descricao': 'Relatórios de saldo, disponibilidade e visão atual do estoque.',
        'relatorios': [
            {
                'id': 'saldos',
                'titulo': 'Saldo em Estoque',
                'descricao': 'Consulta, sincronização e exportação do saldo atual por filial e armazém.',
                'path': '/relatorios/estoque/saldos',
                'api_base': '/api/relatorios/estoque/saldos',
                'ativo': True,
            }
        ],
    },
]


def chave_relatorio(modulo_id, relatorio_id):
    return f'{modulo_id}.{relatorio_id}'


def listar_modulos():
    return RELATORIOS_CATALOGO


def listar_relatorios_flat():
    relatorios = []
    for modulo in RELATORIOS_CATALOGO:
        for relatorio in modulo['relatorios']:
            relatorios.append({
                'modulo_id': modulo['id'],
                'modulo_titulo': modulo['titulo'],
                'relatorio_id': relatorio['id'],
                'chave': chave_relatorio(modulo['id'], relatorio['id']),
                **relatorio,
            })
    return relatorios


def obter_relatorio(modulo_id, relatorio_id):
    for modulo in RELATORIOS_CATALOGO:
        if modulo['id'] != modulo_id:
            continue
        for relatorio in modulo['relatorios']:
            if relatorio['id'] == relatorio_id:
                return modulo, relatorio
    return None, None
