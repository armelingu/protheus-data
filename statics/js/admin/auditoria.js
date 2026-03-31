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
        'usuario_configuracao_atualizada':  'Perfil e permissões atualizados',
        'usuario_status_alterado':          'Status alterado',
        'usuario_reset_senha':              'Senha resetada',
        'usuario_desativado':               'Usuário desativado',
        'usuario_ativado':                  'Usuário ativado',
        'email_acesso_enviado':             'E-mail de acesso enviado',
        'email_acesso_falhou':              'Falha no envio de e-mail',
        'email_acesso_reenviado':           'E-mail de acesso reenviado',
        'email_acesso_reenvio_falhou':      'Falha no reenvio de e-mail',
        'troca_senha_primeiro_acesso':      'Senha definida no primeiro acesso',
        'login_negado_usuario_inativo':     'Login negado — conta inativa',
        'login_negado_senha_incorreta':     'Login negado — senha incorreta',
        'setor_criado':                     'Setor criado',
        'setor_excluido':                   'Setor excluído',
        'setor_atualizado':                 'Setor atualizado',
        'gerente_atualizou_permissoes':     'Permissões ajustadas pelo gerente',
    };

    /* ── tradução de ações de acesso ──────────────────────────────────────── */
    var LABELS_ACESSO = {
        'login':                        'Login realizado',
        'login_primeiro_acesso':        'Login (primeiro acesso)',
        'logout':                       'Logout realizado',
        'download_csv':                 'Download CSV — Pedidos',
        'download_excel':               'Download Excel — Pedidos',
        'download_estoque_csv':         'Download CSV — Estoque',
        'download_estoque_excel':       'Download Excel — Estoque',
        'sync_manual':                  'Sync manual — Pedidos',
        'sync_manual_estoque':          'Sync manual — Estoque',
        'troca_senha_primeiro_acesso':  'Senha definida no primeiro acesso',
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
