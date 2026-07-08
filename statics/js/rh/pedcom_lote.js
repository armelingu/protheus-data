/**
 * PedCom — página de criação de lote (/rh/pedcom)
 *
 * Máquina de estados com 3 etapas:
 *   upload      → o usuário seleciona/arrasta o .xlsx e clica "Analisar"
 *   preview     → exibe a tabela de collaboradores para confirmação
 *   processando → dispara o lote e faz polling a cada 3 s até concluir
 */

'use strict';

// ─── Utilitários ─────────────────────────────────────────────────────────────

const csrf = () => document.querySelector('meta[name="csrf-token"]')?.content ?? '';

function toast(tipo, texto, duracao = 5000) {
    const el = document.getElementById('mensagem');
    if (!el) return;
    el.className = `mensagem ${tipo} visivel`;
    el.textContent = texto;
    clearTimeout(el._t);
    if (duracao > 0) {
        el._t = setTimeout(() => {
            el.className = 'mensagem';
        }, duracao);
    }
}

function fmtMoeda(val) {
    const n = parseFloat(String(val).replace(',', '.'));
    if (isNaN(n)) return val;
    return n.toLocaleString('pt-BR', { style: 'currency', currency: 'BRL', minimumFractionDigits: 2 });
}

function fmtData(iso) {
    if (!iso) return '—';
    const d = new Date(iso.replace(' ', 'T'));
    if (isNaN(d)) return iso;
    return d.toLocaleString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

// ─── Estado global ────────────────────────────────────────────────────────────

let _arquivo   = null;   // File selecionado
let _itens     = [];     // Lista de itens pós-importação
let _loteId    = null;   // ID do lote após confirmação
let _polling   = null;   // setInterval do polling

// ─── Stepper ─────────────────────────────────────────────────────────────────

function irParaEtapa(num) {
    const etapas = ['upload', 'preview', 'processando'];
    etapas.forEach((id, i) => {
        const stage = document.getElementById(`stage-${id}`);
        const step  = document.getElementById(`step-${i + 1}`);
        if (!stage || !step) return;

        if (i + 1 === num) {
            stage.classList.add('ativa');
            step.className = 'pedcom-step ativo';
        } else if (i + 1 < num) {
            stage.classList.remove('ativa');
            step.className = 'pedcom-step concluido';
            // Substitui o número pelo ✓ via CSS (classe concluido)
            step.querySelector('.pedcom-step-num').textContent = '';
        } else {
            stage.classList.remove('ativa');
            step.className = 'pedcom-step';
            step.querySelector('.pedcom-step-num').textContent = i + 1;
        }
    });
}

// ─── Etapa 1 — Upload ────────────────────────────────────────────────────────

const dropzone    = document.getElementById('dropzone');
const inputArq    = document.getElementById('input-arquivo');
const btnSelec    = document.getElementById('btn-selecionar');
const btnImportar = document.getElementById('btn-importar');
const nomeEl      = document.getElementById('dropzone-nome');
const arqEl       = document.getElementById('dropzone-arquivo');

function selecionarArquivo(file) {
    if (!file || !file.name.toLowerCase().endsWith('.xlsx')) {
        toast('erro', 'Apenas arquivos .xlsx são aceitos.');
        return;
    }
    _arquivo = file;
    nomeEl.textContent = file.name;
    arqEl.style.display = 'flex';
    btnImportar.disabled = false;
    document.getElementById('upload-erros').style.display = 'none';
}

btnSelec.addEventListener('click', (e) => {
    e.stopPropagation();
    inputArq.click();
});

inputArq.addEventListener('change', () => {
    if (inputArq.files[0]) selecionarArquivo(inputArq.files[0]);
});

dropzone.addEventListener('click', (e) => {
    if (e.target === btnSelec) return;
    inputArq.click();
});

dropzone.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); inputArq.click(); }
});

dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.classList.add('drag-over');
});

dropzone.addEventListener('dragleave', () => {
    dropzone.classList.remove('drag-over');
});

dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.classList.remove('drag-over');
    const file = e.dataTransfer?.files?.[0];
    if (file) selecionarArquivo(file);
});

