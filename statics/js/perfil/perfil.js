document.addEventListener('DOMContentLoaded', function() {
    var tokenNomeEl      = document.getElementById('token-nome');
    var btnCriar         = document.getElementById('btn-criar-token');
    var tokenList        = document.getElementById('token-list');
    var tokenReveal      = document.getElementById('token-novo-reveal');
    var mensagem         = document.getElementById('mensagem');
    var urlExemploEl     = document.getElementById('url-exemplo');
    var escopoOpcoes     = document.getElementById('token-escopo-opcoes');
    var escopoAviso      = document.getElementById('token-escopo-aviso');
    var endpointsBox     = document.getElementById('endpoints-box');
    var mensagemTimeout  = null;
    var BASE_URL         = window.location.origin;

    // Lista declarativa dos relatórios disponíveis para este usuário, vinda do backend.
    // Cada item: { chave, tag, titulo, url_path }
    var endpointsEl = document.getElementById('perfil-endpoints');
    var ENDPOINTS   = [];
    try {
        ENDPOINTS = endpointsEl ? (JSON.parse(endpointsEl.textContent) || []) : [];
    } catch (e) {
        ENDPOINTS = [];
    }

    function montarUrlEndpoint(endpoint, token) {
        var t = token || 'SEU_TOKEN';
        return BASE_URL + endpoint.url_path + '?token=' + t;
    }

    /* ── renderizar checkboxes de escopo disponíveis ──────────────────────── */
    function renderizarEscopoOpcoes() {
        if (!escopoOpcoes) return;
        if (!ENDPOINTS.length) {
            escopoOpcoes.innerHTML = '<span style="font-size:.82rem;color:#aaa">Nenhum relatório disponível para você.</span>';
            return;
        }
        escopoOpcoes.innerHTML = ENDPOINTS.map(function(ep) {
            return [
                '<label class="admin-toggle" style="flex-direction:row;align-items:center;gap:8px;',
                'padding:8px 12px;border:1px solid #e8e8e8;background:#fafafa;cursor:pointer">',
                '<input type="checkbox" class="js-escopo-check" value="' + escapeHtml(ep.chave) + '" checked>',
                '<span style="font-size:.85rem">' + escapeHtml(ep.titulo) + '</span>',
                '</label>'
            ].join('');
        }).join('');
    }

    function coletarEscopos() {
        if (!escopoOpcoes) return [];
        return Array.from(escopoOpcoes.querySelectorAll('.js-escopo-check:checked')).map(function(el) {
            return el.value;
        });
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

    function escapeHtml(t) {
        return String(t || '').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
            .replace(/"/g,'&quot;').replace(/'/g,'&#39;');
    }

    function copiarTexto(texto, btn) {
        navigator.clipboard.writeText(texto).then(function() {
            var orig = btn.textContent;
            btn.textContent = 'Copiado!';
            setTimeout(function() { btn.textContent = orig; }, 1500);
        }).catch(function() {
            mostrarMensagem('Não foi possível copiar automaticamente. Copie manualmente.', 'erro');
        });
    }

    function atualizarUrlsInterface(token) {
        if (!endpointsBox) return;
        var temToken = !!token;
        var linhas = endpointsBox.querySelectorAll('.endpoint-row');
        linhas.forEach(function(row) {
            var chave = row.getAttribute('data-chave');
            var urlPath = row.getAttribute('data-url-path');
            var ep = ENDPOINTS.find(function(e) { return e.chave === chave; })
                     || { url_path: urlPath };
            var urlEl = row.querySelector('.js-endpoint-url');
            var btnEl = row.querySelector('.js-endpoint-copy');
            var url = montarUrlEndpoint(ep, token);
            if (urlEl) urlEl.textContent = temToken ? url : '— gere um token para ver a URL —';
            if (btnEl) btnEl.disabled = !temToken;
        });

        if (urlExemploEl) {
            if (temToken && ENDPOINTS.length) {
                urlExemploEl.textContent = montarUrlEndpoint(ENDPOINTS[0], token);
            } else {
                urlExemploEl.textContent = '— gere um token para ver o exemplo —';
            }
        }
    }

    function labelPorChave(chave) {
        var ep = ENDPOINTS.find(function(e) { return e.chave === chave; });
        return ep ? ep.titulo : chave;
    }

    function renderizarTokens(tokens) {
        if (!tokens.length) {
            tokenList.innerHTML = '<li style="font-size:.85rem;color:#aaa">Nenhum token ativo. Gere um acima.</li>';
            return;
        }
        tokenList.innerHTML = tokens.map(function(t) {
            var escopoLabels = (t.permissoes || []).map(function(chave) {
                return '<span style="font-size:.72rem;background:#e8f4ff;color:#1a6fa8;padding:2px 7px;border-radius:0;border:1px solid #b3d9f7">' +
                    escapeHtml(labelPorChave(chave)) + '</span>';
            }).join(' ');
            var escopoHtml = escopoLabels
                ? '<div style="margin-top:4px;display:flex;flex-wrap:wrap;gap:4px">' + escopoLabels + '</div>'
                : '<span style="font-size:.72rem;color:#aaa">(escopo legado — acesso via permissões do usuário)</span>';

            return [
                '<li class="token-item" data-id="' + t.id + '">',
                '<div class="token-item-info">',
                '<div class="token-item-nome">' + escapeHtml(t.nome) + '</div>',
                '<div class="token-item-meta">Criado: ' + escapeHtml(t.criado_em) + ' &nbsp;·&nbsp; Último uso: ' + escapeHtml(t.ultimo_uso) + '</div>',
                escopoHtml,
                '</div>',
                '<button type="button" class="token-btn-revogar" data-id="' + t.id + '">Revogar</button>',
                '</li>'
            ].join('');
        }).join('');
    }

    function mostrarTokenNovo(token, escoposSelecionados) {
        // Gera uma linha de URL para cada endpoint incluído no escopo do token criado.
        var escoposSet = new Set(escoposSelecionados || []);
        var linhasUrls = ENDPOINTS
            .filter(function(ep) { return escoposSet.has(ep.chave); })
            .map(function(ep) {
                var url = montarUrlEndpoint(ep, token);
                return [
                    '<div class="endpoint-row">',
                    '<span class="endpoint-tag">' + escapeHtml(ep.tag) + '</span>',
                    '<span class="endpoint-url">' + escapeHtml(url) + '</span>',
                    '<button type="button" class="endpoint-copy" data-value="' + escapeHtml(url) + '">Copiar</button>',
                    '</div>'
                ].join('');
            });

        tokenReveal.style.display = 'block';
        tokenReveal.innerHTML = [
            '<div class="token-novo-box">',
            '<p>Token gerado com sucesso!</p>',
            '<small>⚠ Copie agora — este valor não será exibido novamente.</small>',
            '<div class="token-copy-row">',
            '<span class="token-value" id="token-val">' + escapeHtml(token) + '</span>',
            '<button type="button" class="token-copy-btn" id="btn-copiar-token">Copiar token</button>',
            '</div>',
            linhasUrls.length
                ? '<div style="margin-top:14px;display:flex;flex-direction:column;gap:6px">' +
                  '<p style="margin:0 0 6px;font-size:.82rem;color:#2d7a47;font-weight:600">URLs prontas (seus acessos):</p>' +
                  linhasUrls.join('') +
                  '</div>'
                : '',
            '</div>'
        ].join('');

        document.getElementById('btn-copiar-token').addEventListener('click', function() {
            copiarTexto(token, this);
        });
    }

    function carregarTokens() {
        return fetch('/api/meu-perfil/tokens')
            .then(function(r) { return r.json(); })
            .then(function(d) { renderizarTokens(d.tokens || []); })
            .catch(function() { tokenList.innerHTML = '<li style="color:#c0392b;font-size:.85rem">Falha ao carregar tokens.</li>'; });
    }

    btnCriar.addEventListener('click', function() {
        var nome = tokenNomeEl.value.trim();
        if (!nome) { tokenNomeEl.focus(); mostrarMensagem('Dê um nome ao token antes de criar.', 'erro'); return; }

        var escopos = coletarEscopos();
        if (!escopos.length) {
            if (escopoAviso) escopoAviso.style.display = 'block';
            mostrarMensagem('Selecione pelo menos um relatório para o token.', 'erro');
            return;
        }
        if (escopoAviso) escopoAviso.style.display = 'none';

        mostrarMensagem('Gerando token...', 'processando');
        fetch('/api/meu-perfil/tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nome: nome, permissoes: escopos })
        })
        .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
        .then(function(d) {
            tokenNomeEl.value = '';
            mostrarMensagem(d.mensagem || 'Token gerado.', 'sucesso');
            mostrarTokenNovo(d.token, escopos);
            atualizarUrlsInterface(d.token);
            return carregarTokens();
        })
        .catch(function(e) { mostrarMensagem(e.message || 'Falha ao gerar token.', 'erro'); });
    });

    tokenList.addEventListener('click', function(e) {
        if (!e.target.classList.contains('token-btn-revogar')) return;
        var id = e.target.getAttribute('data-id');
        if (!window.confirm('Revogar este token? Todas as conexões que usam ele perderão acesso.')) return;
        mostrarMensagem('Revogando token...', 'processando');
        fetch('/api/meu-perfil/tokens/' + id, { method: 'DELETE' })
        .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
        .then(function(d) {
            mostrarMensagem(d.mensagem || 'Token revogado. Atualize a URL nas ferramentas que usavam este token.', 'sucesso');
            tokenReveal.style.display = 'none';
            atualizarUrlsInterface(null);
            return carregarTokens();
        })
        .catch(function(e) { mostrarMensagem(e.message || 'Falha ao revogar token.', 'erro'); });
    });

    tokenReveal.addEventListener('click', function(e) {
        if (!e.target.classList.contains('endpoint-copy')) return;
        copiarTexto(e.target.getAttribute('data-value'), e.target);
    });

    if (endpointsBox) {
        endpointsBox.addEventListener('click', function(e) {
            var btn = e.target.closest('.js-endpoint-copy');
            if (!btn || btn.disabled) return;
            var row = btn.closest('.endpoint-row');
            var urlEl = row && row.querySelector('.js-endpoint-url');
            if (urlEl) copiarTexto(urlEl.textContent, btn);
        });
    }

    renderizarEscopoOpcoes();
    atualizarUrlsInterface(null);
    carregarTokens();

    /* ── Toggle mostrar/ocultar senha ────────────────────────────────────── */
    document.querySelectorAll('.btn-ver-senha-perfil').forEach(function (btn) {
        btn.addEventListener('click', function () {
            var input = document.getElementById(btn.dataset.alvo);
            if (!input) return;
            var visivel = input.type === 'text';
            input.type = visivel ? 'password' : 'text';
            btn.textContent = visivel ? 'ver' : 'ocultar';
        });
    });

    /* ── Alterar senha ───────────────────────────────────────────────────── */
    var formAlterarSenha = document.getElementById('form-alterar-senha');
    if (formAlterarSenha) {
        formAlterarSenha.addEventListener('submit', function (e) {
            e.preventDefault();
            var erroEl  = document.getElementById('alterar-senha-erro');
            var btnEl   = document.getElementById('btn-alterar-senha');
            var senhaAtual  = document.getElementById('perfil-senha-atual').value;
            var novaSenha   = document.getElementById('perfil-nova-senha').value;
            var confirmar   = document.getElementById('perfil-confirmar-senha').value;

            erroEl.style.display = 'none';
            erroEl.textContent   = '';

            if (!senhaAtual || !novaSenha || !confirmar) {
                erroEl.textContent = 'Preencha todos os campos.';
                erroEl.style.display = 'block';
                return;
            }
            if (novaSenha !== confirmar) {
                erroEl.textContent = 'As senhas nao conferem.';
                erroEl.style.display = 'block';
                return;
            }
            if (novaSenha.length < 10) {
                erroEl.textContent = 'A nova senha deve ter pelo menos 10 caracteres.';
                erroEl.style.display = 'block';
                return;
            }
            if (!/\d/.test(novaSenha)) {
                erroEl.textContent = 'A nova senha deve conter pelo menos um numero.';
                erroEl.style.display = 'block';
                return;
            }

            var labelOriginal = btnEl.textContent;
            btnEl.disabled    = true;
            btnEl.textContent = 'Salvando...';

            fetch('/api/meu-perfil/alterar-senha', {
                method:  'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': (document.querySelector('meta[name="csrf-token"]') || {}).content || '',
                },
                body: JSON.stringify({
                    senha_atual:     senhaAtual,
                    nova_senha:      novaSenha,
                    confirmar_senha: confirmar,
                }),
            })
            .then(function (resp) {
                return resp.json().then(function (data) {
                    if (!resp.ok) throw new Error(data.erro || 'Erro ao alterar senha.');
                    return data;
                });
            })
            .then(function () {
                formAlterarSenha.reset();
                mostrarMensagem('Senha alterada com sucesso.');
            })
            .catch(function (err) {
                erroEl.textContent   = err.message;
                erroEl.style.display = 'block';
            })
            .finally(function () {
                btnEl.disabled    = false;
                btnEl.textContent = labelOriginal;
            });
        });
    }
});
