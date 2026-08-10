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
