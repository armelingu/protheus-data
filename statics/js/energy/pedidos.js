var API_BASE = '/api/relatorios/energy/pedidos';
var mensagemTimeout = null;
var _historicoOffset = 0;
var _HISTORICO_LIMIT = 10;

document.addEventListener('DOMContentLoaded', function() {
    var btnSync = document.getElementById('btn-sync');
    if (btnSync) btnSync.disabled = true;
    Promise.all([carregarInfo(), carregarHistoricoSync()])
        .finally(function() { if (btnSync) btnSync.disabled = false; });

    var botoes = [
        document.getElementById('btn-baixar'),
        document.getElementById('btn-sync')
    ];

    for (var i = 0; i < botoes.length; i++) {
        if (botoes[i] && !botoes[i].getAttribute('data-default-label')) {
            botoes[i].setAttribute('data-default-label', botoes[i].textContent);
        }
    }

    var btnLimpar = document.getElementById('btn-limpar-filtro');
    if (btnLimpar) {
        btnLimpar.addEventListener('click', function() {
            var inicio = document.getElementById('filtro-data-inicio');
            var fim    = document.getElementById('filtro-data-fim');
            if (inicio) inicio.value = '';
            if (fim)    fim.value   = '';
            document.querySelector('.painel-controles').classList.remove('filtro-ativo');
        });
    }

    var inputInicio = document.getElementById('filtro-data-inicio');
    var inputFim    = document.getElementById('filtro-data-fim');
    function atualizarFiltroAtivo() {
        var ativo = (inputInicio && inputInicio.value) || (inputFim && inputFim.value);
        document.querySelector('.painel-controles').classList.toggle('filtro-ativo', !!ativo);
    }
    if (inputInicio) inputInicio.addEventListener('change', atualizarFiltroAtivo);
    if (inputFim)    inputFim.addEventListener('change', atualizarFiltroAtivo);
});

document.getElementById('btn-baixar').addEventListener('click', function() {
    baixarRelatorio();
});

document.getElementById('btn-sync').addEventListener('click', function() {
    atualizarDados();
});

function definirBotaoCarregando(botao, carregando, texto) {
    if (!botao) return;
    botao.disabled = carregando;
    botao.classList.toggle('is-loading', carregando);
    botao.textContent = carregando ? (texto || 'Carregando...') : botao.getAttribute('data-default-label');
}

function destacarMetricas() {
    var info = document.querySelector('.info');
    if (!info) return;
    info.classList.remove('info-loading');
    info.classList.remove('info-refresh');
    void info.offsetWidth;
    info.classList.add('info-refresh');
}

function verificarAuth(resp) {
    if (resp.status === 401) {
        window.location.href = '/login';
        return false;
    }
    return true;
}

function getFormato() {
    var radios = document.querySelectorAll('input[name="formato"]');
    for (var i = 0; i < radios.length; i++) {
        if (radios[i].checked) return radios[i].value;
    }
    return 'csv';
}

function carregarInfo() {
    var info = document.querySelector('.info');
    info.classList.add('info-loading');

    return fetch(API_BASE + '/info')
        .then(function(resp) {
            if (!verificarAuth(resp)) return;
            if (!resp.ok) throw new Error('Erro ao carregar info');
            return resp.json();
        })
        .then(function(data) {
            if (!data) return;
            document.getElementById('total-registros').textContent = data.total_registros;
            document.getElementById('ultima-atualizacao').textContent = data.ultima_atualizacao;
            document.getElementById('proximo-sync').textContent = data.proximo_sync || '--';
            atualizarStatusSync(data.ultimo_sync_status, data.ultimo_sync_status_label);
            destacarMetricas();
        })
        .catch(function() {
            document.getElementById('total-registros').textContent = 'Erro';
            document.getElementById('ultima-atualizacao').textContent = 'Sem conexão';
            document.getElementById('proximo-sync').textContent = '--';
            atualizarStatusSync('erro', 'Falha ao consultar');
            info.classList.remove('info-loading');
            mostrarMensagem('Não foi possível conectar ao servidor.', 'erro');
        });
}

function carregarHistoricoSync() {
    var append = !!arguments[0];
    var offset = append ? _historicoOffset : 0;
    if (!append) _historicoOffset = 0;
    return fetch(API_BASE + '/historico-sync?limit=' + _HISTORICO_LIMIT + '&offset=' + offset)
        .then(function(resp) {
            if (!verificarAuth(resp)) return;
            if (!resp.ok) throw new Error('Erro ao carregar histórico');
            return resp.json();
        })
        .then(function(data) {
            if (!data) return;
            if (append) { appendHistoricoSync(data.historico || []); }
            else { renderizarHistoricoSync(data.historico || []); }
            _historicoOffset = offset + (data.historico || []).length;
            atualizarBotaoVerMais(data.tem_mais);
        })
        .catch(function() {
            if (!append) renderizarHistoricoSync([]);
        });
}

function getFiltrosDatas() {
    var inicio = document.getElementById('filtro-data-inicio');
    var fim    = document.getElementById('filtro-data-fim');
    var params = '';
    if (inicio && inicio.value) params += '&data_inicio=' + inicio.value;
    if (fim    && fim.value)    params += '&data_fim='    + fim.value;
    return params;
}

