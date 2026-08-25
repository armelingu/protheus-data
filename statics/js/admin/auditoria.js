document.addEventListener('DOMContentLoaded', function () {
    /* ── refs ─────────────────────────────────────────────────────────────── */
    var logsAuditoria   = document.getElementById('logs-auditoria');
    var logsAcesso      = document.getElementById('logs-acesso');
    var pagAuditoria    = document.getElementById('paginacao-auditoria');
    var pagAcesso       = document.getElementById('paginacao-acesso');
    var contAuditoria   = document.getElementById('contador-auditoria');
    var contAcesso      = document.getElementById('contador-acesso');
    var filtrosBadge    = document.getElementById('filtros-status');
    var mensagem        = document.getElementById('mensagem');
    var inputBusca      = document.getElementById('filtro-busca');
    var selectAcao      = document.getElementById('filtro-acao');
    var inputInicio     = document.getElementById('filtro-data-inicio');
    var inputFim        = document.getElementById('filtro-data-fim');
    var btnLimpar       = document.getElementById('btn-limpar-filtros');

    var mensagemTimeout = null;
    var buscaTimeout    = null;
    var paginaAtual     = 1;

    /* ── labels de ação ───────────────────────────────────────────────────── */
    var LABELS = {
        /* administração */
        'usuario_criado':                   { label: 'Usuário criado',              cat: 'criacao'   },
        'usuario_configuracao_atualizada':  { label: 'Perfil e permissões atualizados', cat: 'edicao' },
        'usuario_status_alterado':          { label: 'Status alterado',             cat: 'edicao'    },
        'usuario_reset_senha':              { label: 'Senha resetada',              cat: 'seguranca' },
        'usuario_desativado':               { label: 'Usuário desativado',          cat: 'edicao'    },
        'usuario_ativado':                  { label: 'Usuário ativado',             cat: 'criacao'   },
        'email_acesso_enviado':             { label: 'E-mail de acesso enviado',    cat: 'email'     },
        'email_acesso_falhou':              { label: 'Falha no envio de e-mail',    cat: 'erro'      },
        'email_acesso_reenviado':           { label: 'E-mail de acesso reenviado',  cat: 'email'     },
        'email_acesso_reenvio_falhou':      { label: 'Falha no reenvio de e-mail',  cat: 'erro'      },
        'troca_senha_primeiro_acesso':      { label: 'Senha definida (1º acesso)',  cat: 'seguranca' },
        'login_negado_usuario_inativo':     { label: 'Login negado — conta inativa', cat: 'aviso'   },
        'login_negado_senha_incorreta':     { label: 'Login negado — senha incorreta', cat: 'aviso' },
        'setor_criado':                     { label: 'Setor criado',                cat: 'criacao'   },
        'setor_excluido':                   { label: 'Setor excluído',              cat: 'remocao'   },
        'setor_atualizado':                 { label: 'Setor atualizado',            cat: 'edicao'    },
        'gerente_atualizou_permissoes':     { label: 'Permissões ajustadas',        cat: 'edicao'    },
        'aviso_melhoria_publicado':         { label: 'Aviso de melhoria publicado', cat: 'aviso'     },
        /* acesso */
        'login':                            { label: 'Login realizado',             cat: 'acesso'    },
        'login_primeiro_acesso':            { label: 'Login (primeiro acesso)',      cat: 'acesso'    },
        'logout':                           { label: 'Logout realizado',            cat: 'acesso'    },
        'download_csv':                     { label: 'Download CSV — Pedidos',      cat: 'download'  },
        'download_excel':                   { label: 'Download Excel — Pedidos',    cat: 'download'  },
        'download_estoque_csv':             { label: 'Download CSV — Estoque',      cat: 'download'  },
        'download_estoque_excel':           { label: 'Download Excel — Estoque',    cat: 'download'  },
        'download_historico_csv':           { label: 'Download CSV — Histórico',    cat: 'download'  },
        'download_historico_excel':         { label: 'Download Excel — Histórico',  cat: 'download'  },
        'sync_manual':                      { label: 'Sync manual — Pedidos',       cat: 'sync'      },
        'sync_manual_estoque':              { label: 'Sync manual — Estoque',       cat: 'sync'      },
        'sync_manual_historico':            { label: 'Sync manual — Histórico',     cat: 'sync'      },
    };

    var CAT_LABELS = {
        'criacao':   'Criação',
        'edicao':    'Edição',
        'remocao':   'Remoção',
        'seguranca': 'Segurança',
        'email':     'E-mail',
        'erro':      'Erro',
        'aviso':     'Aviso',
        'acesso':    'Acesso',
        'download':  'Download',
        'sync':      'Sync',
    };

    function infoAcao(acao) {
        return LABELS[acao] || { label: acao.replace(/_/g, ' '), cat: 'outro' };
    }

    /* ── helpers ──────────────────────────────────────────────────────────── */
    function verificarAuth(resp) {
        if (resp.status === 401) { window.location.href = '/login'; return false; }
        return true;
    }

    function mostrarMensagem(texto, tipo) {
        mensagem.textContent = texto;
        mensagem.className   = 'mensagem ' + (tipo || 'sucesso') + ' visivel';
        window.clearTimeout(mensagemTimeout);
        if (tipo !== 'processando') {
            mensagemTimeout = window.setTimeout(function () {
                mensagem.className = 'mensagem';
            }, 3200);
        }
    }

    function escapeHtml(texto) {
        return String(texto || '')
            .replace(/&/g, '&amp;').replace(/</g, '&lt;')
            .replace(/>/g, '&gt;').replace(/"/g, '&quot;')
            .replace(/'/g, '&#39;');
    }

    function badge(cat) {
        var label = CAT_LABELS[cat] || cat;
        return '<span class="audit-badge audit-badge--' + cat + '">' + label + '</span>';
    }

    /* ── renderização ─────────────────────────────────────────────────────── */
    function renderizarAuditoria(container, itens) {
        if (!itens.length) {
            container.innerHTML = '<p class="admin-vazio">Nenhum evento encontrado.</p>';
            return;
        }
        container.innerHTML = itens.map(function (item) {
            var info     = infoAcao(item.acao);
            var detalhe  = item.detalhe ? '<p class="admin-log-sub">' + escapeHtml(item.detalhe) + '</p>' : '';
            return [
                '<article class="admin-log-row audit-row-4col">',
                '<div class="audit-cell-evento">',
                badge(info.cat),
                '<strong class="admin-log-title">' + escapeHtml(info.label) + '</strong>',
                detalhe,
                '</div>',
                '<div class="audit-cell">' + escapeHtml(item.usuario_afetado_login || '—') + '</div>',
                '<div class="audit-cell audit-cell--muted">' + escapeHtml(item.admin_usuario_nome || 'Sistema') + '</div>',
                '<time class="admin-log-time">' + escapeHtml(item.data_hora || '--') + '</time>',
                '</article>',
            ].join('');
        }).join('');
    }

    function renderizarAcesso(container, itens) {
        if (!itens.length) {
            container.innerHTML = '<p class="admin-vazio">Nenhum evento encontrado.</p>';
            return;
        }
        container.innerHTML = itens.map(function (item) {
            var info = infoAcao(item.acao);
            return [
                '<article class="admin-log-row audit-row-4col">',
                '<div class="audit-cell-evento">',
                badge(info.cat),
                '<strong class="admin-log-title">' + escapeHtml(info.label) + '</strong>',
                '</div>',
                '<div class="audit-cell">' + escapeHtml(item.usuario_nome || '—') + '</div>',
                '<div class="audit-cell audit-cell--muted">' + escapeHtml(item.ip || '--') + '</div>',
                '<time class="admin-log-time">' + escapeHtml(item.data_hora || '--') + '</time>',
                '</article>',
            ].join('');
        }).join('');
    }

    /* ── paginação ────────────────────────────────────────────────────────── */
    function renderizarPaginacao(container, pagina, total, porPagina, tipo) {
        var totalPaginas = Math.ceil(total / porPagina) || 1;
        if (totalPaginas <= 1) { container.innerHTML = ''; return; }

        var html = '<div class="audit-pag-inner">';
        html += '<button class="audit-pag-btn" data-pag="prev" data-tipo="' + tipo + '"'
              + (pagina <= 1 ? ' disabled' : '') + '>&#8592; Anterior</button>';

        // janela de páginas
        var inicio = Math.max(1, pagina - 2);
        var fim    = Math.min(totalPaginas, pagina + 2);

        if (inicio > 1) {
            html += '<button class="audit-pag-num" data-pag="1" data-tipo="' + tipo + '">1</button>';
            if (inicio > 2) html += '<span class="audit-pag-reticencias">…</span>';
        }

        for (var p = inicio; p <= fim; p++) {
            var ativo = p === pagina ? ' ativo' : '';
            html += '<button class="audit-pag-num' + ativo + '" data-pag="' + p + '" data-tipo="' + tipo + '">' + p + '</button>';
        }

        if (fim < totalPaginas) {
            if (fim < totalPaginas - 1) html += '<span class="audit-pag-reticencias">…</span>';
            html += '<button class="audit-pag-num" data-pag="' + totalPaginas + '" data-tipo="' + tipo + '">' + totalPaginas + '</button>';
        }

        html += '<button class="audit-pag-btn" data-pag="next" data-tipo="' + tipo + '"'
              + (pagina >= totalPaginas ? ' disabled' : '') + '>Próxima &#8594;</button>';
        html += '</div>';

        var inicio_reg = (pagina - 1) * porPagina + 1;
        var fim_reg    = Math.min(pagina * porPagina, total);
        html += '<p class="audit-pag-info">Exibindo ' + inicio_reg + '–' + fim_reg + ' de ' + total + ' eventos</p>';

        container.innerHTML = html;

        container.querySelectorAll('[data-pag]').forEach(function (btn) {
            btn.addEventListener('click', function () {
                var tipo_ = btn.dataset.tipo;
                var val   = btn.dataset.pag;
                if (val === 'prev') paginaAtual--;
                else if (val === 'next') paginaAtual++;
                else paginaAtual = parseInt(val, 10);
                carregarDados();
                // scroll suave até o painel correspondente
                var alvo = tipo_ === 'auditoria' ? logsAuditoria : logsAcesso;
                alvo.closest('.admin-panel').scrollIntoView({ behavior: 'smooth', block: 'start' });
            });
        });
    }

    /* ── status de filtros ativos ─────────────────────────────────────────── */
    function atualizarStatusFiltros() {
        var ativos = [];
        if (inputBusca.value.trim())     ativos.push('Busca: "' + inputBusca.value.trim() + '"');
        if (selectAcao.value)            ativos.push('Ação: ' + (LABELS[selectAcao.value] ? LABELS[selectAcao.value].label : selectAcao.value));
        if (inputInicio.value)           ativos.push('De: ' + inputInicio.value);
        if (inputFim.value)              ativos.push('Até: ' + inputFim.value);

        if (ativos.length) {
            filtrosBadge.innerHTML = '<span class="audit-filtros-label">Filtros ativos:</span> '
                + ativos.map(function (f) {
                    return '<span class="audit-filtro-tag">' + escapeHtml(f) + '</span>';
                }).join('');
        } else {
            filtrosBadge.innerHTML = '';
        }
    }

    /* ── contador de resultados ───────────────────────────────────────────── */
    function atualizarContador(el, total) {
        el.textContent = total > 0 ? total + ' evento' + (total !== 1 ? 's' : '') : '';
    }

    /* ── carregar dados ───────────────────────────────────────────────────── */
    function carregarDados() {
        var params = new URLSearchParams();
        if (inputBusca.value.trim())  params.set('busca',        inputBusca.value.trim());
        if (selectAcao.value)         params.set('acao',         selectAcao.value);
        if (inputInicio.value)        params.set('data_inicio',  inputInicio.value);
        if (inputFim.value)           params.set('data_fim',     inputFim.value);
        params.set('pagina', String(paginaAtual));

        atualizarStatusFiltros();

        fetch('/api/admin/logs?' + params.toString())
            .then(function (resp) {
                if (!verificarAuth(resp)) return null;
                return resp.json().then(function (data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao carregar auditoria.');
                    return data;
                });
            })
            .then(function (dados) {
                if (!dados) return;
                renderizarAuditoria(logsAuditoria, dados.auditoria || []);
                renderizarAcesso(logsAcesso, dados.logs_acesso || []);

                atualizarContador(contAuditoria, dados.total_auditoria || 0);
                atualizarContador(contAcesso,    dados.total_acesso    || 0);

                renderizarPaginacao(pagAuditoria, dados.pagina, dados.total_auditoria, dados.por_pagina, 'auditoria');
                renderizarPaginacao(pagAcesso,    dados.pagina, dados.total_acesso,    dados.por_pagina, 'acesso');
            })
            .catch(function (err) {
                mostrarMensagem(err.message || 'Falha ao carregar auditoria.', 'erro');
            });
    }

    /* ── eventos de filtro ────────────────────────────────────────────────── */
    inputBusca.addEventListener('input', function () {
        window.clearTimeout(buscaTimeout);
        buscaTimeout = window.setTimeout(function () {
            paginaAtual = 1;
            carregarDados();
        }, 400);
    });

    [selectAcao, inputInicio, inputFim].forEach(function (el) {
        el.addEventListener('change', function () {
            paginaAtual = 1;
            carregarDados();
        });
    });

    btnLimpar.addEventListener('click', function () {
        inputBusca.value  = '';
        selectAcao.value  = '';
        inputInicio.value = '';
        inputFim.value    = '';
        paginaAtual = 1;
        carregarDados();
    });

    /* ── carga inicial ────────────────────────────────────────────────────── */
    persistirPaineisAdmin('admin.auditoria.panel.');
    carregarDados();
});
