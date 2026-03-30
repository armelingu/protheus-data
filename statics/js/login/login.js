document.getElementById('loginform').addEventListener('submit', function(e) {
    e.preventDefault();

    var usuario = document.getElementById('usuario').value.trim();
    var senha = document.getElementById('senha').value.trim();
    var erro = document.getElementById('erro');
    var btn = e.target.querySelector('button');

    erro.textContent = '';
    erro.classList.remove('visivel');

    if (!usuario || !senha) {
        erro.textContent = 'Preencha todos os campos.';
        erro.classList.add('visivel');
        return;
    }

    btn.disabled = true;
    btn.classList.add('is-loading');
    btn.setAttribute('data-default-label', btn.textContent);
    btn.textContent = 'Entrando...';

    fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ usuario: usuario, senha: senha })
    })
    .then(function(resp) {
        if (!resp.ok) {
            return resp.json().then(function(data) {
                throw new Error(data.erro || 'Credenciais inválidas');
            });
        }
        return resp.json();
    })
    .then(function(data) {
        window.location.href = data.redirect || '/relatorios';
    })
    .catch(function(err) {
        erro.textContent = err.message || 'Usuário ou senha incorretos.';
        erro.classList.add('visivel');
        btn.disabled = false;
        btn.classList.remove('is-loading');
        btn.textContent = btn.getAttribute('data-default-label') || 'Entrar';
    });
});
