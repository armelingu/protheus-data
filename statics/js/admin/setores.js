document.addEventListener('DOMContentLoaded', function() {
    var formCriar      = document.getElementById('form-criar-setor');
    var listaSetores   = document.getElementById('lista-setores');
    var paginacaoEl    = document.getElementById('paginacao-setores');
    var contadorEl     = document.getElementById('contador-setores');
    var mensagem       = document.getElementById('mensagem');
    var novoPerms      = document.getElementById('novo-setor-permissoes');
    var catalogo       = JSON.parse(document.getElementById('admin-relatorios-catalogo').textContent || '[]');
    var mensagemTimeout = null;
    var setoresCache    = [];
    var paginaAtual     = 1;
    var POR_PAGINA      = 10;

    function verificarAuth(resp) {
        if (resp.status === 401) {
            window.location.href = '/login';
            return false;
        }
        return true;
    }

    function mostrarMensagem(texto, tipo) {
        mensagem.textContent = texto;
        mensagem.className = 'mensagem ' + (tipo || 'sucesso') + ' visivel';
        window.clearTimeout(mensagemTimeout);
        if (tipo !== 'processando') {
            mensagemTimeout = window.setTimeout(function() { mensagem.className = 'mensagem'; }, 3200);
        }
    }

    function escapeHtml(t) {
        return String(t || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    function chevron() {
        return '<svg width="12" height="12" viewBox="0 0 12 12" fill="none">' +
               '<path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>';
    }

    function montarPermissoesHtml(nomeCampo, selecionadas) {
        return catalogo.map(function(r) {
            var checked = selecionadas.indexOf(r.chave) >= 0 ? 'checked' : '';
            return [
                '<label class="admin-permission-chip">',
                '<input type="checkbox" name="' + nomeCampo + '" value="' + escapeHtml(r.chave) + '" ' + checked + '>',
                '<span><strong>' + escapeHtml(r.titulo) + '</strong>',
                '<span>' + escapeHtml(r.modulo_titulo) + '</span></span>',
                '</label>'
            ].join('');
        }).join('');
    }

    function coletarPermissoes(raiz, nome) {
        return Array.from(raiz.querySelectorAll('input[name="' + nome + '"]:checked')).map(function(i) { return i.value; });
    }

    function renderizarSetores(setores) {
        if (!setores.length) {
            listaSetores.innerHTML = '<p class="admin-vazio">Nenhum setor cadastrado.</p>';
            return;
        }
        listaSetores.innerHTML = setores.map(function(s) {
            var modulos = s.permissoes.length
                ? s.permissoes.map(function(p) {
                    var titulo = (catalogo.find(function(r) { return r.chave === p; }) || {}).titulo || p.split(':')[1] || p;
                    return '<span class="admin-badge is-strong">' + escapeHtml(titulo) + '</span>';
                }).join(' ')
                : '<span class="admin-badge">Nenhum módulo liberado</span>';
            var gerentes = s.gerentes.length
                ? s.gerentes.map(function(g) { return escapeHtml(g.nome); }).join(', ')
                : '--';
            var podeDeletar = s.total_usuarios === 0;
            var btnDeletar = podeDeletar
                ? '<button type="button" class="admin-btn admin-btn-danger js-excluir-setor" style="margin-left:auto">Excluir setor</button>'
                : '<span style="font-size:.78rem;color:#aaa;margin-left:auto">' + s.total_usuarios + ' usuário(s) — não pode excluir</span>';

            return [
                '<details class="admin-user-row" data-setor-id="' + s.id + '">',
                '<summary class="admin-user-summary" style="grid-template-columns: minmax(160px,1.2fr) minmax(0,1.5fr) 80px 80px 90px;">',
                '<div>',
                '<strong class="aur-name">' + escapeHtml(s.nome) + '</strong>',
                s.descricao ? '<span class="aur-login">' + escapeHtml(s.descricao) + '</span>' : '',
                '</div>',
                '<div class="admin-badges">' + modulos + '</div>',
                '<div><span class="aur-login">' + escapeHtml(gerentes) + '</span></div>',
                '<div>',
                s.total_usuarios > 0
                    ? '<span class="admin-badge is-ok">' + s.total_usuarios + ' usuário(s)</span>'
                    : '<span class="admin-badge">Vazio</span>',
                '</div>',
                '<div style="display:flex;justify-content:flex-end">',
                '<span class="aur-expand-btn">' + chevron() + 'Editar</span>',
                '</div>',
                '</summary>',

                '<div class="aur-edit-panel">',

                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Dados do setor</span>',
                '<div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;">',
                '<label class="admin-field"><span>Nome</span>',
                '<input type="text" class="js-nome" value="' + escapeHtml(s.nome) + '"></label>',
                '<label class="admin-field"><span>Descrição</span>',
                '<input type="text" class="js-descricao" value="' + escapeHtml(s.descricao || '') + '"></label>',
                '</div>',
                '</div>',

                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Módulos liberados para este setor</span>',
                '<div class="admin-permissions-grid js-setor-perms">',
                montarPermissoesHtml('sp-' + s.id, s.permissoes),
                '</div>',
                '</div>',

                '<div class="aur-edit-actions" style="display:flex;gap:10px;align-items:center;flex-wrap:wrap">',
                '<button type="button" class="admin-btn admin-btn-primario js-salvar-setor">Salvar alterações</button>',
                btnDeletar,
                '</div>',

                '</div>',
                '</details>'
            ].join('');
        }).join('');
    }

    function renderizarPagina() {
        var total = setoresCache.length;
        var totalPaginas = Math.max(1, Math.ceil(total / POR_PAGINA) || 1);
        if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;
        if (paginaAtual < 1) paginaAtual = 1;
        var inicio = (paginaAtual - 1) * POR_PAGINA;
        renderizarSetores(setoresCache.slice(inicio, inicio + POR_PAGINA));
        renderizarPaginacaoAdmin(paginacaoEl, paginaAtual, total, POR_PAGINA, 'setores');
        if (contadorEl) contadorEl.textContent = total ? '(' + total + ')' : '';
    }

    function carregarDados() {
        mostrarMensagem('Carregando setores...', 'processando');
        return fetch('/api/admin/setores')
            .then(function(r) { if (!verificarAuth(r)) return null; return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
            .then(function(d) {
                if (!d) return;
                setoresCache = d.setores || [];
                renderizarPagina();
                mostrarMensagem('Setores carregados.', 'sucesso');
            })
            .catch(function(e) { mostrarMensagem(e.message || 'Falha ao carregar setores.', 'erro'); });
    }

    novoPerms.innerHTML = montarPermissoesHtml('permissoes', []);

    formCriar.addEventListener('submit', function(e) {
        e.preventDefault();
        var payload = {
            nome: formCriar.nome.value.trim(),
            descricao: formCriar.descricao.value.trim(),
            permissoes: coletarPermissoes(formCriar, 'permissoes')
        };
        mostrarMensagem('Criando setor...', 'processando');
        fetch('/api/admin/setores', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function(r) { if (!verificarAuth(r)) return null; return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
        .then(function(d) {
            formCriar.reset();
            novoPerms.innerHTML = montarPermissoesHtml('permissoes', []);
            mostrarMensagem(d.mensagem || 'Setor criado.', 'sucesso');
            var painelNovo = document.getElementById('painel-novo-setor');
            if (painelNovo) painelNovo.open = false;
            paginaAtual = 1;
            return carregarDados();
        })
        .catch(function(e) { mostrarMensagem(e.message || 'Falha ao criar setor.', 'erro'); });
    });

    listaSetores.addEventListener('click', function(e) {
        var card = e.target.closest('.admin-user-row');
        if (!card) return;
        var setorId = card.getAttribute('data-setor-id');

        if (e.target.classList.contains('js-salvar-setor')) {
            var nome = card.querySelector('.js-nome').value.trim();
            if (!nome) { mostrarMensagem('O nome do setor não pode ser vazio.', 'erro'); return; }
            var payload = {
                nome: nome,
                descricao: card.querySelector('.js-descricao').value.trim(),
                permissoes: coletarPermissoes(card, 'sp-' + setorId),
                ativo: true
            };
            mostrarMensagem('Salvando setor...', 'processando');
            fetch('/api/admin/setores/' + setorId + '/configuracao', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(r) { if (!verificarAuth(r)) return null; return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
            .then(function(d) { mostrarMensagem(d.mensagem || 'Setor salvo.', 'sucesso'); return carregarDados(); })
            .catch(function(e) { mostrarMensagem(e.message || 'Falha ao salvar setor.', 'erro'); });
        }

        if (e.target.classList.contains('js-excluir-setor')) {
            var nomeSetor = card.querySelector('.js-nome') ? card.querySelector('.js-nome').value : setorId;
            if (!window.confirm('Excluir o setor "' + nomeSetor + '"? Esta ação não pode ser desfeita.')) return;
            mostrarMensagem('Excluindo setor...', 'processando');
            fetch('/api/admin/setores/' + setorId, { method: 'DELETE' })
            .then(function(r) { if (!verificarAuth(r)) return null; return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
            .then(function(d) { mostrarMensagem(d.mensagem || 'Setor excluído.', 'sucesso'); return carregarDados(); })
            .catch(function(e) { mostrarMensagem(e.message || 'Falha ao excluir setor.', 'erro'); });
        }
    });

    persistirPaineisAdmin('admin.setores.panel.');
    if (paginacaoEl) {
        paginacaoEl.addEventListener('click', function(event) {
            var btn = event.target.closest('[data-pag]');
            if (!btn || btn.disabled) return;
            paginaAtual = lerPaginaPaginacao(btn, paginaAtual);
            renderizarPagina();
            var listaPainel = document.getElementById('painel-setores-lista');
            if (listaPainel) listaPainel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }
    carregarDados();
});
