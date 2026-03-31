document.addEventListener('DOMContentLoaded', function() {
    var logsAuditoria = document.getElementById('logs-auditoria');
    var logsAcesso    = document.getElementById('logs-acesso');
    var mensagem      = document.getElementById('mensagem');
    var mensagemTimeout = null;

    /* ── helpers ──────────────────────────────────────────────────────────── */
    function mostrarMensagem(texto, tipo) {
        mensagem.textContent = texto;
        mensagem.className = 'mensagem ' + (tipo || 'sucesso') + ' visivel';
        window.clearTimeout(mensagemTimeout);
        if (tipo !== 'processando') {
            mensagemTimeout = window.setTimeout(function() {
                mensagem.className = 'mensagem';
            }, 3200);
        }
    }

    function escapeHtml(texto) {
        return String(texto || '')
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    /* ── tradução de ações de administração ───────────────────────────────── */
    var LABELS_ADMIN = {
        'usuario_criado':                   'Usuário criado',
        'usuario_configuracao_atualizada':  'Permissões atualizadas',
        'usuario_status_alterado':          'Status alterado',
        'usuario_senha_resetada':           'Senha resetada',
        'email_reenviado':                  'E-mail reenviado',
        'usuario_desativado':               'Usuário desativado',
        'usuario_ativado':                  'Usuário ativado',
    };

    /* ── tradução de ações de acesso ──────────────────────────────────────── */
    var LABELS_ACESSO = {
        'login':                'Login realizado',
        'logout':               'Logout realizado',
        'download_csv':         'Download CSV',
        'download_excel':       'Download Excel',
        'sync_manual':          'Sincronização manual',
        'sync_manual_estoque':  'Sync manual — Estoque',
        'sync_manual_pedidos':  'Sync manual — Pedidos',
        'primeiro_acesso':      'Primeira troca de senha',
        'reset_senha':          'Senha redefinida',
    };

    function labelAdmin(acao) {
        return LABELS_ADMIN[acao] || acao.replace(/_/g, ' ');
    }

    function labelAcesso(acao) {
        return LABELS_ACESSO[acao] || acao.replace(/_/g, ' ');
    }

    /* ── renderizar logs ──────────────────────────────────────────────────── */
    function renderizarAuditoria(container, itens) {
        if (!itens.length) {
            container.innerHTML = '<p class="admin-vazio">Nenhum evento registrado.</p>';
            return;
        }

        container.innerHTML = itens.map(function(item) {
            var titulo  = labelAdmin(item.acao);
            var afetado = item.usuario_afetado_login
                ? 'Usuário: <strong>' + escapeHtml(item.usuario_afetado_login) + '</strong>'
                : '';
            var origem  = (item.admin_usuario_nome || 'Sistema') +
                          (item.detalhe ? ' — ' + item.detalhe : '');

            return [
                '<article class="admin-log-row">',
                '<div>',
                '<strong class="admin-log-title">' + escapeHtml(titulo) + '</strong>',
                afetado ? '<p class="admin-log-sub">' + afetado + '</p>' : '',
                '</div>',
                '<div class="admin-log-origin">' + escapeHtml(origem) + '</div>',
                '<time class="admin-log-time">' + escapeHtml(item.data_hora || '--') + '</time>',
                '</article>'
            ].join('');
        }).join('');
    }

    function renderizarAcesso(container, itens) {
        if (!itens.length) {
            container.innerHTML = '<p class="admin-vazio">Nenhum evento registrado.</p>';
            return;
        }

        container.innerHTML = itens.map(function(item) {
            var titulo  = labelAcesso(item.acao);
            var usuario = item.usuario_nome
                ? 'Usuário: <strong>' + escapeHtml(item.usuario_nome) + '</strong>'
                : '';

            return [
                '<article class="admin-log-row">',
                '<div>',
                '<strong class="admin-log-title">' + escapeHtml(titulo) + '</strong>',
                usuario ? '<p class="admin-log-sub">' + usuario + '</p>' : '',
                '</div>',
                '<div class="admin-log-origin">' + escapeHtml(item.ip || '--') + '</div>',
                '<time class="admin-log-time">' + escapeHtml(item.data_hora || '--') + '</time>',
                '</article>'
            ].join('');
        }).join('');
    }

    /* ── carregar dados ───────────────────────────────────────────────────── */
    function carregarDados() {
        mostrarMensagem('Carregando auditoria...', 'processando');
        fetch('/api/admin/logs')
            .then(function(resp) {
                return resp.json().then(function(data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao carregar auditoria.');
                    return data;
                });
            })
            .then(function(dados) {
                renderizarAuditoria(logsAuditoria, dados.auditoria || []);
                renderizarAcesso(logsAcesso, dados.logs_acesso || []);
                mostrarMensagem('Auditoria carregada.', 'sucesso');
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao carregar auditoria.', 'erro');
            });
    }

    carregarDados();
});