function baixarRelatorio() {
    var btn = document.getElementById('btn-baixar');
    var formato = getFormato();
    var ext = formato === 'excel' ? '.xlsx' : '.csv';
    var filtros = getFiltrosDatas();

    if (filtros) {
        var inicio = document.getElementById('filtro-data-inicio');
        var fim    = document.getElementById('filtro-data-fim');
        if (inicio && inicio.value && fim && fim.value && inicio.value > fim.value) {
            mostrarMensagem('A data de início não pode ser maior que a data de fim.', 'erro');
            return;
        }
    }

    definirBotaoCarregando(btn, true, 'Gerando...');
    mostrarMensagem(
        filtros ? 'Aguarde, gerando relatório filtrado...' : 'Aguarde, gerando relatório de pedidos Energy...',
        'processando'
    );

    fetch(API_BASE + '/download?formato=' + formato + filtros, { credentials: 'same-origin' })
        .then(function(resp) {
            if (!verificarAuth(resp)) return Promise.reject(new Error('auth'));
            if (!resp.ok) {
                return resp.json().then(function(data) {
                    throw new Error(data.erro || 'Erro ao gerar relatório');
                });
            }
            return resp.blob();
        })
        .then(function(blob) {
            if (!blob) return;
            var url = window.URL.createObjectURL(blob);
            var a = document.createElement('a');
            a.href = url;
            a.download = 'pedidos_energy' + ext;
            a.style.display = 'none';
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
            mostrarMensagem('Relatório gerado e download iniciado.', 'sucesso');
        })
        .catch(function(err) {
            if (err.message !== 'auth') {
                mostrarMensagem(err.message || 'Erro ao gerar o relatório.', 'erro');
            }
        })
        .finally(function() {
            definirBotaoCarregando(btn, false);
        });
}

function atualizarDados() {
    var btn = document.getElementById('btn-sync');
    var t0 = Date.now();
    var timerInterval = _iniciarTimerSync(btn);

    mostrarMensagem('Sincronizando pedidos de compra Energy...', 'processando');

    fetch(API_BASE + '/sync', { method: 'POST' })
        .then(function(resp) {
            if (!verificarAuth(resp)) return;
            if (!resp.ok) {
                return resp.json().then(function(data) {
                    throw new Error(data.erro || 'Erro ao sincronizar');
                });
            }
            return resp.json();
        })
        .then(function(data) {
            if (!data) return;
            mostrarMensagem(_formatarMensagemSync(data, t0), 'sucesso');
            _historicoOffset = 0;
            return Promise.all([carregarInfo(), carregarHistoricoSync(false)]);
        })
        .catch(function(err) {
            mostrarMensagem(err.message || 'Erro ao sincronizar.', 'erro');
        })
        .finally(function() {
            clearInterval(timerInterval);
            definirBotaoCarregando(btn, false);
        });
}

function _iniciarTimerSync(btn) {
    var segundos = 0;
    btn.disabled = true;
    btn.classList.add('is-loading');
    btn.textContent = 'Sincronizando... 0s';
    return setInterval(function() {
        segundos++;
        btn.textContent = 'Sincronizando... ' + segundos + 's';
    }, 1000);
}

function _formatarMensagemSync(data, t0) {
    var duracao = data.duracao_segundos != null
        ? data.duracao_segundos
        : Math.round((Date.now() - t0) / 1000);
    var novos = data.registros_novos != null ? data.registros_novos : null;
    var partes = ['Sincronização concluída em ' + duracao + 's'];
    if (novos != null) {
        partes.push(novos === 0 ? 'nenhum registro novo' : novos + ' registro(s) atualizado(s)');
    }
    return partes.join(' · ');
}

function mostrarMensagem(texto, tipo) {
    var el = document.getElementById('mensagem');
    if (mensagemTimeout) {
        clearTimeout(mensagemTimeout);
        mensagemTimeout = null;
    }

    el.textContent = texto;
    el.className = 'mensagem';
    if (tipo) el.classList.add(tipo);

    if (texto) {
        requestAnimationFrame(function() {
            el.classList.add('visivel');
        });
    }

    if (tipo === 'sucesso' || tipo === 'erro') {
        mensagemTimeout = setTimeout(function() {
            esconderMensagem();
        }, 4200);
    }
}

function esconderMensagem() {
    var el = document.getElementById('mensagem');
    el.classList.remove('visivel');
}

function renderizarHistoricoSync(historico) {
    var container = document.getElementById('historico-sync');
    if (!historico.length) {
        container.innerHTML = '<p class="historico-vazio">Nenhuma atualização registrada até o momento.</p>';
        return;
    }
    container.innerHTML = '<div class="historico-lista">' + _itensHistorico(historico) + '</div>';
}

function appendHistoricoSync(historico) {
    var container = document.getElementById('historico-sync');
    var lista = container.querySelector('.historico-lista');
    if (!lista) { renderizarHistoricoSync(historico); return; }
    lista.insertAdjacentHTML('beforeend', _itensHistorico(historico));
}

function _itensHistorico(historico) {
    return historico.map(function(h) {
        return '<div class="historico-item">' +
            '<span class="historico-data">' + h.executado_em + '</span>' +
            '<span class="historico-quantidade">' + h.registros_novos + ' alterado(s)</span>' +
        '</div>';
    }).join('');
}

function atualizarBotaoVerMais(temMais) {
    var container = document.getElementById('historico-sync');
    var btnExistente = document.getElementById('btn-ver-mais-historico');
    if (btnExistente) btnExistente.remove();
    if (temMais) {
        var btn = document.createElement('button');
        btn.id = 'btn-ver-mais-historico';
        btn.className = 'historico-ver-mais';
        btn.textContent = 'Ver mais';
        btn.addEventListener('click', function() {
            btn.disabled = true;
            btn.textContent = 'Carregando...';
            carregarHistoricoSync(true);
        });
        container.appendChild(btn);
    }
}

function atualizarStatusSync(status, label) {
    var el = document.getElementById('status-sync');
    el.textContent = label || '--';
    el.className = 'status-sync';

    if (status) {
        el.classList.add(status);
    }
}