btnImportar.addEventListener('click', async () => {
    if (!_arquivo) return;

    btnImportar.disabled = true;
    btnImportar.textContent = 'Analisando...';
    document.getElementById('upload-erros').style.display = 'none';

    const form = new FormData();
    form.append('arquivo', _arquivo);

    try {
        const res  = await fetch('/api/rh/pedcom/importar', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrf() },
            body: form,
        });
        const data = await res.json();

        if (!res.ok || !data.ok) {
            renderErrosUpload(data.erros || ['Erro desconhecido ao processar a planilha.'], data.avisos || []);
            return;
        }

        _itens = data.itens || [];
        renderPreview(data);

    } catch (e) {
        toast('erro', `Erro de comunicação: ${e.message}`);
    } finally {
        btnImportar.disabled = false;
        btnImportar.textContent = 'Analisar Planilha';
    }
});

function renderErrosUpload(erros, avisos) {
    const wrap = document.getElementById('upload-erros');
    wrap.innerHTML = '';
    avisos.forEach(a => {
        const d = document.createElement('div');
        d.className = 'pedcom-aviso-item';
        d.textContent = a;
        wrap.appendChild(d);
    });
    erros.forEach(e => {
        const d = document.createElement('div');
        d.className = 'pedcom-erro-item';
        d.textContent = e;
        wrap.appendChild(d);
    });
    wrap.style.display = 'block';
}

// ─── Etapa 2 — Preview ───────────────────────────────────────────────────────

function renderPreview(data) {
    // Resumo
    document.getElementById('resumo-total').textContent  = data.total ?? '—';
    document.getElementById('resumo-codcc').textContent  = data.codcc  ?? '—';
    document.getElementById('resumo-codclvl').textContent = data.codclvl ?? '—';

    // Avisos
    const avisosWrap = document.getElementById('preview-avisos');
    if (data.avisos?.length) {
        avisosWrap.innerHTML = data.avisos.map(a => `<div class="pedcom-aviso-item">${_esc(a)}</div>`).join('');
        avisosWrap.style.display = 'block';
    } else {
        avisosWrap.style.display = 'none';
    }

    // Tabela
    const tbody = document.getElementById('preview-tbody');
    if (!_itens.length) {
        tbody.innerHTML = '<tr><td colspan="6" class="pedcom-vazio"><strong>Nenhum colaborador encontrado.</strong></td></tr>';
    } else {
        tbody.innerHTML = _itens.map(item => {
            const rateiosHtml = (item.rateios || []).map(r =>
                `<div class="pedcom-rateio-tag"><strong>${_esc(r.CODITEMCTA)}</strong> ${_esc(fmtMoeda(r.VALORMENSAL))}/mês</div>`
            ).join('');

            return `
            <tr>
                <td class="col-nome">${_esc(item.nome_colaborador || '—')}</td>
                <td class="col-fornec">${_esc(item.CODFORNECEDOR || '—')} / ${_esc(item.LOJAFORNEC || '—')}</td>
                <td>${_esc(item.CODIGOCOND || '—')}</td>
                <td>${_esc(item.CODIGOPRODUTO || '—')}</td>
                <td class="col-periodo">
                    ${_esc(item.MESINICIAL)}/${_esc(item.ANOREFERENCIA)}<br>
                    <span style="color:#adadad;font-size:11px">${_esc(item.QTDMESES)} mês(es)</span>
                </td>
                <td><div class="pedcom-rateios-lista">${rateiosHtml}</div></td>
            </tr>`;
        }).join('');
    }

    irParaEtapa(2);
}

document.getElementById('btn-voltar-upload').addEventListener('click', () => {
    irParaEtapa(1);
});

document.getElementById('btn-confirmar').addEventListener('click', async () => {
    if (!_itens.length) return;

    const btn = document.getElementById('btn-confirmar');
    btn.disabled = true;
    btn.textContent = 'Criando lote...';

    const nomeLote = _arquivo?.name ?? 'Lote manual';

    try {
        const res  = await fetch('/api/rh/pedcom/lote', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRF-Token': csrf(),
            },
            body: JSON.stringify({ itens: _itens, nome_lote: nomeLote }),
        });
        const data = await res.json();

        if (!res.ok) {
            toast('erro', data.erro ?? 'Erro ao criar o lote.', 0);
            return;
        }

        _loteId = data.lote_id;
        iniciarProcessamento();

    } catch (e) {
        toast('erro', `Erro de comunicação: ${e.message}`, 0);
    } finally {
        btn.disabled = false;
        btn.textContent = 'Confirmar e Criar Pedidos';
    }
});

