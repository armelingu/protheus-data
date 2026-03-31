document.addEventListener('DOMContentLoaded', function() {
    var tokenNomeEl    = document.getElementById('token-nome');
    var btnCriar       = document.getElementById('btn-criar-token');
    var tokenList      = document.getElementById('token-list');
    var tokenReveal    = document.getElementById('token-novo-reveal');
    var mensagem       = document.getElementById('mensagem');
    var urlPedidosEl   = document.getElementById('url-pedidos');
    var urlEstoqueEl   = document.getElementById('url-estoque');
    var urlExemploEl   = document.getElementById('url-exemplo-pedidos');
    var mensagemTimeout = null;
    var BASE_URL        = window.location.origin;

    var permEl = document.getElementById('perfil-permissoes');
    var perms  = permEl ? JSON.parse(permEl.textContent) : { pode_pedidos: false, pode_estoque: false };

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

    function montarUrls(token) {
        var t = token || 'SEU_TOKEN';
        var obj = {};
        if (perms.pode_pedidos) obj.pedidos = BASE_URL + '/odata/pedidos?token=' + t;
        if (perms.pode_estoque) obj.estoque = BASE_URL + '/odata/estoque?token=' + t;
        return obj;
    }

    function atualizarUrlsInterface(token) {
        var urls = montarUrls(token);
        if (urlPedidosEl && urls.pedidos) urlPedidosEl.textContent = urls.pedidos;
        if (urlEstoqueEl && urls.estoque) urlEstoqueEl.textContent = urls.estoque;
        if (urlExemploEl && urls.pedidos)  urlExemploEl.textContent = urls.pedidos;
    }

    function renderizarTokens(tokens) {
        if (!tokens.length) {
            tokenList.innerHTML = '<li style="font-size:.85rem;color:#aaa">Nenhum token ativo. Gere um acima.</li>';
            return;
        }
        tokenList.innerHTML = tokens.map(function(t) {
            return [
                '<li class="token-item" data-id="' + t.id + '">',
                '<div class="token-item-info">',
                '<div class="token-item-nome">' + escapeHtml(t.nome) + '</div>',
                '<div class="token-item-meta">Criado: ' + escapeHtml(t.criado_em) + ' &nbsp;·&nbsp; Último uso: ' + escapeHtml(t.ultimo_uso) + '</div>',
                '</div>',
                '<button type="button" class="token-btn-revogar" data-id="' + t.id + '">Revogar</button>',
                '</li>'
            ].join('');
        }).join('');
    }

    function mostrarTokenNovo(token) {
        var urls = montarUrls(token);
        var linhasUrls = [];
        if (urls.pedidos) {
            linhasUrls.push(
                '<div class="endpoint-row">',
                '<span class="endpoint-tag">Pedidos</span>',
                '<span class="endpoint-url">' + escapeHtml(urls.pedidos) + '</span>',
                '<button type="button" class="endpoint-copy" data-value="' + escapeHtml(urls.pedidos) + '">Copiar</button>',
                '</div>'
            );
        }
        if (urls.estoque) {
            linhasUrls.push(
                '<div class="endpoint-row">',
                '<span class="endpoint-tag">Estoque</span>',
                '<span class="endpoint-url">' + escapeHtml(urls.estoque) + '</span>',
                '<button type="button" class="endpoint-copy" data-value="' + escapeHtml(urls.estoque) + '">Copiar</button>',
                '</div>'
            );
        }

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
        mostrarMensagem('Gerando token...', 'processando');
        fetch('/api/meu-perfil/tokens', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ nome: nome })
        })
        .then(function(r) { return r.json().then(function(d) { if (!r.ok) throw new Error(d.erro); return d; }); })
        .then(function(d) {
            tokenNomeEl.value = '';
            mostrarMensagem(d.mensagem || 'Token gerado.', 'sucesso');
            mostrarTokenNovo(d.token);
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
            mostrarMensagem(d.mensagem || 'Token revogado.', 'sucesso');
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

    document.querySelectorAll('.endpoint-copy[data-target]').forEach(function(btn) {
        btn.addEventListener('click', function() {
            var el = document.getElementById(btn.getAttribute('data-target'));
            if (el) copiarTexto(el.textContent, btn);
        });
    });

    atualizarUrlsInterface(null);
    carregarTokens();
});
