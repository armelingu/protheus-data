document.addEventListener('DOMContentLoaded', function() {
    var logsAuditoria = document.getElementById('logs-auditoria');
    var logsAcesso = document.getElementById('logs-acesso');
    var mensagem = document.getElementById('mensagem');
    var mensagemTimeout = null;

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

    function renderizarLogs(container, itens, tituloFn, detalheFn) {
        if (!itens.length) {
            container.innerHTML = '<p class="admin-vazio">Nenhum registro encontrado.</p>';
            return;
        }

        container.innerHTML = itens.map(function(item) {
            return [
                '<article class="admin-log-row">',
                '<div>',
                '<strong class="admin-log-title">' + escapeHtml(tituloFn(item)) + '</strong>',
                '<p class="admin-log-meta">' + escapeHtml(detalheFn(item)) + '</p>',
                '</div>',
                '<div class="admin-log-meta">' + escapeHtml(item.ip || '--') + '</div>',
                '<time class="admin-log-time">' + escapeHtml(item.data_hora || '--') + '</time>',
                '</article>'
            ].join('');
        }).join('');
    }

    function carregarDados() {
        mostrarMensagem('Atualizando auditoria...', 'processando');
        fetch('/api/admin/logs')
            .then(function(resp) {
                return resp.json().then(function(data) {
                    if (!resp.ok) {
                        throw new Error(data.erro || 'Falha ao carregar auditoria.');
                    }
                    return data;
                });
            })
            .then(function(dados) {
                renderizarLogs(logsAuditoria, dados.auditoria || [], function(item) {
                    return item.acao + ' · ' + item.usuario_afetado_login;
                }, function(item) {
                    return (item.admin_usuario_nome || 'Sistema') + ' · ' + (item.detalhe || 'Sem detalhe');
                });
                renderizarLogs(logsAcesso, dados.logs_acesso || [], function(item) {
                    return item.acao + ' · ' + item.usuario_nome;
                }, function(item) {
                    return 'Evento registrado no ambiente autenticado';
                });
                mostrarMensagem('Auditoria carregada.', 'sucesso');
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao carregar auditoria.', 'erro');
            });
    }

    carregarDados();
});