// ─── Etapa 3 — Processamento com polling ─────────────────────────────────────

function iniciarProcessamento() {
    irParaEtapa(3);
    document.getElementById('status-lote-banner').style.display = 'none';
    atualizarStatus();
    _polling = setInterval(atualizarStatus, 3000);
}

async function atualizarStatus() {
    if (!_loteId) return;

    try {
        const res  = await fetch(`/api/rh/pedcom/lote/${_loteId}/status`, {
            headers: { 'X-CSRF-Token': csrf() },
        });
        if (!res.ok) return;

        const data = await res.json();
        renderStatus(data);

        const status = data.lote?.status ?? '';
        if (status === 'concluido' || status === 'concluido_com_falhas') {
            clearInterval(_polling);
            _polling = null;
            renderBannerFinal(status, data.lote);
        }

    } catch (_) {
        // silencioso — tenta de novo no próximo tick
    }
}

function renderStatus(data) {
    const lote  = data.lote  ?? {};
    const itens = data.itens ?? [];

    const total    = lote.total     ?? itens.length;
    const sucesso  = lote.sucesso   ?? 0;
    const falha    = lote.falha     ?? 0;
    const pendente = lote.pendente  ?? 0;

    document.getElementById('cnt-total').textContent   = total;
    document.getElementById('cnt-sucesso').textContent = sucesso;
    document.getElementById('cnt-falha').textContent   = falha;
    document.getElementById('cnt-pendente').textContent = pendente;

    const pctOk  = total > 0 ? Math.round((sucesso / total) * 100) : 0;
    const pctErr = total > 0 ? Math.round((falha   / total) * 100) : 0;
    const barra  = document.getElementById('barra-progresso');
    barra.style.width = `${pctOk + pctErr}%`;
    barra.style.setProperty('--pct-ok', pctOk);
    if (falha > 0) barra.classList.add('tem-falha'); else barra.classList.remove('tem-falha');

    const concluidos = sucesso + falha;
    document.getElementById('barra-texto').textContent = total > 0
        ? `${concluidos} de ${total} processados (${pctOk + pctErr}%)`
        : 'Aguardando...';

    renderTabelaItens(itens);
}

function renderTabelaItens(itens) {
    const tbody = document.getElementById('itens-tbody');

    if (!itens.length) {
        tbody.innerHTML = '<tr><td colspan="5" class="pedcom-loading">Aguardando início...</td></tr>';
        return;
    }

    tbody.innerHTML = itens.map(item => {
        const badgeHtml  = badgeStatus(item.status);
        const pedidoHtml = item.numero_pedido
            ? `<span class="pedcom-num-pedido">${_esc(item.numero_pedido)}</span>`
            : '<span style="color:#adadad">—</span>';
        const obsHtml = item.status === 'falha' && item.erro
            ? `<span class="pedcom-erro-resumo" title="${_esc(item.erro)}">${_esc(item.erro)}</span>`
            : '';

        return `
        <tr>
            <td class="col-nome">${_esc(item.nome_colaborador || '—')}</td>
            <td class="col-fornec">${_esc(item.codfornecedor || '—')} / ${_esc(item.lojafornec || '—')}</td>
            <td>${badgeHtml}</td>
            <td>${pedidoHtml}</td>
            <td>${obsHtml}</td>
        </tr>`;
    }).join('');
}

function badgeStatus(status) {
    const labels = {
        pendente:     'Pendente',
        processando:  'Processando',
        sucesso:      '✓ Sucesso',
        falha:        '✕ Falha',
    };
    return `<span class="pedcom-badge ${_esc(status)}">${labels[status] ?? status}</span>`;
}

function renderBannerFinal(status, lote) {
    const banner = document.getElementById('status-lote-banner');
    banner.className  = `pedcom-status-lote ${status}`;
    banner.style.display = 'flex';

    const textos = {
        concluido:            `Lote concluído com sucesso — ${lote.sucesso} pedido(s) criado(s) no Protheus.`,
        concluido_com_falhas: `Lote finalizado com ${lote.falha} falha(s) — ${lote.sucesso} pedido(s) criado(s) com sucesso.`,
    };
    document.getElementById('status-lote-texto').textContent = textos[status] ?? 'Processamento finalizado.';
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _esc(str) {
    return String(str ?? '')
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;');
}
