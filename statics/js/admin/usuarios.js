document.addEventListener('DOMContentLoaded', function() {
    var formCriar        = document.getElementById('form-criar-usuario');
    var listaUsuarios    = document.getElementById('lista-usuarios');
    var mensagem         = document.getElementById('mensagem');
    var novoIsAdmin      = document.getElementById('novo-is-admin');
    var novoIsGerente    = document.getElementById('novo-is-gerente');
    var novoQueryToggle  = document.getElementById('novo-pode-ver-query');
    var novoSetorEl      = document.getElementById('novo-setor-id');
    var novoPermissoes   = document.getElementById('novo-usuario-permissoes');
    var catalogo         = JSON.parse(document.getElementById('admin-relatorios-catalogo').textContent || '[]');
    var mensagemTimeout  = null;
    var setoresCache     = [];

    function carregarSetores() {
        return fetch('/api/admin/setores')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                setoresCache = d.setores || [];
                var opts = '<option value="">— Sem setor —</option>';
                setoresCache.forEach(function(s) {
                    if (s.ativo) opts += '<option value="' + s.id + '">' + escapeHtml(s.nome) + '</option>';
                });
                novoSetorEl.innerHTML = opts;
            })
            .catch(function() {});
    }

    function montarSetorSelectHtml(selecionado, prefixo) {
        var opts = '<option value="">— Sem setor —</option>';
        setoresCache.forEach(function(s) {
            if (!s.ativo) return;
            var sel = String(s.id) === String(selecionado) ? 'selected' : '';
            opts += '<option value="' + s.id + '" ' + sel + '>' + escapeHtml(s.nome) + '</option>';
        });
        return '<select class="js-setor-id" id="' + (prefixo || 'setor') + '">' + opts + '</select>';
    }

    /* ── helpers ──────────────────────────────────────────────────────────── */
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

    function chevron() {
        return '<svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">' +
               '<path d="M2 4l4 4 4-4" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/>' +
               '</svg>';
    }

    /* ── permissões ───────────────────────────────────────────────────────── */
    function montarPermissoesHtml(nomeCampo, selecionadas, desabilitado) {
        if (!catalogo.length) {
            return '<p class="admin-vazio">Nenhum relatório cadastrado.</p>';
        }
        return catalogo.map(function(relatorio) {
            var checked   = selecionadas.indexOf(relatorio.chave) >= 0 ? 'checked' : '';
            var disabled  = desabilitado ? 'disabled' : '';
            return [
                '<label class="admin-permission-chip">',
                '<input type="checkbox" name="' + nomeCampo + '" value="' + escapeHtml(relatorio.chave) + '" ' + checked + ' ' + disabled + '>',
                '<span>',
                '<strong>' + escapeHtml(relatorio.titulo) + '</strong>',
                '<span>' + escapeHtml(relatorio.modulo_titulo) + '</span>',
                '</span>',
                '</label>'
            ].join('');
        }).join('');
    }

    function coletarPermissoes(raiz, nomeCampo) {
        return Array.from(raiz.querySelectorAll('input[name="' + nomeCampo + '"]:checked')).map(function(i) {
            return i.value;
        });
    }

    /* ── email badge ──────────────────────────────────────────────────────── */
    function emailStatusLabel(ea) {
        if (!ea || ea.status === 'nunca_enviado') return 'Nunca enviado';
        if (ea.status === 'enviado') return 'Enviado';
        if (ea.status === 'falha')   return 'Falhou';
        return ea.status;
    }

    function emailStatusBadge(ea) {
        var label = emailStatusLabel(ea);
        var cls   = 'admin-badge';
        if (ea && ea.status === 'enviado') cls += ' is-ok';
        if (ea && ea.status === 'falha')   cls += ' is-warn';
        return '<span class="' + cls + '">E-mail: ' + escapeHtml(label) + '</span>';
    }

    /* ── renderizar linha de usuário ─────────────────────────────────────── */
    function renderizarLinhaUsuario(u) {
            /* badges de status */
            var badgeAtivo = u.ativo
                ? '<span class="admin-badge is-ok">Ativo</span>'
                : '<span class="admin-badge is-danger">Desativado</span>';
            var badgeTroca = u.deve_trocar_senha
                ? '<span class="admin-badge is-warn">Troca pendente</span>'
                : '';
            var badgePerfil = u.is_admin
                ? '<span class="admin-badge is-strong">Superadmin</span>'
                : '<span class="admin-badge">Padrão</span>';

            return [
                /* ── linha recolhida ── */
                '<details class="admin-user-row" data-user-id="' + u.id + '">',
                '<summary class="admin-user-summary">',

                /* col: identidade */
                '<div>',
                '<strong class="aur-name">' + escapeHtml(u.nome) + '</strong>',
                '<span class="aur-login">' + escapeHtml(u.usuario) + '</span>',
                '</div>',

                /* col: perfil */
                '<div>' + badgePerfil + '</div>',

                /* col: status */
                '<div class="admin-badges">',
                badgeAtivo, badgeTroca, emailStatusBadge(u.email_acesso),
                '</div>',

                /* col: último login */
                '<div><span class="aur-login">' + escapeHtml(u.ultimo_login_em || 'Nunca') + '</span></div>',

                /* col: botão expand */
                '<div style="display:flex;justify-content:flex-end">',
                '<span class="aur-expand-btn">' + chevron() + 'Editar</span>',
                '</div>',

                '</summary>',

                /* ── painel de edição ── */
                '<div class="aur-edit-panel">',

                /* seção 1: perfil */
                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Perfil de acesso</span>',
                '<div style="margin-bottom:10px">',
                '<label class="admin-field" style="max-width:240px"><span>Setor</span>',
                montarSetorSelectHtml(u.setor_id, 'setor-' + u.id),
                '</label>',
                '</div>',
                '<div class="aur-toggles">',
                '<label class="admin-toggle">',
                '<input type="checkbox" class="js-is-admin" ' + (u.is_admin ? 'checked' : '') + '>',
                '<span>Administrador total do sistema</span>',
                '</label>',
                '<label class="admin-toggle">',
                '<input type="checkbox" class="js-is-gerente" ' + (u.is_gerente ? 'checked' : '') + '>',
                '<span>Gerente do setor</span>',
                '</label>',
                '<label class="admin-toggle">',
                '<input type="checkbox" class="js-pode-ver-query" ' + (u.pode_ver_query ? 'checked' : '') + '>',
                '<span>Pode ver a query SQL dos relatórios</span>',
                '</label>',
                '</div>',
                '</div>',

                /* seção 2: relatórios */
                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Relatórios permitidos</span>',
                '<div class="admin-permissions-grid js-permissoes">',
                montarPermissoesHtml('permissoes-' + u.id, u.permissoes, u.is_admin),
                '</div>',
                '</div>',

                /* seção 3: informações */
                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Informações da conta</span>',
                '<div class="aur-meta-grid">',
                metaItem('E-mail', u.email || '--'),
                metaItem('Setor', u.setor_nome || '--'),
                metaItem('Criado em', u.criado_em || '--'),
                metaItem('Último login', u.ultimo_login_em || 'Nunca'),
                metaItem('Status e-mail', emailStatusLabel(u.email_acesso)),
                metaItem('Último erro de e-mail', (u.email_acesso && u.email_acesso.ultimo_erro) || '--'),
                '</div>',
                '</div>',

                /* seção 4: ações */
                '<div class="aur-edit-actions">',
                '<button type="button" class="admin-btn admin-btn-primario js-salvar">Salvar alterações</button>',
                '<button type="button" class="admin-btn admin-btn-secundario js-reset-senha">Resetar senha</button>',
                '<button type="button" class="admin-btn admin-btn-secundario js-reenviar-email">Reenviar e-mail</button>',
                '<button type="button" class="admin-btn ' + (u.ativo ? 'admin-btn-danger js-status' : 'admin-btn-secundario js-status') + '">' + (u.ativo ? 'Desativar usuário' : 'Ativar usuário') + '</button>',
                '</div>',

                '</div>', /* /aur-edit-panel */
                '</details>'
            ].join('');
    }

    /* ── renderizar lista agrupada por setor ──────────────────────────────── */
    function renderizarUsuarios(usuarios) {
        if (!usuarios.length) {
            listaUsuarios.innerHTML = '<p class="admin-vazio">Nenhum usuário cadastrado.</p>';
            return;
        }

        /* agrupar por setor, "Sem setor" sempre por último */
        var grupos = {};
        var ordemGrupos = [];
        usuarios.forEach(function(u) {
            var chave = u.setor_nome || '__sem_setor__';
            if (!grupos[chave]) {
                grupos[chave] = [];
                ordemGrupos.push(chave);
            }
            grupos[chave].push(u);
        });

        /* mover "Sem setor" para o final */
        var idxSemSetor = ordemGrupos.indexOf('__sem_setor__');
        if (idxSemSetor > -1) {
            ordemGrupos.splice(idxSemSetor, 1);
            ordemGrupos.push('__sem_setor__');
        }

        var html = '';
        ordemGrupos.forEach(function(chave) {
            var label = chave === '__sem_setor__' ? 'Sem setor' : chave;
            var membros = grupos[chave];
            var totalAtivos = membros.filter(function(u) { return u.ativo; }).length;

            html += [
                '<div class="admin-setor-grupo">',
                '<div class="admin-setor-header">',
                '<span class="admin-setor-nome">' + escapeHtml(label) + '</span>',
                '<span class="admin-setor-contagem">' + membros.length + ' usuário' + (membros.length !== 1 ? 's' : '') +
                    ' &nbsp;·&nbsp; ' + totalAtivos + ' ativo' + (totalAtivos !== 1 ? 's' : '') + '</span>',
                '</div>',
                '<div class="admin-setor-usuarios">',
                membros.map(renderizarLinhaUsuario).join(''),
                '</div>',
                '</div>'
            ].join('');
        });

        listaUsuarios.innerHTML = html;
    }

    function metaItem(label, valor) {
        return [
            '<div class="aur-meta-item">',
            '<strong>' + escapeHtml(label) + '</strong>',
            '<span>' + escapeHtml(valor) + '</span>',
            '</div>'
        ].join('');
    }

    /* ── bloquear permissões quando admin marcado ─────────────────────────── */
    function sincronizarPermissoes(card, isAdmin) {
        card.querySelectorAll('.js-permissoes input[type="checkbox"]').forEach(function(input) {
            input.disabled = isAdmin;
        });
    }

    /* ── formulário de criação: sincronizar estado ────────────────────────── */
    function alternarPermissoesCriacao() {
        var desabilitar = novoIsAdmin.checked;
        novoPermissoes.querySelectorAll('input[type="checkbox"]').forEach(function(input) {
            input.disabled = desabilitar;
        });
    }

    function renderizarCatalogoCriacao() {
        novoPermissoes.innerHTML = montarPermissoesHtml('permissoes', catalogo.map(function(item) {
            return item.chave;
        }), false);
    }

    /* ── carregar dados ───────────────────────────────────────────────────── */
    function carregarDados() {
        mostrarMensagem('Carregando usuários...', 'processando');
        return fetch('/api/admin/usuarios')
            .then(function(resp) {
                if (!verificarAuth(resp)) return null;
                return resp.json().then(function(data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao carregar usuários.');
                    return data;
                });
            })
            .then(function(data) {
                renderizarUsuarios(data.usuarios || []);
                mostrarMensagem('Usuários carregados.', 'sucesso');
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao carregar dados.', 'erro');
            });
    }

    /* ── criar usuário ────────────────────────────────────────────────────── */
    formCriar.addEventListener('submit', function(event) {
        event.preventDefault();
        var email = formCriar.email.value.trim().toLowerCase();
        if (!/@(hbraviacao|hbrenergy)\.com\.br$/.test(email)) {
            mostrarMensagem('Use um e-mail corporativo @hbraviacao.com.br ou @hbrenergy.com.br.', 'erro');
            return;
        }

        var payload = {
            email:          email,
            is_admin:       novoIsAdmin.checked,
            is_gerente:     novoIsGerente.checked,
            pode_ver_query: novoQueryToggle.checked,
            setor_id:       novoSetorEl.value ? parseInt(novoSetorEl.value, 10) : null,
            permissoes:     coletarPermissoes(formCriar, 'permissoes')
        };

        mostrarMensagem('Criando usuário...', 'processando');
        fetch('/api/admin/usuarios', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
        .then(function(resp) {
            if (!verificarAuth(resp)) return null;
            return resp.json().then(function(data) {
                if (!resp.ok) throw new Error(data.erro || 'Falha ao criar usuário.');
                return data;
            });
        })
        .then(function(data) {
            formCriar.reset();
            renderizarCatalogoCriacao();
            alternarPermissoesCriacao();
            mostrarMensagem((data && data.mensagem) || 'Usuário criado com sucesso.', 'sucesso');
            return carregarDados();
        })
        .catch(function(err) {
            mostrarMensagem(err.message || 'Falha ao criar usuário.', 'erro');
        });
    });

    /* ── eventos da lista ─────────────────────────────────────────────────── */
    listaUsuarios.addEventListener('change', function(event) {
        if (!event.target.classList.contains('js-is-admin')) return;
        var card = event.target.closest('.admin-user-row');
        if (card) sincronizarPermissoes(card, event.target.checked);
    });

    listaUsuarios.addEventListener('click', function(event) {
        var card = event.target.closest('.admin-user-row');
        if (!card) return;
        var userId = card.getAttribute('data-user-id');

        /* salvar */
        if (event.target.classList.contains('js-salvar')) {
            var setorEl = card.querySelector('.js-setor-id');
            var payload = {
                is_admin:       card.querySelector('.js-is-admin').checked,
                is_gerente:     card.querySelector('.js-is-gerente').checked,
                pode_ver_query: card.querySelector('.js-pode-ver-query').checked,
                setor_id:       setorEl && setorEl.value ? parseInt(setorEl.value, 10) : null,
                permissoes:     coletarPermissoes(card, 'permissoes-' + userId)
            };
            mostrarMensagem('Salvando configuração...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/configuracao', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
            .then(function(resp) {
                if (!verificarAuth(resp)) return null;
                return resp.json().then(function(data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao salvar.');
                    return data;
                });
            })
            .then(function() {
                mostrarMensagem('Configuração salva com sucesso.', 'sucesso');
                return carregarDados();
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao salvar configuração.', 'erro');
            });
        }

        /* resetar senha */
        if (event.target.classList.contains('js-reset-senha')) {
            mostrarMensagem('Resetando senha...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/reset-senha', { method: 'POST' })
            .then(function(resp) {
                if (!verificarAuth(resp)) return null;
                return resp.json().then(function(data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao resetar senha.');
                    return data;
                });
            })
            .then(function() {
                mostrarMensagem('Senha resetada para o login do usuário.', 'sucesso');
                return carregarDados();
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao resetar senha.', 'erro');
            });
        }

        /* reenviar e-mail */
        if (event.target.classList.contains('js-reenviar-email')) {
            mostrarMensagem('Reenviando e-mail de acesso...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/reenviar-email', { method: 'POST' })
            .then(function(resp) {
                if (!verificarAuth(resp)) return null;
                return resp.json().then(function(data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao reenviar e-mail.');
                    return data;
                });
            })
            .then(function(data) {
                mostrarMensagem(data.mensagem || 'Reenvio concluído.', 'sucesso');
                return carregarDados();
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao reenviar e-mail.', 'erro');
            });
        }

        /* ativar / desativar */
        if (event.target.classList.contains('js-status')) {
            var ativar = event.target.textContent.trim().toLowerCase().startsWith('ativar');
            mostrarMensagem((ativar ? 'Ativando' : 'Desativando') + ' usuário...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ativo: ativar })
            })
            .then(function(resp) {
                if (!verificarAuth(resp)) return null;
                return resp.json().then(function(data) {
                    if (!resp.ok) throw new Error(data.erro || 'Falha ao atualizar status.');
                    return data;
                });
            })
            .then(function(data) {
                mostrarMensagem(data.mensagem || 'Status atualizado.', 'sucesso');
                if (data.redirect) { window.location.href = data.redirect; return null; }
                return carregarDados();
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao atualizar status.', 'erro');
            });
        }
    });

    /* ── init ─────────────────────────────────────────────────────────────── */
    novoIsAdmin.addEventListener('change', alternarPermissoesCriacao);
    renderizarCatalogoCriacao();
    alternarPermissoesCriacao();
    carregarSetores().then(function() { carregarDados(); });
});
