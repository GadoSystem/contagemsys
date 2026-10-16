'use strict';
(() => {
  const $ = (s) => document.querySelector(s);
  const form = $('#form'), cpfInput = $('#cpf'), senhaInput = $('#senha'), entrar = $('#entrar'), alerta = $('#alerta');

  // Sessao ainda valida: vai direto ao painel.
  try { if (localStorage.getItem('contagem_token')) location.replace('/painel'); } catch { /* sem storage */ }

  const ICONE = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="12" cy="12" r="10"/><path d="M12 8v4M12 16h.01"/></svg>';

  function mostrarAlerta(texto, tipo = 'error', campo = null) {
    alerta.className = `login-alert ${tipo}`;
    alerta.innerHTML = ICONE;
    const span = document.createElement('span');
    span.textContent = texto;
    alerta.appendChild(span);
    cpfInput.setAttribute('aria-invalid', String(campo === cpfInput));
    senhaInput.setAttribute('aria-invalid', String(campo === senhaInput));
    if (campo) campo.focus();
  }
  function limparAlerta() {
    alerta.className = 'login-alert hidden';
    alerta.textContent = '';
    cpfInput.removeAttribute('aria-invalid');
    senhaInput.removeAttribute('aria-invalid');
  }

  function mascara(d) {
    if (d.length > 9) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
    if (d.length > 6) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6)}`;
    if (d.length > 3) return `${d.slice(0, 3)}.${d.slice(3)}`;
    return d;
  }
  // Mesma regra do servidor e do cadastro do Rebano: 11 digitos e verificadores.
  function cpfValido(d) {
    if (!/^\d{11}$/.test(d) || /^(\d)\1{10}$/.test(d)) return false;
    for (const n of [9, 10]) {
      let soma = 0;
      for (let i = 0; i < n; i++) soma += Number(d[i]) * (n + 1 - i);
      const resto = soma % 11;
      if (Number(d[n]) !== (resto < 2 ? 0 : 11 - resto)) return false;
    }
    return true;
  }

  cpfInput.addEventListener('input', () => {
    cpfInput.value = mascara(cpfInput.value.replace(/\D/g, '').slice(0, 11));
    if (cpfInput.getAttribute('aria-invalid') === 'true') limparAlerta();
  });
  senhaInput.addEventListener('input', () => { if (senhaInput.getAttribute('aria-invalid') === 'true') limparAlerta(); });

  $('#toggleSenha').addEventListener('click', (e) => {
    const visivel = senhaInput.type === 'text';
    senhaInput.type = visivel ? 'password' : 'text';
    e.currentTarget.setAttribute('aria-pressed', String(!visivel));
    e.currentTarget.setAttribute('aria-label', visivel ? 'Mostrar senha' : 'Ocultar senha');
  });

  function ocupado(sim) {
    entrar.disabled = sim;
    entrar.innerHTML = sim ? '<span class="spinner" aria-hidden="true"></span><span>Entrando…</span>' : 'Entrar';
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    limparAlerta();
    const digitos = cpfInput.value.replace(/\D/g, '');
    const senha = senhaInput.value;
    if (!digitos) return mostrarAlerta('Informe o CPF.', 'error', cpfInput);
    if (!senha) return mostrarAlerta('Informe a senha.', 'error', senhaInput);
    if (digitos.length !== 11) return mostrarAlerta('O CPF precisa ter 11 dígitos.', 'error', cpfInput);
    if (!cpfValido(digitos)) return mostrarAlerta('CPF inválido. Confira os números digitados.', 'error', cpfInput);

    ocupado(true);
    try {
      let r;
      try {
        r = await fetch('/api/auth/login', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ cpf: mascara(digitos), senha }),
        });
      } catch {
        return mostrarAlerta('Não foi possível conectar ao ContagemSys. Verifique a rede e tente novamente.', 'warn');
      }
      const data = await r.json().catch(() => ({}));
      if (r.status === 401) { senhaInput.value = ''; return mostrarAlerta('CPF ou senha incorretos.', 'error', senhaInput); }
      if (r.status === 400) return mostrarAlerta(data.detail || 'Confira o CPF e a senha.', 'error', cpfInput);
      if (r.status === 502 || r.status === 503 || r.status === 504) {
        return mostrarAlerta('O Rebano está fora do ar no momento. Tente novamente em instantes.', 'warn');
      }
      if (!r.ok || !data.token) return mostrarAlerta('Não foi possível entrar agora. Tente novamente.', 'warn');
      try {
        localStorage.setItem('contagem_token', data.token);
        localStorage.setItem('contagem_usuario', JSON.stringify(data.usuario || {}));
      } catch {
        return mostrarAlerta('O navegador bloqueou o armazenamento da sessão. Desative o modo restrito e tente de novo.', 'warn');
      }
      location.href = '/painel';
    } finally {
      ocupado(false);
    }
  });

  cpfInput.focus();
})();
