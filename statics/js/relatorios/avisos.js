document.addEventListener('DOMContentLoaded', function () {
    var overlay = document.getElementById('aviso-melhoria-overlay');
    if (!overlay) {
        return;
    }

    var kicker = overlay.querySelector('.aviso-kicker');
    var versaoEl = overlay.querySelector('.aviso-versao');
    var relatorioEl = overlay.querySelector('.aviso-relatorio');
    var tituloEl = overlay.querySelector('.aviso-titulo');
    var mensagemEl = overlay.querySelector('.aviso-mensagem');
    var botao = document.getElementById('aviso-ok');
    var fila = [];
    var atual = null;
    var enviando = false;

    function fechar() {
        overlay.hidden = true;
        document.body.style.overflow = '';
        atual = null;
    }

    function exibir(aviso) {
        atual = aviso;
        kicker.textContent = 'Atualização de relatório';
        if (aviso.versao) {
            versaoEl.textContent = 'Versão ' + aviso.versao;
            versaoEl.hidden = false;
        } else {
            versaoEl.textContent = '';
            versaoEl.hidden = true;
        }
        relatorioEl.textContent = [aviso.modulo_titulo, aviso.relatorio_titulo]
            .filter(Boolean)
            .join(' / ');
        tituloEl.textContent = aviso.titulo || '';
        mensagemEl.textContent = aviso.mensagem || '';
        overlay.hidden = false;
        document.body.style.overflow = 'hidden';
        botao.focus();
    }

    function proximo() {
        if (!fila.length) {
            fechar();
            return;
        }
        exibir(fila.shift());
    }

    function marcarLido() {
        if (!atual || enviando) {
            return;
        }
        enviando = true;
        botao.disabled = true;
        fetch('/api/avisos/' + atual.id + '/lido', { method: 'POST' })
            .catch(function () {
                return null;
            })
            .finally(function () {
                enviando = false;
                botao.disabled = false;
                proximo();
            });
    }

    botao.addEventListener('click', marcarLido);

    fetch('/api/avisos/pendentes')
        .then(function (resp) {
            if (!resp.ok) {
                return null;
            }
            return resp.json();
        })
        .then(function (dados) {
            fila = (dados && dados.avisos) || [];
            proximo();
        })
        .catch(function () {
            return null;
        });
});
