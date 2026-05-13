/**
 * _base.js — lógica compartilhada para todos os relatórios do módulo Financeiro.
 * Cada relatório define window.FINANCEIRO_CONFIG antes de carregar este arquivo.
 *
 * Exemplo de config:
 *   window.FINANCEIRO_CONFIG = {
 *     api_base:       '/api/relatorios/financeiro/nf-entrada',
 *     nome_relatorio: 'NF de Entrada',
 *     nome_arquivo:   'nf_entrada',
 *   };
 */
(function () {
    'use strict';

    var cfg             = window.FINANCEIRO_CONFIG || {};
    var API_BASE        = cfg.api_base       || '';
    var NOME_RELATORIO  = cfg.nome_relatorio  || 'Relatório';
    var NOME_ARQUIVO    = cfg.nome_arquivo    || 'relatorio';
    var mensagemTimeout = null;

    /* ── Auth ──────────────────────────────────────────────────────────────── */
    function verificarAuth(resp) {
        if (resp.status === 401) { window.location.href = '/login'; return false; }
        return true;
    }

    /* ── Mensagens ─────────────────────────────────────────────────────────── */
    function mostrarMensagem(texto, tipo) {
        var el = document.getElementById('mensagem');
        if (!el) return;
        if (mensagemTimeout) { clearTimeout(mensagemTimeout); mensagemTimeout = null; }
        el.textContent = texto;
        el.className   = 'mensagem';
        if (tipo) el.classList.add(tipo);
        if (texto) requestAnimationFrame(function () { el.classList.add('visivel'); });
        if (tipo === 'sucesso' || tipo === 'erro') {
            mensagemTimeout = setTimeout(function () {
                el.classList.remove('visivel');
            }, 4200);
        }
    }

    /* ── Botão carregando ──────────────────────────────────────────────────── */
    function definirBotaoCarregando(btn, carregando, texto) {
        if (!btn) return;
        btn.disabled = carregando;
        btn.classList.toggle('is-loading', carregando);
        btn.textContent = carregando
            ? (texto || 'Carregando...')
            : (btn.getAttribute('data-default-label') || btn.textContent);
    }

    /* ── Status sync ───────────────────────────────────────────────────────── */
    function atualizarStatusSync(status, label) {
        var el = document.getElementById('status-sync');
        if (!el) return;
        el.textContent = label || '--';
        el.className   = 'status-sync';
        if (status) el.classList.add(status);
    }

    function destacarMetricas() {
        var info = document.querySelector('.info');
        if (!info) return;
        info.classList.remove('info-loading', 'info-refresh');
        void info.offsetWidth;
        info.classList.add('info-refresh');
    }

    /* ── Filtros de data ───────────────────────────────────────────────────── */
    function getFiltrosDatas() {
        var inicio = document.getElementById('filtro-data-inicio');
        var fim    = document.getElementById('filtro-data-fim');
        var params = '';
        if (inicio && inicio.value) params += '&data_inicio=' + inicio.value;
        if (fim    && fim.value)    params += '&data_fim='    + fim.value;
        return params;
    }

    function getFormato() {
        var radios = document.querySelectorAll('input[name="formato"]');
        for (var i = 0; i < radios.length; i++) {
            if (radios[i].checked) return radios[i].value;
        }
        return 'csv';
    }

    /* ── Carregar info ─────────────────────────────────────────────────────── */
    function carregarInfo() {
        var info = document.querySelector('.info');
        if (info) info.classList.add('info-loading');

        fetch(API_BASE + '/info')
            .then(function (resp) {
                if (!verificarAuth(resp)) return null;
                if (!resp.ok) throw new Error('Erro ao carregar info');
                return resp.json();
            })
            .then(function (data) {
                if (!data) return;
                document.getElementById('total-registros').textContent    = data.total_registros;
                document.getElementById('ultima-atualizacao').textContent = data.ultima_atualizacao;
                document.getElementById('proximo-sync').textContent       = data.proximo_sync || '--';
                atualizarStatusSync(data.ultimo_sync_status, data.ultimo_sync_status_label);
                destacarMetricas();
            })
            .catch(function () {
                document.getElementById('total-registros').textContent    = 'Erro';
                document.getElementById('ultima-atualizacao').textContent = 'Sem conexão';
                document.getElementById('proximo-sync').textContent       = '--';
                atualizarStatusSync('erro', 'Falha ao consultar');
                if (info) info.classList.remove('info-loading');
                mostrarMensagem('Não foi possível conectar ao servidor.', 'erro');
            });
    }

    /* ── Histórico sync ────────────────────────────────────────────────────── */
    function renderizarHistoricoSync(historico) {
        var container = document.getElementById('historico-sync');
        if (!container) return;
        if (!historico.length) {
            container.innerHTML = '<p class="historico-vazio">Nenhuma atualização registrada até o momento.</p>';
            return;
        }
        var html = '<div class="historico-lista">';
        for (var i = 0; i < historico.length; i++) {
            html += '<div class="historico-item">' +
                '<span class="historico-data">'        + historico[i].executado_em    + '</span>' +
                '<span class="historico-quantidade">'  + historico[i].registros_novos + ' alterado(s)</span>' +
                '</div>';
        }
        html += '</div>';
        container.innerHTML = html;
    }

    function carregarHistoricoSync() {
        fetch(API_BASE + '/historico-sync')
            .then(function (resp) {
                if (!verificarAuth(resp)) return null;
                if (!resp.ok) throw new Error('Erro');
                return resp.json();
            })
            .then(function (data) {
                if (data) renderizarHistoricoSync(data.historico || []);
            })
            .catch(function () { renderizarHistoricoSync([]); });
    }

    /* ── Download ──────────────────────────────────────────────────────────── */
    function baixarRelatorio() {
        var btn     = document.getElementById('btn-baixar');
        var formato = getFormato();
        var ext     = formato === 'excel' ? '.xlsx' : '.csv';
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
            filtros
                ? 'Aguarde, gerando relatório filtrado...'
                : 'Aguarde, gerando ' + NOME_RELATORIO + '...',
            'processando'
        );

        fetch(API_BASE + '/download?formato=' + formato + filtros)
            .then(function (resp) {
                if (!verificarAuth(resp)) return null;
                if (!resp.ok) {
                    return resp.json().then(function (d) {
                        throw new Error(d.erro || 'Erro ao gerar relatório');
                    });
                }
                return resp.blob();
            })
            .then(function (blob) {
                if (!blob) return;
                var url = window.URL.createObjectURL(blob);
                var a   = document.createElement('a');
                a.href  = url;
                a.download = NOME_ARQUIVO + ext;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                window.URL.revokeObjectURL(url);
                mostrarMensagem('Relatório gerado e download iniciado.', 'sucesso');
            })
            .catch(function (err) {
                mostrarMensagem(err.message || 'Erro ao gerar o relatório.', 'erro');
            })
            .finally(function () { definirBotaoCarregando(btn, false); });
    }

    /* ── Sync manual ───────────────────────────────────────────────────────── */
    function atualizarDados() {
        var btn = document.getElementById('btn-sync');
        definirBotaoCarregando(btn, true, 'Atualizando...');
        mostrarMensagem('Sincronizando ' + NOME_RELATORIO + '...', 'processando');

        fetch(API_BASE + '/sync', { method: 'POST' })
            .then(function (resp) {
                if (!verificarAuth(resp)) return null;
                if (!resp.ok) {
                    return resp.json().then(function (d) {
                        throw new Error(d.erro || 'Erro ao sincronizar');
                    });
                }
                return resp.json();
            })
            .then(function (data) {
                if (!data) return;
                mostrarMensagem(data.mensagem, 'sucesso');
                carregarInfo();
                carregarHistoricoSync();
            })
            .catch(function (err) {
                mostrarMensagem(err.message || 'Erro ao sincronizar.', 'erro');
            })
            .finally(function () { definirBotaoCarregando(btn, false); });
    }

    /* ── Init ──────────────────────────────────────────────────────────────── */
    document.addEventListener('DOMContentLoaded', function () {
        var botoes = [
            document.getElementById('btn-baixar'),
            document.getElementById('btn-sync'),
        ];
        botoes.forEach(function (b) {
            if (b && !b.getAttribute('data-default-label')) {
                b.setAttribute('data-default-label', b.textContent);
            }
        });

        var btnLimpar = document.getElementById('btn-limpar-filtro');
        if (btnLimpar) {
            btnLimpar.addEventListener('click', function () {
                var ini = document.getElementById('filtro-data-inicio');
                var fim = document.getElementById('filtro-data-fim');
                if (ini) ini.value = '';
                if (fim) fim.value = '';
                var ctrl = document.querySelector('.painel-controles');
                if (ctrl) ctrl.classList.remove('filtro-ativo');
            });
        }

        ['filtro-data-inicio', 'filtro-data-fim'].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.addEventListener('change', function () {
                var ini   = document.getElementById('filtro-data-inicio');
                var fim   = document.getElementById('filtro-data-fim');
                var ativo = (ini && ini.value) || (fim && fim.value);
                var ctrl  = document.querySelector('.painel-controles');
                if (ctrl) ctrl.classList.toggle('filtro-ativo', !!ativo);
            });
        });

        var btnBaixar = document.getElementById('btn-baixar');
        var btnSync   = document.getElementById('btn-sync');
        if (btnBaixar) btnBaixar.addEventListener('click', baixarRelatorio);
        if (btnSync)   btnSync.addEventListener('click', atualizarDados);

        carregarInfo();
        carregarHistoricoSync();
    });
}());
