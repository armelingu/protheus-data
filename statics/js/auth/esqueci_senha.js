'use strict';

const form        = document.getElementById('esqueci-form');
const btnEnviar   = document.getElementById('btn-enviar');
const erroEl      = document.getElementById('erro');
const estadoForm  = document.getElementById('estado-form');
const estadoSuc   = document.getElementById('estado-sucesso');

function setBotaoCarregando(ativo) {
    btnEnviar.disabled    = ativo;
    btnEnviar.textContent = ativo ? 'Enviando...' : 'Enviar link de recuperacao';
}

function mostrarErro(msg) {
    erroEl.textContent = msg;
    erroEl.style.display = msg ? 'block' : 'none';
}

form.addEventListener('submit', async function (e) {
    e.preventDefault();
    mostrarErro('');

    const email = document.getElementById('email').value.trim();
    if (!email) {
        mostrarErro('Informe o e-mail.');
        return;
    }

    setBotaoCarregando(true);

    try {
        const resp = await fetch('/api/esqueci-senha', {
            method:  'POST',
            headers: { 'Content-Type': 'application/json' },
            body:    JSON.stringify({ email }),
        });

        const dados = await resp.json();

        if (!resp.ok) {
            mostrarErro(dados.erro || 'Erro ao processar a solicitacao.');
            setBotaoCarregando(false);
            return;
        }

        estadoForm.style.display = 'none';
        estadoSuc.style.display  = 'block';

    } catch (_) {
        mostrarErro('Erro de conexao. Tente novamente.');
        setBotaoCarregando(false);
    }
});
