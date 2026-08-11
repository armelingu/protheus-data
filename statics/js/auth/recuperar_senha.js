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

const form          = document.getElementById('recuperar-form');
const btnSalvar     = document.getElementById('btn-salvar');
const erroEl        = document.getElementById('erro');
const tokenInput    = document.getElementById('token');

function setBotaoCarregando(ativo) {
    btnSalvar.disabled    = ativo;
    btnSalvar.textContent = ativo ? 'Salvando...' : 'Salvar nova senha';
}

function mostrarErro(msg) {
    erroEl.textContent   = msg;
    erroEl.style.display = msg ? 'block' : 'none';
}

form.addEventListener('submit', async function (e) {
    e.preventDefault();
    mostrarErro('');

    const nova_senha     = document.getElementById('nova_senha').value;
    const confirmar_senha = document.getElementById('confirmar_senha').value;
    const token          = tokenInput.value;

    if (!nova_senha || !confirmar_senha) {
        mostrarErro('Preencha todos os campos.');
        return;
    }
    if (nova_senha !== confirmar_senha) {
        mostrarErro('As senhas nao conferem.');
        return;
    }
    if (nova_senha.length < 10) {
        mostrarErro('A senha deve ter pelo menos 10 caracteres.');
        return;
    }
    if (!/\d/.test(nova_senha)) {
        mostrarErro('A senha deve conter pelo menos um numero.');
        return;
    }

    setBotaoCarregando(true);

    try {
        const resp = await fetch('/api/recuperar-senha', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ token, nova_senha, confirmar_senha }),
        });

        const dados = await resp.json();

        if (!resp.ok) {
            mostrarErro(dados.erro || 'Erro ao redefinir a senha.');
            setBotaoCarregando(false);
            return;
        }

        window.location.href = dados.redirect || '/login?senha=redefinida';

    } catch (_) {
        mostrarErro('Erro de conexao. Tente novamente.');
        setBotaoCarregando(false);
    }
});
