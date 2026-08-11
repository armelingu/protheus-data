'use strict';

/* ── Toggle mostrar/ocultar senha ────────────────────────────────────────── */
var SVG_OLHO_ABERTO  = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>';
var SVG_OLHO_FECHADO = '<svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>';

document.querySelectorAll('.btn-ver-senha').forEach(function (btn) {
    btn.addEventListener('click', function () {
        var input = document.getElementById(btn.dataset.alvo);
        if (!input) return;
        var visivel = input.type === 'text';
        input.type    = visivel ? 'password' : 'text';
        btn.innerHTML = visivel ? SVG_OLHO_ABERTO : SVG_OLHO_FECHADO;
        btn.setAttribute('aria-label', visivel ? 'Mostrar senha' : 'Ocultar senha');
    });
});

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
