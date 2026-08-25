document.addEventListener('DOMContentLoaded', function () {
    var form = document.getElementById('form-criar-aviso');
    var selectRelatorio = document.getElementById('aviso-relatorio');
    var lista = document.getElementById('lista-avisos');
    var paginacaoEl = document.getElementById('paginacao-avisos');
    var contadorEl = document.getElementById('contador-avisos');
    var mensagem = document.getElementById('mensagem');
    var botao = document.getElementById('btn-publicar-aviso');
    var catalogoEl = document.getElementById('admin-relatorios-catalogo');
    var mensagemTimeout = null;
    var catalogo = [];
    var avisosCache = [];
    var paginaAtual = 1;
    var POR_PAGINA = 10;

    try {
        catalogo = JSON.parse(catalogoEl.textContent || '[]');
    } catch (err) {
        catalogo = [];
    }

    function mostrarMensagem(texto, tipo) {
        mensagem.textContent = texto;
        mensagem.className = 'mensagem ' + (tipo || 'sucesso') + ' visivel';
        window.clearTimeout(mensagemTimeout);
        if (tipo !== 'processando') {
            mensagemTimeout = window.setTimeout(function () {
                mensagem.className = 'mensagem';
            }, 3600);
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

    function rotuloRelatorio(aviso) {
        if (aviso.modulo_titulo && aviso.relatorio_titulo) {
            return aviso.modulo_titulo + ' / ' + aviso.relatorio_titulo;
        }
        return (aviso.modulo_id || '') + '.' + (aviso.relatorio_id || '');
    }

    function preencherSelect() {
        var grupos = {};
        catalogo.forEach(function (item) {
            var modulo = item.modulo_titulo || item.modulo_id;
            if (!grupos[modulo]) {
                grupos[modulo] = [];
            }
            grupos[modulo].push(item);
        });
        Object.keys(grupos).forEach(function (modulo) {
            var group = document.createElement('optgroup');
            group.label = modulo;
            grupos[modulo].forEach(function (item) {
                var option = document.createElement('option');
                option.value = item.chave;
                option.textContent = item.titulo;
                group.appendChild(option);
            });
            selectRelatorio.appendChild(group);
        });
    }

    function renderizarAvisos(avisos) {
        if (!avisos.length) {
            lista.innerHTML = '<p class="admin-vazio">Nenhum aviso publicado ainda.</p>';
            return;
        }
        lista.innerHTML = avisos.map(function (aviso) {
            var emails = (aviso.emails_enviados || 0) + ' enviados';
            if (aviso.emails_falha) {
                emails += ' · ' + aviso.emails_falha + ' falha' + (aviso.emails_falha === 1 ? '' : 's');
            }
        var versao = aviso.versao ? '<small>Versão ' + escapeHtml(aviso.versao) + '</small>' : '';
        return [
            '<article class="aviso-lista-row">',
            '<div>',
            '<strong class="admin-log-title">' + escapeHtml(rotuloRelatorio(aviso)) + '</strong>',
            versao,
            '</div>',
                '<div>',
                '<strong class="admin-log-title">' + escapeHtml(aviso.titulo) + '</strong>',
                '<p class="aviso-lista-sub">' + escapeHtml(aviso.mensagem) + '</p>',
                '</div>',
                '<div class="aviso-lista-meta">' + escapeHtml(emails) + '</div>',
                '<div class="aviso-lista-meta">' + escapeHtml(aviso.criado_em || '—'),
                '<small>' + escapeHtml(aviso.criado_por_nome || 'Admin') + '</small>',
                '</div>',
                '</article>',
            ].join('');
        }).join('');
    }

    function carregarAvisos() {
        fetch('/api/admin/avisos')
            .then(function (resp) {
                if (resp.status === 401) {
                    window.location.href = '/login';
                    return null;
                }
                return resp.json().then(function (data) {
                    if (!resp.ok) {
                        throw new Error(data.erro || 'Falha ao carregar avisos.');
                    }
                    return data;
                });
            })
            .then(function (dados) {
                if (!dados) {
                    return;
                }
                avisosCache = dados.avisos || [];
                renderizarPagina();
            })
            .catch(function (err) {
                lista.innerHTML = '<p class="admin-vazio">' + escapeHtml(err.message || 'Falha ao carregar avisos.') + '</p>';
            });
    }

    form.addEventListener('submit', function (evento) {
        evento.preventDefault();
        var chave = (selectRelatorio.value || '').trim();
        var versao = (form.versao.value || '').trim();
        var titulo = (form.titulo.value || '').trim();
        var texto = (form.mensagem.value || '').trim();
        if (!chave || !versao || !titulo || !texto) {
            mostrarMensagem('Preencha versão, relatório, título e mensagem.', 'erro');
            return;
        }

        botao.disabled = true;
        mostrarMensagem('Publicando aviso...', 'processando');
        fetch('/api/admin/avisos', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chave: chave,
                versao: versao,
                titulo: titulo,
                mensagem: texto,
            }),
        })
            .then(function (resp) {
                return resp.json().then(function (data) {
                    if (!resp.ok) {
                        throw new Error(data.erro || 'Falha ao publicar aviso.');
                    }
                    return data;
                });
            })
            .then(function (data) {
                form.reset();
                if (form.versao) form.versao.value = '1.0';
                mostrarMensagem(data.mensagem || 'Aviso publicado.', 'sucesso');
                var painelNovo = document.getElementById('painel-novo-aviso');
                if (painelNovo) painelNovo.open = false;
                paginaAtual = 1;
                carregarAvisos();
                window.setTimeout(carregarAvisos, 4000);
            })
            .catch(function (err) {
                mostrarMensagem(err.message || 'Falha ao publicar aviso.', 'erro');
            })
            .finally(function () {
                botao.disabled = false;
            });
    });

    function renderizarPagina() {
        var total = avisosCache.length;
        var totalPaginas = Math.max(1, Math.ceil(total / POR_PAGINA) || 1);
        if (paginaAtual > totalPaginas) paginaAtual = totalPaginas;
        if (paginaAtual < 1) paginaAtual = 1;
        var inicio = (paginaAtual - 1) * POR_PAGINA;
        renderizarAvisos(avisosCache.slice(inicio, inicio + POR_PAGINA));
        renderizarPaginacaoAdmin(paginacaoEl, paginaAtual, total, POR_PAGINA, 'avisos');
        if (contadorEl) contadorEl.textContent = total ? '(' + total + ')' : '';
    }

    preencherSelect();
    persistirPaineisAdmin('admin.avisos.panel.');
    if (paginacaoEl) {
        paginacaoEl.addEventListener('click', function (event) {
            var btn = event.target.closest('[data-pag]');
            if (!btn || btn.disabled) return;
            paginaAtual = lerPaginaPaginacao(btn, paginaAtual);
            renderizarPagina();
            var listaPainel = document.getElementById('painel-avisos-lista');
            if (listaPainel) listaPainel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        });
    }
    carregarAvisos();
});
