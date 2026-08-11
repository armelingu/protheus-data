'use strict';

/* ── Mensagem de contexto via query string ────────────────────────────────── */
(function () {
    var params   = new URLSearchParams(window.location.search);
    var sessao   = params.get('sessao');
    var motivo   = params.get('motivo');
    var erroEl   = document.getElementById('erro');

    var senha    = params.get('senha');

    var mensagem = '';
    if (sessao === 'expirada')       mensagem = 'Sua sessao expirou. Faca login novamente.';
    else if (motivo === 'inativo')   mensagem = 'Sua conta foi desativada. Entre em contato com o TI.';
    else if (senha === 'redefinida') mensagem = 'Senha redefinida com sucesso. Faca login com a nova senha.';

    if (mensagem && erroEl) {
        erroEl.textContent = mensagem;
        erroEl.classList.add('visivel');
        if (senha === 'redefinida') erroEl.classList.add('sucesso');
        // Limpa o param da URL sem recarregar a pagina
        history.replaceState(null, '', '/login');
    }
})();

/* ── Toggle mostrar/ocultar senha ────────────────────────────────────────── */
var SVG_OLHO_ABERTO  = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
var SVG_OLHO_FECHADO = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

document.querySelectorAll('.btn-ver-senha').forEach(function (btn) {
    btn.addEventListener('click', function () {
        var input = document.getElementById(btn.dataset.alvo);
        if (!input) return;
        var visivel = input.type === 'text';
        input.type       = visivel ? 'password' : 'text';
        btn.innerHTML    = visivel ? SVG_OLHO_ABERTO : SVG_OLHO_FECHADO;
        btn.setAttribute('aria-label', visivel ? 'Mostrar senha' : 'Ocultar senha');
    });
});

/* ── Formulario de login ──────────────────────────────────────────────────── */
document.getElementById('loginform').addEventListener('submit', function (e) {
    e.preventDefault();

    var usuario = document.getElementById('usuario').value.trim();
    var senha   = document.getElementById('senha').value;   // senha nao recebe trim()
    var erro    = document.getElementById('erro');
    var btn     = e.target.querySelector('button');

    erro.textContent = '';
    erro.classList.remove('visivel');

    if (!usuario || !senha) {
        erro.textContent = 'Preencha todos os campos.';
        erro.classList.add('visivel');
        return;
    }

    btn.disabled = true;
    btn.classList.add('is-loading');
    btn.dataset.label = btn.textContent;
    btn.textContent   = 'Entrando...';

    fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario: usuario, senha: senha }),
    })
        .then(function (resp) {
            if (!resp.ok) {
                return resp.json().then(function (data) {
                    throw new Error(data.erro || 'Credenciais invalidas');
                });
            }
            return resp.json();
        })
        .then(function (data) {
            window.location.href = data.redirect || '/relatorios';
        })
        .catch(function (err) {
            erro.textContent = err.message || 'Usuario ou senha incorretos.';
            erro.classList.add('visivel');
            btn.disabled   = false;
            btn.classList.remove('is-loading');
            btn.textContent = btn.dataset.label || 'Entrar';
        });
});
