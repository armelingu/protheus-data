/**
 * PedCom — página de histórico de lotes (/rh/pedcom/historico)
 *
 * Carrega a lista paginada de lotes e permite expandir cada um
 * para ver o resultado por colaborador.
 */

'use strict';

// ─── Estado ───────────────────────────────────────────────────────────────────
let _pagina     = 1;
const _porPagina = 20;
let _loteAberto = null;  // ID do lote atualmente expandido

// ─── Utilitários ─────────────────────────────────────────────────────────────

function _esc(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}

function fmtData(iso) {
    if (!iso) return '—';
    const d = new Date(iso.replace(' ', 'T'));
    if (isNaN(d)) return iso;
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

function csrf() {
    return document.querySelector('meta[name="csrf-token"]')?.content ?? '';
}

function toast(tipo, texto, duracao = 5000) {
    const el = document.getElementById('mensagem');
    if (!el) return;
    el.className = `mensagem ${tipo} visivel`;
    el.textContent = texto;
    clearTimeout(el._t);
    if (duracao > 0) el._t = setTimeout(() => { el.className = 'mensagem'; }, duracao);
}

function badgeStatus(status) {
    const map = {
        pendente:             ['pendente',     'Pendente'],
        processando:          ['processando',  'Processando'],
        concluido:            ['sucesso',      '✓ Concluído'],
        concluido_com_falhas: ['falha',        '⚠ Com falhas'],
    };
    const [cls, label] = map[status] ?? ['pendente', status];
    return `<span class="pedcom-badge ${cls}">${_esc(label)}</span>`;
}

// ─── Carrega lista de lotes ───────────────────────────────────────────────────

async function carregarLotes(pagina = 1) {
    _pagina = pagina;
    const wrap = document.getElementById('lotes-wrap');
    wrap.innerHTML = '<div class="pedcom-loading">Carregando...</div>';
    document.getElementById('detalhe-container').style.display = 'none';
    document.getElementById('paginacao').innerHTML = '';

    try {
        const res  = await fetch(`/api/rh/pedcom/lotes?pagina=${pagina}&por_pagina=${_porPagina}`, {
            headers: { 'X-CSRF-Token': csrf() },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();

        renderTabela(data.lotes ?? []);
        renderPaginacao(data.total ?? 0, pagina);

    } catch (e) {
        wrap.innerHTML = `<div class="pedcom-vazio"><strong>Erro ao carregar histórico.</strong>${e.message}</div>`;
    }
}

function renderTabela(lotes) {
    const wrap = document.getElementById('lotes-wrap');

    if (!lotes.length) {
        wrap.innerHTML = `
            <div class="pedcom-vazio">
                <strong>Nenhum lote encontrado.</strong>
                Use <a href="/rh/pedcom">Novo Lote</a> para criar o primeiro lote.
            </div>`;
        return;
    }

    const linhas = lotes.map(lote => {
        const totaisHtml = `
            <div class="pedcom-lote-totais">
                <span class="t-ok">✓ ${lote.sucesso ?? 0}</span>
                <span class="t-err">✕ ${lote.falha ?? 0}</span>
                <span class="t-pen">⌛ ${lote.pendente ?? 0}</span>
            </div>`;

        return `
        <tr data-lote-id="${lote.id}" title="Ver detalhes do lote ${lote.id}">
            <td style="color:#8a8a8a;font-size:11px">#${lote.id}</td>
            <td class="pedcom-lote-data">${fmtData(lote.criado_em)}</td>
            <td style="color:#5a5a5a;font-size:11px">${_esc(lote.criado_por_nome || '—')}</td>
            <td class="pedcom-lote-nome">${_esc(lote.nome_lote || '—')}</td>
            <td style="font-family:monospace;font-size:11px;color:#5a5a5a">${_esc(lote.codcc || '—')}</td>
            <td style="text-align:center;font-weight:600">${lote.total ?? 0}</td>
            <td>${totaisHtml}</td>
            <td>${badgeStatus(lote.status)}</td>
            <td style="color:#adadad;font-size:11px">${fmtData(lote.concluido_em)}</td>
        </tr>`;
    }).join('');

    wrap.innerHTML = `
        <table class="pedcom-lotes-table">
            <thead>
                <tr>
                    <th>#</th>
                    <th>Data</th>
                    <th>Usuário</th>
                    <th>Arquivo / Lote</th>
                    <th>CC</th>
                    <th style="text-align:center">Total</th>
                    <th>Resultados</th>
                    <th>Status</th>
                    <th>Concluído em</th>
                </tr>
            </thead>
            <tbody>${linhas}</tbody>
        </table>`;

    // Clique em linha → expande detalhe
    wrap.querySelectorAll('tbody tr').forEach(tr => {
        tr.addEventListener('click', () => {
            const id = parseInt(tr.dataset.loteId, 10);
            if (_loteAberto === id) {
                fecharDetalhe();
            } else {
                abrirDetalhe(id);
            }
        });
    });
}

function renderPaginacao(total, pagina) {
    const totalPags = Math.ceil(total / _porPagina);
    if (totalPags <= 1) return;

    const wrap = document.getElementById('paginacao');
    const btnStyle = 'padding:6px 12px;border:1px solid #e2e2e2;background:#fff;font-family:inherit;font-size:11px;font-weight:600;cursor:pointer;color:#555;transition:all .15s';

    let html = '';
    if (pagina > 1) {
        html += `<button style="${btnStyle}" data-p="${pagina - 1}">← Anterior</button>`;
    }
    html += `<span style="font-size:11px;color:#8a8a8a;align-self:center">Página ${pagina} de ${totalPags}</span>`;
    if (pagina < totalPags) {
        html += `<button style="${btnStyle}" data-p="${pagina + 1}">Próxima →</button>`;
    }

    wrap.innerHTML = html;
    wrap.querySelectorAll('button[data-p]').forEach(btn => {
        btn.addEventListener('click', () => carregarLotes(parseInt(btn.dataset.p, 10)));
    });
}

// ─── Detalhe do lote ──────────────────────────────────────────────────────────

async function abrirDetalhe(loteId) {
    _loteAberto = loteId;
    const container = document.getElementById('detalhe-container');
    container.style.display = 'block';
    container.innerHTML = `<div class="pedcom-detalhe"><div class="pedcom-loading">Carregando lote #${loteId}...</div></div>`;
    container.scrollIntoView({ behavior: 'smooth', block: 'nearest' });

    try {
        const res  = await fetch(`/api/rh/pedcom/lote/${loteId}`, {
            headers: { 'X-CSRF-Token': csrf() },
        });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        const data = await res.json();
        renderDetalhe(loteId, data);
    } catch (e) {
        container.innerHTML = `<div class="pedcom-detalhe"><div class="pedcom-vazio"><strong>Erro ao carregar detalhes.</strong>${e.message}</div></div>`;
    }
}

function fecharDetalhe() {
    _loteAberto = null;
    const container = document.getElementById('detalhe-container');
    container.style.display = 'none';
    container.innerHTML = '';
}

function renderDetalhe(loteId, data) {
    const lote  = data.lote  ?? {};
    const itens = data.itens ?? [];
    const container = document.getElementById('detalhe-container');

    const linhasItens = itens.map(item => {
        const pedidoHtml = item.numero_pedido
            ? `<span class="pedcom-num-pedido">${_esc(item.numero_pedido)}</span>`
            : '<span style="color:#adadad">—</span>';
        const obsHtml = item.status === 'falha' && item.erro
            ? `<span class="pedcom-erro-resumo" title="${_esc(item.erro)}">${_esc(item.erro)}</span>`
            : '';
        const badgeHtml = badgeItemStatus(item.status);

        return `
        <tr>
            <td style="color:#3a3a3a;font-weight:600">${_esc(item.nome_colaborador || '—')}</td>
            <td style="font-family:monospace;font-size:11px;color:#5a5a5a">${_esc(item.codfornecedor || '—')} / ${_esc(item.lojafornec || '—')}</td>
            <td>${badgeHtml}</td>
            <td>${pedidoHtml}</td>
            <td>${obsHtml}</td>
            <td style="color:#adadad;font-size:11px;white-space:nowrap">${fmtData(item.concluido_em)}</td>
        </tr>`;
    }).join('') || '<tr><td colspan="6" class="pedcom-vazio">Nenhum item encontrado.</td></tr>';

    container.innerHTML = `
        <div class="pedcom-detalhe">
            <div class="pedcom-detalhe-header">
                <div>
                    <span class="pedcom-detalhe-titulo">Lote #${loteId} — ${_esc(lote.nome_lote || '—')}</span>
                    <span style="color:#adadad;font-size:11px;margin-left:12px">
                        ${fmtData(lote.criado_em)} · ${_esc(lote.criado_por_nome || '—')} ·
                        CC: ${_esc(lote.codcc || '—')} · CLVL: ${_esc(lote.codclvl || '—')}
                    </span>
                </div>
                <button class="pedcom-detalhe-fechar" id="btn-fechar-detalhe">Fechar ✕</button>
            </div>
            <div style="overflow-x:auto">
                <table class="pedcom-itens-table">
                    <thead>
                        <tr>
                            <th>Colaborador</th>
                            <th>Fornecedor / Loja</th>
                            <th>Status</th>
                            <th>Pedido (C7_NUM)</th>
                            <th>Observação</th>
                            <th>Concluído em</th>
                        </tr>
                    </thead>
                    <tbody>${linhasItens}</tbody>
                </table>
            </div>
        </div>`;

    document.getElementById('btn-fechar-detalhe')?.addEventListener('click', fecharDetalhe);
}

function badgeItemStatus(status) {
    const map = {
        pendente:    ['pendente',    'Pendente'],
        processando: ['processando', 'Processando'],
        sucesso:     ['sucesso',     '✓ Sucesso'],
        falha:       ['falha',       '✕ Falha'],
    };
    const [cls, label] = map[status] ?? ['pendente', status];
    return `<span class="pedcom-badge ${cls}">${_esc(label)}</span>`;
}

// ─── Init ─────────────────────────────────────────────────────────────────────
carregarLotes(1);
