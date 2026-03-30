document.getElementById('primeiro-acesso-form').addEventListener('submit', function(event) {
    event.preventDefault();

    var erro = document.getElementById('erro');
    var botao = event.target.querySelector('button');
    var payload = {
        senha_atual: event.target.senha_atual.value.trim(),
        nova_senha: event.target.nova_senha.value.trim(),
        confirmar_senha: event.target.confirmar_senha.value.trim()
    };

    erro.textContent = '';
    botao.disabled = true;

    fetch('/api/primeiro-acesso', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
    })
        .then(function(resp) {
            return resp.json().then(function(data) {
                if (!resp.ok) {
                    throw new Error(data.erro || 'Falha ao atualizar senha.');
                }
                return data;
            });
        })
        .then(function(data) {
            window.location.href = data.redirect || '/relatorios';
        })
        .catch(function(err) {
            erro.textContent = err.message || 'Falha ao atualizar senha.';
            botao.disabled = false;
        });
});
