document.addEventListener('DOMContentLoaded', function() {
    var formCriar = document.getElementById('form-criar-usuario');
    var listaUsuarios = document.getElementById('lista-usuarios');
    var mensagem = document.getElementById('mensagem');
    var novoUsuarioPermissoes = document.getElementById('novo-usuario-permissoes');
    var novoIsAdmin = document.getElementById('novo-is-admin');
    var catalogo = JSON.parse(document.getElementById('admin-relatorios-catalogo').textContent || '[]');
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

    function montarPermissoesHtml(nomeCampo, selecionadas, desabilitado) {
        return catalogo.map(function(relatorio) {
            var checked = selecionadas.indexOf(relatorio.chave) >= 0 ? 'checked' : '';
            var disabled = desabilitado ? 'disabled' : '';
            return [
                '<label class="admin-permission-chip">',
                '<span>',
                '<input type="checkbox" name="' + nomeCampo + '" value="' + escapeHtml(relatorio.chave) + '" ' + checked + ' ' + disabled + '>',
                '</span>',
                '<span>',
                '<strong>' + escapeHtml(relatorio.titulo) + '</strong>',
                '<span>' + escapeHtml(relatorio.modulo_titulo) + '</span>',
                '</span>',
                '</label>'
            ].join('');
        }).join('');
    }

    function coletarPermissoes(raiz, nomeCampo) {
        return Array.from(raiz.querySelectorAll('input[name="' + nomeCampo + '"]:checked')).map(function(input) {
            return input.value;
        });
    }

    function labelStatusEmail(emailAcesso) {
        var status = emailAcesso && emailAcesso.status ? emailAcesso.status : 'nunca_enviado';
        if (status === 'enviado') {
            return 'Enviado';
        }
        if (status === 'falha') {
            return 'Falhou';
        }
        return 'Nunca enviado';
    }

    function renderizarCatalogoCriacao() {
        novoUsuarioPermissoes.innerHTML = montarPermissoesHtml('permissoes', catalogo.map(function(item) {
            return item.chave;
        }), false);
    }

    function alternarPermissoesCriacao() {
        var desabilitar = novoIsAdmin.checked;
        novoUsuarioPermissoes.querySelectorAll('input[type="checkbox"]').forEach(function(input) {
            input.disabled = desabilitar;
        });
    }

    function renderizarUsuarios(usuarios) {
        if (!usuarios.length) {
            listaUsuarios.innerHTML = '<p class="admin-vazio">Nenhum usuário cadastrado até o momento.</p>';
            return;
        }

        listaUsuarios.innerHTML = usuarios.map(function(usuario) {
            var badgesStatus = [];
            badgesStatus.push('<span class="admin-badge ' + (usuario.ativo ? 'is-strong' : 'is-danger') + '">' + (usuario.ativo ? 'Ativo' : 'Desativado') + '</span>');
            if (usuario.deve_trocar_senha) {
                badgesStatus.push('<span class="admin-badge is-danger">Troca pendente</span>');
            }
            var emailBadge = '<span class="admin-badge">E-mail: nunca enviado</span>';
            if (usuario.email_acesso && usuario.email_acesso.status === 'enviado') {
                emailBadge = '<span class="admin-badge is-strong">E-mail enviado</span>';
            } else if (usuario.email_acesso && usuario.email_acesso.status === 'falha') {
                emailBadge = '<span class="admin-badge is-danger">E-mail com falha</span>';
            }
            var perfil = usuario.is_admin
                ? '<span class="admin-badge is-strong">Superadmin</span>'
                : '<span class="admin-badge">Padrão</span>';

            return [
                '<details class="admin-user-row" data-user-id="' + usuario.id + '">',
                '<summary class="admin-user-summary">',
                '<div class="admin-user-col">',
                '<strong class="admin-user-name">' + escapeHtml(usuario.nome) + '</strong>',
                '<span class="admin-user-login">' + escapeHtml(usuario.usuario) + '</span>',
                '<span class="admin-user-created">' + escapeHtml(usuario.email || '--') + '</span>',
                '</div>',
                '<div class="admin-user-col">' + perfil + '</div>',
                '<div class="admin-user-col"><div class="admin-badges">' + badgesStatus.join('') + emailBadge + '</div></div>',
                '<div class="admin-user-col"><span class="admin-user-last-login">' + escapeHtml(usuario.ultimo_login_em || 'Nunca') + '</span></div>',
                '<div class="admin-user-actions-preview"><span class="admin-expand-hint">Abrir edição</span></div>',
                '</summary>',
                '<div class="admin-user-detail">',
                '<div class="admin-user-detail-grid">',
                '<section class="admin-detail-panel">',
                '<span class="admin-detail-title">Dados da conta</span>',
                '<div class="admin-detail-stack">',
                '<label class="admin-toggle">',
                '<input type="checkbox" class="js-is-admin" ' + (usuario.is_admin ? 'checked' : '') + '>',
                '<span>Usuário com acesso total de administração</span>',
                '</label>',
                '<p class="admin-inline-meta">E-mail: ' + escapeHtml(usuario.email || '--') + '</p>',
                '<p class="admin-inline-meta">Status do e-mail: ' + escapeHtml(labelStatusEmail(usuario.email_acesso)) + '</p>',
                '<p class="admin-inline-meta">Última atualização do e-mail: ' + escapeHtml((usuario.email_acesso && usuario.email_acesso.atualizado_em) || '--') + '</p>',
                '<p class="admin-inline-meta">Último erro de envio: ' + escapeHtml((usuario.email_acesso && usuario.email_acesso.ultimo_erro) || '--') + '</p>',
                '<p class="admin-inline-meta">Criado em ' + escapeHtml(usuario.criado_em || '--') + '</p>',
                '<p class="admin-inline-meta">Último login em ' + escapeHtml(usuario.ultimo_login_em || 'Nunca') + '</p>',
                '</div>',
                '</section>',
                '<section class="admin-detail-panel">',
                '<span class="admin-detail-title">Permissões por relatório</span>',
                '<div class="admin-permissions-grid js-permissoes">' + montarPermissoesHtml('permissoes-' + usuario.id, usuario.permissoes, usuario.is_admin) + '</div>',
                '</section>',
                '<section class="admin-detail-panel">',
                '<span class="admin-detail-title">Ações</span>',
                '<div class="admin-detail-actions">',
                '<button type="button" class="admin-btn admin-btn-primario js-salvar">Salvar alterações</button>',
                '<button type="button" class="admin-btn admin-btn-secundario js-reenviar-email">Reenviar e-mail</button>',
                '<button type="button" class="admin-btn admin-btn-secundario js-reset-senha">Resetar senha</button>',
                '<button type="button" class="admin-btn admin-btn-secundario js-status">' + (usuario.ativo ? 'Desativar usuário' : 'Ativar usuário') + '</button>',
                '</div>',
                '</div>',
                '</div>',
                '</details>'
            ].join('');
        }).join('');
    }

    function carregarDados() {
        mostrarMensagem('Atualizando gerenciamento...', 'processando');
        return fetch('/api/admin/usuarios').then(function(resp) {
            return resp.json().then(function(data) {
                if (!resp.ok) {
                    throw new Error(data.erro || 'Falha ao carregar usuários.');
                }
                return data;
            });
        }).then(function(dadosUsuarios) {
            renderizarUsuarios(dadosUsuarios.usuarios || []);
            mostrarMensagem('Gerenciamento carregado.', 'sucesso');
        }).catch(function() {
            mostrarMensagem('Falha ao carregar dados da administração.', 'erro');
        });
    }

    formCriar.addEventListener('submit', function(event) {
        event.preventDefault();
        var email = formCriar.email.value.trim().toLowerCase();
        if (!/@hbraviacao\.com\.br$/.test(email)) {
            mostrarMensagem('Use um e-mail corporativo @hbraviacao.com.br.', 'erro');
            return;
        }

        var payload = {
            email: email,
            is_admin: novoIsAdmin.checked,
            permissoes: coletarPermissoes(formCriar, 'permissoes')
        };

        mostrarMensagem('Criando usuário...', 'processando');
        fetch('/api/admin/usuarios', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        })
            .then(function(resp) {
                return resp.json().then(function(data) {
                    if (!resp.ok) {
                        throw new Error(data.erro || 'Falha ao criar usuário.');
                    }
                    return data;
                });
            })
            .then(function(data) {
                formCriar.reset();
                renderizarCatalogoCriacao();
                alternarPermissoesCriacao();
                var texto = (data && data.mensagem) || 'Usuário criado com sucesso.';
                mostrarMensagem(texto, 'sucesso');
                return carregarDados();
            })
            .catch(function(err) {
                mostrarMensagem(err.message || 'Falha ao criar usuário.', 'erro');
            });
    });

    listaUsuarios.addEventListener('change', function(event) {
        if (!event.target.classList.contains('js-is-admin')) {
            return;
        }
        var card = event.target.closest('.admin-user-row');
        var desabilitar = event.target.checked;
        card.querySelectorAll('.js-permissoes input[type="checkbox"]').forEach(function(input) {
            input.disabled = desabilitar;
        });
    });

    listaUsuarios.addEventListener('click', function(event) {
        var card = event.target.closest('.admin-user-row');
        if (!card) {
            return;
        }

        var userId = card.getAttribute('data-user-id');

        if (event.target.classList.contains('js-salvar')) {
            var payload = {
                is_admin: card.querySelector('.js-is-admin').checked,
                permissoes: coletarPermissoes(card, 'permissoes-' + userId)
            };
            mostrarMensagem('Salvando configuração...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/configuracao', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            })
                .then(function(resp) {
                    return resp.json().then(function(data) {
                        if (!resp.ok) {
                            throw new Error(data.erro || 'Falha ao salvar configuração.');
                        }
                        return data;
                    });
                })
                .then(function() {
                    mostrarMensagem('Configuração atualizada.', 'sucesso');
                    return carregarDados();
                })
                .catch(function(err) {
                    mostrarMensagem(err.message || 'Falha ao salvar configuração.', 'erro');
                });
        }

        if (event.target.classList.contains('js-reset-senha')) {
            mostrarMensagem('Resetando senha...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/reset-senha', { method: 'POST' })
                .then(function(resp) {
                    return resp.json().then(function(data) {
                        if (!resp.ok) {
                            throw new Error(data.erro || 'Falha ao resetar senha.');
                        }
                        return data;
                    });
                })
                .then(function() {
                    mostrarMensagem('Senha resetada para o login.', 'sucesso');
                    return carregarDados();
                })
                .catch(function(err) {
                    mostrarMensagem(err.message || 'Falha ao resetar senha.', 'erro');
                });
        }

        if (event.target.classList.contains('js-reenviar-email')) {
            mostrarMensagem('Reenviando e-mail...', 'processando');
            fetch('/api/admin/usuarios/' + userId + '/reenviar-email', { method: 'POST' })
                .then(function(resp) {
                    return resp.json().then(function(data) {
                        if (!resp.ok) {
                            throw new Error(data.erro || 'Falha ao reenviar e-mail.');
                        }
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

        if (event.target.classList.contains('js-status')) {
            var ativar = event.target.textContent.trim() === 'Ativar';
            mostrarMensagem((ativar ? 'Ativando usuário...' : 'Desativando usuário...'), 'processando');
            fetch('/api/admin/usuarios/' + userId + '/status', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ ativo: ativar })
            })
                .then(function(resp) {
                    return resp.json().then(function(data) {
                        if (!resp.ok) {
                            throw new Error(data.erro || 'Falha ao atualizar status.');
                        }
                        return data;
                    });
                })
                .then(function(data) {
                    mostrarMensagem(data.mensagem || 'Status atualizado.', 'sucesso');
                    if (data.redirect) {
                        window.location.href = data.redirect;
                        return null;
                    }
                    return carregarDados();
                })
                .catch(function(err) {
                    mostrarMensagem(err.message || 'Falha ao atualizar status.', 'erro');
                });
        }
    });

    novoIsAdmin.addEventListener('change', alternarPermissoesCriacao);

    renderizarCatalogoCriacao();
    alternarPermissoesCriacao();
    carregarDados();
});
