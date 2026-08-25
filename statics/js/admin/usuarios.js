document.addEventListener('DOMContentLoaded', function() {
    var formCriar        = document.getElementById('form-criar-usuario');
    var listaUsuarios    = document.getElementById('lista-usuarios');
    var paginacaoEl      = document.getElementById('paginacao-usuarios');
    var contadorEl       = document.getElementById('contador-usuarios');
    var mensagem         = document.getElementById('mensagem');
    var novoIsAdmin      = document.getElementById('novo-is-admin');
    var novoIsGerente    = document.getElementById('novo-is-gerente');
    var novoQueryToggle  = document.getElementById('novo-pode-ver-query');
    var novoSetorEl      = document.getElementById('novo-setor-id');
    var novoPermissoes   = document.getElementById('novo-usuario-permissoes');
    var novoPermissoesAll = document.getElementById('novo-usuario-permissoes-all');
    var catalogo         = JSON.parse(document.getElementById('admin-relatorios-catalogo').textContent || '[]');
    var mensagemTimeout  = null;
    var setoresCache     = [];
    var usuariosCache    = [];
    var paginaAtual      = 1;
    var POR_PAGINA       = 10;

    function carregarSetores() {
        return fetch('/api/admin/setores')
            .then(function(r) { return r.json(); })
            .then(function(d) {
                setoresCache = d.setores || [];
                // DOM API — elimina risco de XSS via innerHTML com dados do servidor
                while (novoSetorEl.firstChild) novoSetorEl.removeChild(novoSetorEl.firstChild);
                var defaultOpt = document.createElement('option');
                defaultOpt.value = '';
                defaultOpt.textContent = '— Sem setor —';
                novoSetorEl.appendChild(defaultOpt);
                setoresCache.forEach(function(s) {
                    if (!s.ativo) return;
                    var opt = document.createElement('option');
                    opt.value = String(parseInt(s.id, 10));
                    opt.textContent = s.nome;
                    novoSetorEl.appendChild(opt);
                });
                // Aviso e pré-seleção de permissões quando setor for selecionado
                novoSetorEl.addEventListener('change', function() {
                    verificarAvisoSetor(novoSetorEl, 'aviso-setor-novo');
                    aplicarPermissoesSetorNovoCadastro();
                });
            })
            .catch(function() {});
    }

    function verificarAvisoSetor(selectEl, avisoId) {
        var avisoEl = document.getElementById(avisoId);
        if (!avisoEl) return;
        var setor = setoresCache.find(function(s) {
            return String(parseInt(s.id, 10)) === selectEl.value;
        });
        if (setor && (!setor.permissoes || setor.permissoes.length === 0)) {
            avisoEl.textContent = '⚠ Este setor não tem relatórios configurados. O usuário não verá nenhum relatório até que o setor seja configurado.';
            avisoEl.style.display = 'block';
        } else {
            avisoEl.style.display = 'none';
        }
    }

    function aplicarPermissoesSetorNovoCadastro() {
        if (novoIsAdmin.checked) return;
        var setorId = novoSetorEl.value;
        var checkboxes = novoPermissoes.querySelectorAll('input[type="checkbox"]');
        if (!setorId) {
            // Sem setor: marcar todos (comportamento padrão)
            checkboxes.forEach(function(cb) { cb.checked = true; });
        } else {
            var setor = setoresCache.find(function(s) {
                return String(parseInt(s.id, 10)) === setorId;
            });
            var perms = (setor && setor.permissoes) ? setor.permissoes : [];
            checkboxes.forEach(function(cb) {
                cb.checked = perms.indexOf(cb.value) >= 0;
            });
        }
        if (novoPermissoesAll) {
            atualizarEstadoToggleTodos(novoPermissoesAll, novoPermissoes);
        }
    }

    function montarSetorSelectHtml(selecionado, prefixo) {
        var opts = '<option value="">— Sem setor —</option>';
        setoresCache.forEach(function(s) {
            if (!s.ativo) return;
            var safeId = parseInt(s.id, 10);
            var sel = String(safeId) === String(selecionado) ? 'selected' : '';
            opts += '<option value="' + safeId + '" ' + sel + '>' + escapeHtml(s.nome) + '</option>';
        });
        var safePrefix = escapeHtml(prefixo || 'setor');
        return '<select class="js-setor-id" id="' + safePrefix + '">' + opts + '</select>';
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

    /* ── checkbox "Selecionar todos" para grid de permissões ──────────────── */
    function bindarToggleTodos(toggleEl, gridEl) {
        if (!toggleEl || !gridEl || toggleEl.dataset.bound === '1') return;
        toggleEl.dataset.bound = '1';

        function checkboxesAtivos() {
            return Array.from(gridEl.querySelectorAll('input[type="checkbox"]:not(:disabled)'));
        }

        toggleEl.addEventListener('change', function() {
            checkboxesAtivos().forEach(function(cb) { cb.checked = toggleEl.checked; });
        });

        gridEl.addEventListener('change', function(event) {
            if (event.target.type !== 'checkbox') return;
            atualizarEstadoToggleTodos(toggleEl, gridEl);
        });

        atualizarEstadoToggleTodos(toggleEl, gridEl);
    }

    function atualizarEstadoToggleTodos(toggleEl, gridEl) {
        var inputs = Array.from(gridEl.querySelectorAll('input[type="checkbox"]'));
        if (!inputs.length) {
            toggleEl.checked = false;
            toggleEl.indeterminate = false;
            return;
        }
        var marcados = inputs.filter(function(cb) { return cb.checked; }).length;
        toggleEl.checked       = marcados === inputs.length;
        toggleEl.indeterminate = marcados > 0 && marcados < inputs.length;
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
            var uid = parseInt(u.id, 10);

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
                '<details class="admin-user-row" data-user-id="' + uid + '">',
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
                montarSetorSelectHtml(u.setor_id, 'setor-' + uid),
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
                '<input type="checkbox" class="js-pode-ver-query" ' + (u.pode_ver_query ? 'checked' : '') + (u.is_admin ? '' : ' disabled') + '>',
                '<span>Pode ver a query SQL dos relatórios <span class="admin-query-hint">(requer Administrador)</span></span>',
                '</label>',
                '</div>',
                '</div>',

                /* seção 2: relatórios */
                '<div class="aur-edit-section">',
                '<span class="aur-section-label">Relatórios permitidos</span>',
                '<label class="admin-permissions-toggle-all">',
                '<input type="checkbox" class="js-permissoes-all"' + (u.is_admin ? ' disabled' : '') + '>',
                '<span>Selecionar todos os relatórios</span>',
                '</label>',
                '<div class="admin-permissions-grid js-permissoes">',
                montarPermissoesHtml('permissoes-' + uid, u.permissoes, u.is_admin),
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
    function ordenarUsuariosPorSetor(usuarios) {
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
        var idxSemSetor = ordemGrupos.indexOf('__sem_setor__');
        if (idxSemSetor > -1) {
            ordemGrupos.splice(idxSemSetor, 1);
            ordemGrupos.push('__sem_setor__');
        }
        var ordenados = [];
        ordemGrupos.forEach(function(chave) {
            grupos[chave].forEach(function(u) { ordenados.push(u); });
        });
        return ordenados;
    }

    function renderizarUsuarios(usuarios) {
        if (!usuarios.length) {
            listaUsuarios.innerHTML = '<p class="admin-vazio">Nenhum usuário cadastrado.</p>';
            return;
        }

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

        listaUsuarios.querySelectorAll('.admin-user-row').forEach(function(card) {
            var toggle = card.querySelector('.js-permissoes-all');
            var grid   = card.querySelector('.js-permissoes');
            if (toggle && grid) bindarToggleTodos(toggle, grid);
        });
    }

    function renderizarPaginacao(total) {
        renderizarPaginacaoAdmin(paginacaoEl, paginaAtual, total, POR_PAGINA, 'usuários');
    }

    function atualizarContador(total) {
        if (!contadorEl) return;
        contadorEl.textContent = total ? '(' + total + ')' : '';
    }

    function renderizarPagina() {
        var ordenados = ordenarUsuariosPorSetor(usuariosCache);
        var total = ordenados.length;
        var totalPaginas = Math.max(1, Math.ceil(total / POR_PAGINA) || 1);
        if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;
        if (paginaAtual < 1) paginaAtual = 1;
        var inicio = (paginaAtual - 1) * POR_PAGINA;
        renderizarUsuarios(ordenados.slice(inicio, inicio + POR_PAGINA));
        renderizarPaginacao(total);
        atualizarContador(total);
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
        var toggle = card.querySelector('.js-permissoes-all');
        if (toggle) {
            toggle.disabled = isAdmin;
            var grid = card.querySelector('.js-permissoes');
            if (grid) atualizarEstadoToggleTodos(toggle, grid);
        }
        var queryToggle = card.querySelector('.js-pode-ver-query');
        if (queryToggle) {
            queryToggle.disabled = !isAdmin;
            if (!isAdmin) queryToggle.checked = false;
        }
    }

    /* ── formulário de criação: sincronizar estado ────────────────────────── */
    function alternarPermissoesCriacao() {
        var desabilitar = novoIsAdmin.checked;
        novoPermissoes.querySelectorAll('input[type="checkbox"]').forEach(function(input) {
            input.disabled = desabilitar;
        });
        if (novoPermissoesAll) novoPermissoesAll.disabled = desabilitar;
        if (novoQueryToggle) {
            novoQueryToggle.disabled = !novoIsAdmin.checked;
            if (!novoIsAdmin.checked) novoQueryToggle.checked = false;
        }
    }

    function renderizarCatalogoCriacao() {
        novoPermissoes.innerHTML = montarPermissoesHtml('permissoes', catalogo.map(function(item) {
            return item.chave;
        }), false);
        if (novoPermissoesAll) {
            novoPermissoesAll.checked = true;
            bindarToggleTodos(novoPermissoesAll, novoPermissoes);
            atualizarEstadoToggleTodos(novoPermissoesAll, novoPermissoes);
        }
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
                usuariosCache = data.usuarios || [];
                renderizarPagina();
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
        if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
            mostrarMensagem('Informe um e-mail válido.', 'erro');
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
            var painelNovo = document.getElementById('painel-novo-usuario');
            if (painelNovo) painelNovo.open = false;
            paginaAtual = 1;
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

    /* ── painéis colapsáveis ──────────────────────────────────────────────── */
    persistirPaineisAdmin('admin.usuarios.panel.');

    if (paginacaoEl) {
        paginacaoEl.addEventListener('click', function(event) {
            var btn = event.target.closest('[data-pag]');
            if (!btn || btn.disabled) return;
            paginaAtual = lerPaginaPaginacao(btn, paginaAtual);
            renderizarPagina();
            var listaPainel = document.getElementById('painel-usuarios-lista');
            if (listaPainel) listaPainel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }

    /* ── init ─────────────────────────────────────────────────────────────── */
    novoIsAdmin.addEventListener('change', alternarPermissoesCriacao);
    renderizarCatalogoCriacao();
    alternarPermissoesCriacao();
    carregarSetores().then(function() { carregarDados(); });
});
