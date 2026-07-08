"""
Validações client-side para o módulo PedCom.

Espelha o checklist da seção 7 da documentação WSHBPEDC, evitando chamadas
ao webservice com dados obviamente inválidos. Não faz consulta ao Protheus —
isso é responsabilidade do próprio .prw (validações STRC010 a STRC019).

Todas as funções retornam list[str] com as mensagens de erro encontradas.
Lista vazia = dados válidos.
"""
from __future__ import annotations


def _parse_valor(valor) -> float:
    """Converte string de valor monetário (BR ou US) para float.

    Espelha a lógica do fParseValor do WSHBPEDC_7.prw:
    - Detecta o separador decimal pela ÚLTIMA ocorrência de ',' ou '.'
    - Tudo antes do separador decimal é tratado como separador de milhar e removido
    - Sem separador = inteiro
    """
    s = str(valor).strip()
    if not s:
        return 0.0

    pos_ponto = s.rfind('.')
    pos_virgula = s.rfind(',')

    if pos_ponto > pos_virgula:
        # separador decimal é o ponto (formato US ou BR sem vírgula)
        limpo = s[:pos_ponto].replace(',', '') + '.' + s[pos_ponto + 1:]
    elif pos_virgula > pos_ponto:
        # separador decimal é a vírgula (formato BR)
        limpo = s[:pos_virgula].replace('.', '') + '.' + s[pos_virgula + 1:]
    else:
        # nenhum separador — inteiro
        limpo = s

    try:
        return float(limpo)
    except ValueError:
        return 0.0


def validar_item(item: dict) -> list[str]:
    """Valida um único item de pedido antes de enviar ao WS.

    Parâmetros
    ----------
    item : dict
        Campos obrigatórios: CODFORNECEDOR, LOJAFORNEC, CODIGOCOND, CODCC,
        CODCLVL, CODIGOPRODUTO, MESINICIAL, ANOREFERENCIA, QTDMESES, rateios.
        rateios: list[dict] com CODITEMCTA e VALORMENSAL por item.
    """
    erros: list[str] = []

    # ── Campos de cabeçalho obrigatórios ─────────────────────────────────────
    campos_obrigatorios = {
        'CODFORNECEDOR': 'Código do fornecedor',
        'LOJAFORNEC':    'Loja do fornecedor',
        'CODIGOCOND':    'Condição de pagamento',
        'CODCC':         'Centro de custo',
        'CODCLVL':       'Classe de valor',
        'CODIGOPRODUTO': 'Código do produto',
    }
    for campo, label in campos_obrigatorios.items():
        if not str(item.get(campo, '')).strip():
            erros.append(f'{label} é obrigatório.')

    # ── Mês inicial ───────────────────────────────────────────────────────────
    try:
        mes = int(item.get('MESINICIAL', 0))
        if mes < 1 or mes > 12:
            erros.append('Mês inicial deve ser entre 1 e 12.')
    except (ValueError, TypeError):
        erros.append('Mês inicial inválido (deve ser um número de 1 a 12).')

    # ── Ano de referência ─────────────────────────────────────────────────────
    try:
        ano = int(item.get('ANOREFERENCIA', 0))
        if ano < 2000 or ano > 2100:
            erros.append('Ano de referência inválido.')
    except (ValueError, TypeError):
        erros.append('Ano de referência inválido (deve ser um número com 4 dígitos).')

    # ── Quantidade de meses ───────────────────────────────────────────────────
    try:
        qtd = int(item.get('QTDMESES', 0))
        if qtd <= 0:
            erros.append('Quantidade de meses deve ser maior que zero.')
    except (ValueError, TypeError):
        erros.append('Quantidade de meses inválida (deve ser um número inteiro positivo).')

    # ── Rateios ───────────────────────────────────────────────────────────────
    rateios = item.get('rateios', [])
    if not rateios:
        erros.append('O pedido deve ter pelo menos um rateio (Item Contábil).')
    else:
        for i, r in enumerate(rateios, start=1):
            if not str(r.get('CODITEMCTA', '')).strip():
                erros.append(f'Item contábil do rateio {i} é obrigatório.')
            valor = _parse_valor(r.get('VALORMENSAL', 0))
            if valor <= 0:
                erros.append(
                    f'Valor mensal do rateio {i} deve ser maior que zero '
                    f'(recebido: {r.get("VALORMENSAL", "")!r}).'
                )

    return erros


def validar_lote(itens: list[dict]) -> list[str]:
    """Valida consistência do lote inteiro antes de persistir.

    Verifica:
    - Lote não pode estar vazio
    - CODCC e CODCLVL devem ser iguais em todos os itens
    """
    erros: list[str] = []

    if not itens:
        erros.append('O lote não contém itens.')
        return erros

    codccs = {str(i.get('CODCC', '')).strip() for i in itens}
    codclvls = {str(i.get('CODCLVL', '')).strip() for i in itens}

    if len(codccs) > 1:
        erros.append(
            f'CODCC não é único no lote — valores encontrados: {", ".join(sorted(codccs))}. '
            'Todos os pedidos do mesmo lote semestral devem usar o mesmo Centro de Custo.'
        )
    if len(codclvls) > 1:
        erros.append(
            f'CODCLVL não é único no lote — valores encontrados: {", ".join(sorted(codclvls))}. '
            'Todos os pedidos do mesmo lote semestral devem usar a mesma Classe de Valor.'
        )

    return erros
