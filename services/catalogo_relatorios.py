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
            },
            {
                'id': 'historico',
                'titulo': 'Histórico de Pedidos',
                'descricao': 'Todos os pedidos de compra de 2024 até hoje, sem filtro por comprador.',
                'path': '/relatorios/compras/historico',
                'api_base': '/api/relatorios/compras/historico',
                'ativo': True,
            },
            {
                'id': 'pendencia_aprovacao',
                'titulo': 'Pendências de Aprovação',
                'descricao': 'Pedidos de compra com aprovação pendente, filtrável por aprovador e período.',
                'path': '/relatorios/compras/pendencia-aprovacao',
                'api_base': '/api/relatorios/compras/pendencia-aprovacao',
                'ativo': True,
            },
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
    {
        'id': 'financeiro',
        'titulo': 'Controladoria Financeira',
        'descricao': 'Movimentações financeiras do ERP Protheus: NFs, títulos e movimentos bancários.',
        'relatorios': [
            {
                'id': 'nf_entrada',
                'titulo': 'NF de Entrada',
                'descricao': 'Itens das Notas Fiscais de Entrada (SD1) a partir de 2024.',
                'path': '/relatorios/financeiro/nf-entrada',
                'api_base': '/api/relatorios/financeiro/nf-entrada',
                'ativo': True,
            },
            {
                'id': 'nf_saida',
                'titulo': 'NF de Saída',
                'descricao': 'Itens das Notas Fiscais de Saída (SD2) a partir de 2024.',
                'path': '/relatorios/financeiro/nf-saida',
                'api_base': '/api/relatorios/financeiro/nf-saida',
                'ativo': True,
            },
            {
                'id': 'contas_receber',
                'titulo': 'Contas a Receber',
                'descricao': 'Títulos a receber (SE1) emitidos a partir de 2024.',
                'path': '/relatorios/financeiro/contas-receber',
                'api_base': '/api/relatorios/financeiro/contas-receber',
                'ativo': True,
            },
            {
                'id': 'contas_pagar',
                'titulo': 'Contas a Pagar',
                'descricao': 'Títulos a pagar (SE2) emitidos a partir de 2024.',
                'path': '/relatorios/financeiro/contas-pagar',
                'api_base': '/api/relatorios/financeiro/contas-pagar',
                'ativo': True,
            },
            {
                'id': 'mov_bancarios',
                'titulo': 'Movimentos Bancários',
                'descricao': 'Movimentos bancários (SE5) registrados a partir de 2024.',
                'path': '/relatorios/financeiro/mov-bancarios',
                'api_base': '/api/relatorios/financeiro/mov-bancarios',
                'ativo': True,
            },
        ],
    },
    {
        'id': 'energy',
        'titulo': 'Energy',
        'descricao': 'Relatórios do negócio Energy (E2_ITEMD = 05.001).',
        'relatorios': [
            {
                'id': 'contas_pagar',
                'titulo': 'Contas a Pagar',
                'descricao': 'Títulos a pagar (SE2) do negócio Energy, excluindo naturezas internas.',
                'path': '/relatorios/energy/contas-pagar',
                'api_base': '/api/relatorios/energy/contas-pagar',
                'ativo': True,
            },
            {
                'id': 'pedidos',
                'titulo': 'Pedidos de Compra',
                'descricao': 'Pedidos de compra (SC7) dos compradores do setor Energy.',
                'path': '/relatorios/energy/pedidos',
                'api_base': '/api/relatorios/energy/pedidos',
                'ativo': True,
            },
            {
                'id': 'pedidos_conta_05001',
                'titulo': 'Pedidos — Conta 05.001',
                'descricao': 'Todos os pedidos de compra com item contábil 05.001, independente do comprador.',
                'path': '/relatorios/energy/pedidos-conta-05001',
                'api_base': '/api/relatorios/energy/pedidos-conta-05001',
                'ativo': True,
            },
        ],
    },
]


def chave_relatorio(modulo_id, relatorio_id):
    return f'{modulo_id}.{relatorio_id}'


def listar_modulos():
    return RELATORIOS_CATALOGO


def listar_relatorios_flat(incluir_admin_only=False):
    """Retorna a lista plana de relatórios do catálogo.

    Por padrão exclui relatórios marcados com admin_only=True para que não
    entrem no sistema de permissões de usuários regulares.
    Passe incluir_admin_only=True para obter todas as chaves válidas (ex.: tokens OData).
    """
    relatorios = []
    for modulo in RELATORIOS_CATALOGO:
        for relatorio in modulo['relatorios']:
            if not incluir_admin_only and relatorio.get('admin_only'):
                continue
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
