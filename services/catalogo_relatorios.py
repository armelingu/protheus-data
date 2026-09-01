RELATORIOS_CATALOGO = [
    {
        'id': 'compras',
        'titulo': 'Compras',
        'descricao': 'Pedidos de compra e o que ainda precisa de aprovação.',
        'relatorios': [
            {
                'id': 'pedidos',
                'titulo': 'Pedidos de Compra',
                'descricao': 'Lista os pedidos de compra dos compradores do setor.',
                'path': '/relatorios/compras/pedidos',
                'api_base': '/api/relatorios/compras/pedidos',
                'ativo': False,
            },
            {
                'id': 'historico',
                'titulo': 'Histórico de Pedidos',
                'descricao': 'Todos os pedidos de compra desde 2024, sem filtrar por comprador.',
                'path': '/relatorios/compras/historico',
                'api_base': '/api/relatorios/compras/historico',
                'ativo': False,
            },
            {
                'id': 'pendencia_aprovacao',
                'titulo': 'Pendências de Aprovação',
                'descricao': 'Pedidos de compra que ainda aguardam aprovação. Dá para filtrar por aprovador e período.',
                'path': '/relatorios/compras/pendencia-aprovacao',
                'api_base': '/api/relatorios/compras/pendencia-aprovacao',
                'ativo': True,
            },
            {
                'id': 'pedidos_detalhado',
                'titulo': 'Pedidos de Compra',
                'descricao': 'Pedidos de compra com centro de custo, item orçamentário, conta, condição de pagamento, data da última edição e revisão.',
                'path': '/relatorios/compras/pedidos-detalhado',
                'api_base': '/api/relatorios/compras/pedidos-detalhado',
                'ativo': True,
            },
        ],
    },
    {
        'id': 'estoque',
        'titulo': 'Estoque',
        'descricao': 'Quanto há de cada produto em cada filial e armazém.',
        'relatorios': [
            {
                'id': 'saldos',
                'titulo': 'Saldo em Estoque',
                'descricao': 'Saldo atual de cada produto por filial e armazém, incluindo o que já está reservado.',
                'path': '/relatorios/estoque/saldos',
                'api_base': '/api/relatorios/estoque/saldos',
                'ativo': True,
            }
        ],
    },
    {
        'id': 'financeiro',
        'titulo': 'Controladoria Financeira',
        'descricao': 'Notas fiscais, contas a pagar e a receber, movimentos bancários e cadastro de fornecedores.',
        'relatorios': [
            {
                'id': 'nf_entrada',
                'titulo': 'NF de Entrada',
                'descricao': 'Itens das notas fiscais de entrada (compras) a partir de 2024.',
                'path': '/relatorios/financeiro/nf-entrada',
                'api_base': '/api/relatorios/financeiro/nf-entrada',
                'ativo': True,
            },
            {
                'id': 'nf_saida',
                'titulo': 'NF de Saída',
                'descricao': 'Itens das notas fiscais de saída (vendas) a partir de 2024.',
                'path': '/relatorios/financeiro/nf-saida',
                'api_base': '/api/relatorios/financeiro/nf-saida',
                'ativo': True,
            },
            {
                'id': 'contas_receber',
                'titulo': 'Contas a Receber',
                'descricao': 'O que a empresa tem a receber de clientes, a partir de 2024.',
                'path': '/relatorios/financeiro/contas-receber',
                'api_base': '/api/relatorios/financeiro/contas-receber',
                'ativo': True,
            },
            {
                'id': 'contas_pagar',
                'titulo': 'Contas a Pagar',
                'descricao': 'O que a empresa tem a pagar a fornecedores, a partir de 2024.',
                'path': '/relatorios/financeiro/contas-pagar',
                'api_base': '/api/relatorios/financeiro/contas-pagar',
                'ativo': True,
            },
            {
                'id': 'mov_bancarios',
                'titulo': 'Movimentos Bancários',
                'descricao': 'Entradas e saídas nas contas bancárias, a partir de 2024.',
                'path': '/relatorios/financeiro/mov-bancarios',
                'api_base': '/api/relatorios/financeiro/mov-bancarios',
                'ativo': True,
            },
            {
                'id': 'fornecedores',
                'titulo': 'Fornecedores',
                'descricao': 'Cadastro de fornecedores do Protheus: identificação, endereço, banco, natureza e situação.',
                'path': '/relatorios/financeiro/fornecedores',
                'api_base': '/api/relatorios/financeiro/fornecedores',
                'ativo': True,
            },
        ],
    },
    {
        'id': 'energy',
        'titulo': 'Energy',
        'descricao': 'Compras e financeiro do negócio Energy.',
        'relatorios': [
            {
                'id': 'contas_pagar',
                'titulo': 'Contas a Pagar',
                'descricao': 'O que o negócio Energy tem a pagar, sem os lançamentos só de uso interno.',
                'path': '/relatorios/energy/contas-pagar',
                'api_base': '/api/relatorios/energy/contas-pagar',
                'ativo': True,
            },
            {
                'id': 'pedidos',
                'titulo': 'Pedidos de Compra',
                'descricao': 'Pedidos de compra dos compradores do setor Energy.',
                'path': '/relatorios/energy/pedidos',
                'api_base': '/api/relatorios/energy/pedidos',
                'ativo': False,
            },
            {
                'id': 'pedidos_conta_05001',
                'titulo': 'Pedidos de Compra',
                'descricao': 'Pedidos de compra do Energy: da conta do negócio e dos compradores do setor, com o status de aprovação.',
                'path': '/relatorios/energy/pedidos-conta-05001',
                'api_base': '/api/relatorios/energy/pedidos-conta-05001',
                'ativo': True,
            },
            {
                'id': 'nf_saida',
                'titulo': 'Contas a Receber',
                'descricao': 'O que o negócio Energy tem a receber, a partir de 2024.',
                'path': '/relatorios/energy/nf-saida',
                'api_base': '/api/relatorios/energy/nf-saida',
                'ativo': True,
            },
        ],
    },
]


def chave_relatorio(modulo_id, relatorio_id):
    return f'{modulo_id}.{relatorio_id}'


def chaves_acesso_equivalentes(modulo_id, relatorio_id):
    """Chaves de permissão que liberam o relatório, incluindo sucessor de relatório desativado."""
    chave = chave_relatorio(modulo_id, relatorio_id)
    if modulo_id == 'compras' and relatorio_id == 'pedidos_detalhado':
        return {chave, 'compras.pedidos'}
    if modulo_id == 'energy' and relatorio_id == 'pedidos_conta_05001':
        return {chave, 'energy.pedidos'}
    return {chave}


def relatorio_esta_ativo(modulo_id, relatorio_id):
    _, relatorio = obter_relatorio(modulo_id, relatorio_id)
    if not relatorio:
        return False
    return bool(relatorio.get('ativo', True))


def listar_modulos():
    return RELATORIOS_CATALOGO


def listar_relatorios_flat(incluir_admin_only=False, incluir_inativos=False):
    """Retorna a lista plana de relatórios do catálogo.

    Por padrão exclui relatórios marcados com admin_only=True para que não
    entrem no sistema de permissões de usuários regulares.
    Passe incluir_admin_only=True para obter todas as chaves válidas (ex.: tokens OData).
    Relatórios com ativo=False ficam de fora do menu e das permissões, a menos
    que incluir_inativos=True.
    """
    relatorios = []
    for modulo in RELATORIOS_CATALOGO:
        for relatorio in modulo['relatorios']:
            if not incluir_admin_only and relatorio.get('admin_only'):
                continue
            if not incluir_inativos and not relatorio.get('ativo', True):
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
