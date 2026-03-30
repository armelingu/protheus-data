document.addEventListener('DOMContentLoaded', function() {
    var body = document.body;
    var btnLogout = document.querySelector('[data-logout]');
    var isTransitioning = false;

    function deveIgnorarClique(evento, link) {
        if (!link || isTransitioning) {
            return true;
        }

        if (link.hasAttribute('download') || link.dataset.noPageTransition !== undefined) {
            return true;
        }

        if (link.target && link.target !== '_self') {
            return true;
        }

        if (
            evento.metaKey ||
            evento.ctrlKey ||
            evento.shiftKey ||
            evento.altKey ||
            evento.button !== 0
        ) {
            return true;
        }

        var href = link.getAttribute('href');
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) {
            return true;
        }

        var destino = new URL(link.href, window.location.origin);
        if (destino.origin !== window.location.origin) {
            return true;
        }

        var origem = window.location.pathname + window.location.search;
        var proximo = destino.pathname + destino.search;
        return origem === proximo;
    }

    function iniciarTransicao(texto) {
        if (isTransitioning) {
            return false;
        }

        isTransitioning = true;
        body.classList.add('is-page-transitioning');
        return true;
    }

    window.addEventListener('pageshow', function() {
        body.classList.remove('is-page-transitioning');
        isTransitioning = false;
    });

    document.querySelectorAll('a[href]').forEach(function(link) {
        link.addEventListener('click', function(evento) {
            if (deveIgnorarClique(evento, link)) {
                return;
            }

            evento.preventDefault();

            if (!iniciarTransicao('Abrindo tela')) {
                return;
            }

            window.setTimeout(function() {
                window.location.href = link.href;
            }, 95);
        });
    });

    if (!btnLogout) {
        return;
    }

    btnLogout.addEventListener('click', function() {
        iniciarTransicao('Saindo');
        fetch('/api/logout', { method: 'POST' })
            .then(function() {
                window.location.href = '/login';
            })
            .catch(function() {
                body.classList.remove('is-page-transitioning');
                isTransitioning = false;
            });
    });
});
