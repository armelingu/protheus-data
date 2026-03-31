document.addEventListener('DOMContentLoaded', function() {
    var listaEl     = document.getElementById('lista-usuarios-setor');
    var modulosEl   = document.getElementById('modulos-setor');
    var mensagem    = document.getElementById('mensagem');
    var catalogo    = JSON.parse(document.getElementById('admin-relatorios-catalogo').textContent || '[]');
    var mensagemTimeout = null;

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

    function montarPermissoesHtml(userId, permissoesSetor, permissoesUsuario) {
        return catalogo
            .filter(function(r) { return permissoesSetor.indexOf(r.chave) >= 0; })
            .map(function(r) {
                var checked = permissoesUsuario.indexOf(r.chave) >= 0 ? 'checked' : '';
                return [
                    '<label class="admin-permission-chip">',
                    '<input type="checkbox" name="perm-' + userId + '" value="' + escapeHtml(r.chave) + '" ' + checked + '>',
                    '<span><strong>' + escapeHtml(r.titulo) + '</strong>',
                    '<span>' + escapeHtml(r.modulo_titulo) + '</span></span>',
                    '</label>'
                ].join('');
            }).join('');
    }

    function coletarPermissoes(card, userId) {
        return Array.from(card.querySelectorAll('input[name="perm-' + userId + '"]:checked'))
            .map(function(i) { return i.value; });
    }

    function renderizarUsuarios(usuarios, permissoesSetor) {
        modulosEl.innerHTML = permissoesSetor.length
            ? permissoesSetor.map(function(p) {
                var titulo = (catalogo.find(function(r) { return r.chave === p; }) || {}).titulo || p;
                return '<span class="admin-badge is-strong">' + escapeHtml(titulo) + '</span>';
            }).join(' ')
            : '<span class="admin-badge">Nenhum módulo liberado pelo administrador.</span>';

        if (!usuarios.length) {
            listaEl.innerHTML = '<p class="admin-vazio">Nenhum usuário neste setor.</p>';
            return;
        }

        listaEl.innerHTML = usuarios.map(function(u) {
            var statusBadge = u.ativo
                ? '<span class="admin-badge is-ok">Ativo</span>'
                : '<span class="admin-badge is-danger">Inativo</span>';

            var permsAtuais = u.permissoes.length
                ? u.permissoes.map(function(p) {
                    var titulo = (catalogo.find(function(r) { return r.chave === p; }) || {}).titulo || p;
                    return '<span class="admin-badge is-strong">' + escapeHtml(titulo) + '</span>';
                }).join(' ')
                : '<span class="admin-badge">Sem acesso</span>';

            return [
                '<details class="admin-user-row" data-usuario-id="' + u.id + '">',
                '<summary class="admin-user-summary" style="grid-template-columns: minmax(160px,1.5fr) 1fr 120px;">',
                '<div>',
                '<strong class="aur-name">' + escapeHtml(u.nome) + '</strong>',
                '<span class="aur-login">' + escapeHtml(u.usuario) + '</span>',
                '</div>',
                '<div class="admin-badges">' + permsAtuais + '</div>',
                '<div style="display:flex;align-items:center;gap:8px;justify-content:flex-end">',
                statusBadge,
                '<span class="aur-expand-btn">' + chevron() + 'Editar</span>',
                '</div>',
                '</summary>',

                '<div class="aur-edit-panel">',
                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Acesso a relatórios (dentro do escopo do setor)</span>',
                '<div class="admin-permissions-grid">',
                montarPermissoesHtml(u.id, permissoesSetor, u.permissoes),
                '</div>',
                '</div>',
                '<div class="aur-edit-actions">',
                '<button type="button" class="admin-btn admin-btn-primario js-salvar-usuario">Salvar permissões</button>',
                '</div>',
                '</div>',
                '</details>'
            ].join('');
        }).join('');
    }

    function carregarDados() {
        mostrarMensagem('Carregando usuários do setor...', 'processando');
        return fetch('/api/gerente/usuarios')
            .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
            .then(function(d) {
                var ps = (d.usuarios && d.usuarios[0]) ? d.usuarios[0].permissoes_setor : [];
                renderizarUsuarios(d.usuarios || [], ps);
                mostrarMensagem('Dados carregados.', 'sucesso');
            })
            .catch(function(e) { mostrarMensagem(e.message || 'Falha ao carregar dados.', 'erro'); });
    }

    listaEl.addEventListener('click', function(e) {
        if (!e.target.classList.contains('js-salvar-usuario')) return;
        var card = e.target.closest('.admin-user-row');
        if (!card) return;
        var userId = card.getAttribute('data-usuario-id');
        var payload = { permissoes: coletarPermissoes(card, userId) };
        mostrarMensagem('Salvando...', 'processando');
        fetch('/api/gerente/usuarios/' + userId + '/configuracao', {
            method: 'POST', headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
        .then(function(d) { mostrarMensagem(d.mensagem || 'Permissões salvas.', 'sucesso'); return carregarDados(); })
        .catch(function(e) { mostrarMensagem(e.message || 'Falha ao salvar.', 'erro'); });
    });

    carregarDados();
});
