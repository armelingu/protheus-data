var API_BASE = '/api/relatorios/estoque/saldos';
var mensagemTimeout = null;

document.addEventListener('DOMContentLoaded', function() {
    carregarInfo();
    carregarHistoricoSync();

    var botoes = [
        document.getElementById('btn-baixar'),
        document.getElementById('btn-sync')
    ];

    for (var i = 0; i < botoes.length; i++) {
        if (botoes[i] && !botoes[i].getAttribute('data-default-label')) {
            botoes[i].setAttribute('data-default-label', botoes[i].textContent);
        }
    }
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

    fetch(API_BASE + '/info')
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
    fetch(API_BASE + '/historico-sync')
        .then(function(resp) {
            if (!verificarAuth(resp)) return;
            if (!resp.ok) throw new Error('Erro ao carregar histórico');
            return resp.json();
        })
        .then(function(data) {
            if (!data) return;
            renderizarHistoricoSync(data.historico || []);
        })
        .catch(function() {
            renderizarHistoricoSync([]);
        });
}

function baixarRelatorio() {
    var btn = document.getElementById('btn-baixar');
    var formato = getFormato();
    var ext = formato === 'excel' ? '.xlsx' : '.csv';

    definirBotaoCarregando(btn, true, 'Gerando...');
    mostrarMensagem('Aguarde, gerando relatório de estoque...', 'processando');

    fetch(API_BASE + '/download?formato=' + formato)
        .then(function(resp) {
            if (!verificarAuth(resp)) return;
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
            a.download = 'saldo_estoque' + ext;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);

            mostrarMensagem('Relatório gerado e download iniciado.', 'sucesso');
        })
        .catch(function(err) {
            mostrarMensagem(err.message || 'Erro ao gerar o relatório.', 'erro');
        })
        .finally(function() {
            definirBotaoCarregando(btn, false);
        });
}

function atualizarDados() {
    var btn = document.getElementById('btn-sync');

    definirBotaoCarregando(btn, true, 'Atualizando...');
    mostrarMensagem('Sincronizando posição atual do estoque...', 'processando');

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
            mostrarMensagem(data.mensagem, 'sucesso');
            carregarInfo();
            carregarHistoricoSync();
        })
        .catch(function(err) {
            mostrarMensagem(err.message || 'Erro ao sincronizar.', 'erro');
        })
        .finally(function() {
            definirBotaoCarregando(btn, false);
        });
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

    var html = '<div class="historico-lista">';

    for (var i = 0; i < historico.length; i++) {
        html += '<div class="historico-item">' +
            '<span class="historico-data">' + historico[i].executado_em + '</span>' +
            '<span class="historico-quantidade">' + historico[i].registros_novos + ' alterado(s)</span>' +
        '</div>';
    }

    html += '</div>';
    container.innerHTML = html;
}

function atualizarStatusSync(status, label) {
    var el = document.getElementById('status-sync');
    el.textContent = label || '--';
    el.className = 'status-sync';

    if (status) {
        el.classList.add(status);
    }
}
