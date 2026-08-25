(function (global) {
    global.persistirPaineisAdmin = function (prefixo) {
        prefixo = prefixo || 'admin.panel.';
        document.querySelectorAll('details.admin-panel-collapsible').forEach(function (painel) {
            var id = painel.getAttribute('data-panel');
            if (!id) return;
            var chave = prefixo + id;
            try {
                var salvo = window.localStorage.getItem(chave);
                if (salvo === 'closed') painel.open = false;
                if (salvo === 'open') painel.open = true;
            } catch (err) {}
            painel.addEventListener('toggle', function () {
                try {
                    window.localStorage.setItem(chave, painel.open ? 'open' : 'closed');
                } catch (err2) {}
            });
        });
    };

    global.renderizarPaginacaoAdmin = function (container, paginaAtual, total, porPagina, rotulo) {
        if (!container) return;
        rotulo = rotulo || 'itens';
        var totalPaginas = Math.ceil(total / porPagina) || 1;
        if (total <= porPagina) {
            container.innerHTML = '';
            return;
        }

        var html = '<div class="audit-pag-inner">';
        html += '<button type="button" class="audit-pag-btn" data-pag="prev"'
              + (paginaAtual <= 1 ? ' disabled' : '') + '>Anterior</button>';

        var inicio = Math.max(1, paginaAtual - 2);
        var fim = Math.min(totalPaginas, paginaAtual + 2);
        if (inicio > 1) {
            html += '<button type="button" class="audit-pag-num" data-pag="1">1</button>';
            if (inicio > 2) html += '<span class="audit-pag-reticencias">...</span>';
        }
        for (var p = inicio; p <= fim; p++) {
            var ativo = p === paginaAtual ? ' ativo' : '';
            html += '<button type="button" class="audit-pag-num' + ativo + '" data-pag="' + p + '">' + p + '</button>';
        }
        if (fim < totalPaginas) {
            if (fim < totalPaginas - 1) html += '<span class="audit-pag-reticencias">...</span>';
            html += '<button type="button" class="audit-pag-num" data-pag="' + totalPaginas + '">' + totalPaginas + '</button>';
        }
        html += '<button type="button" class="audit-pag-btn" data-pag="next"'
              + (paginaAtual >= totalPaginas ? ' disabled' : '') + '>Próxima</button>';
        html += '</div>';

        var inicioReg = (paginaAtual - 1) * porPagina + 1;
        var fimReg = Math.min(paginaAtual * porPagina, total);
        html += '<p class="audit-pag-info">Exibindo ' + inicioReg + '-' + fimReg + ' de ' + total + ' ' + rotulo + '</p>';
        container.innerHTML = html;
    };

    global.lerPaginaPaginacao = function (botao, paginaAtual) {
        var val = botao.getAttribute('data-pag');
        if (val === 'prev') return paginaAtual - 1;
        if (val === 'next') return paginaAtual + 1;
        return parseInt(val, 10) || 1;
    };
})(window);
