'use strict';

/* ── Toggle mostrar/ocultar senha ────────────────────────────────────────── */
document.querySelectorAll('.btn-ver-senha').forEach(function (btn) {
    btn.addEventListener('click', function () {
        var input = document.getElementById(btn.dataset.alvo);
        if (!input) return;
        var visivel = input.type === 'text';
        input.type = visivel ? 'password' : 'text';
        btn.textContent = visivel ? 'ver' : 'ocultar';
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
