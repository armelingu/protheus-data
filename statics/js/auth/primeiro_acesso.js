'use strict';

/* ── CSRF ─────────────────────────────────────────────────────────────────── */
function csrfToken() {
    return (document.querySelector('meta[name="csrf-token"]') || {}).content || '';
}

/* ── Botão loading state ──────────────────────────────────────────────────── */
function setBotaoCarregando(btn, carregando) {
    if (carregando) {
        btn.disabled = true;
        btn.dataset.label = btn.textContent;
        btn.textContent = 'Salvando...';
    } else {
        btn.disabled = false;
        btn.textContent = btn.dataset.label || 'Salvar nova senha';
    }
}

/* ── Formulário de troca de senha ─────────────────────────────────────────── */
document.getElementById('primeiro-acesso-form').addEventListener('submit', function (event) {
    event.preventDefault();

    var erro  = document.getElementById('erro');
    var botao = document.getElementById('btn-salvar');

    erro.textContent = '';

    var payload = {
        senha_atual:     event.target.senha_atual.value,       // sem trim — senha pode ter espaço
        nova_senha:      event.target.nova_senha.value,
        confirmar_senha: event.target.confirmar_senha.value,
    };

    /* Validação mínima no cliente para feedback imediato */
    if (!payload.senha_atual || !payload.nova_senha || !payload.confirmar_senha) {
        erro.textContent = 'Preencha todos os campos.';
        return;
    }
    if (payload.nova_senha !== payload.confirmar_senha) {
        erro.textContent = 'A confirmacao da senha nao confere.';
        return;
    }
    if (payload.nova_senha.length < 10) {
        erro.textContent = 'A nova senha deve ter pelo menos 10 caracteres.';
        return;
    }
    if (!/\d/.test(payload.nova_senha)) {
        erro.textContent = 'A nova senha deve conter pelo menos um numero.';
        return;
    }

    setBotaoCarregando(botao, true);

    fetch('/api/primeiro-acesso', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRF-Token': csrfToken(),
        },
        body: JSON.stringify(payload),
    })
        .then(function (resp) {
            return resp.json().then(function (data) {
                if (!resp.ok) throw new Error(data.erro || 'Falha ao atualizar senha.');
                return data;
            });
        })
        .then(function (data) {
            window.location.href = data.redirect || '/relatorios';
        })
        .catch(function (err) {
            erro.textContent = err.message || 'Falha ao atualizar senha.';
            setBotaoCarregando(botao, false);
        });
});

/* ── Link de logout ───────────────────────────────────────────────────────── */
var linkLogout = document.getElementById('link-logout');
if (linkLogout) {
    linkLogout.addEventListener('click', function (e) {
        e.preventDefault();
        fetch('/api/logout', {
            method: 'POST',
            headers: { 'X-CSRF-Token': csrfToken() },
        }).finally(function () {
            window.location.href = '/login';
        });
    });
}
