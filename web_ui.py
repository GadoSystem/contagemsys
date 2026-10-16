from __future__ import annotations

# Login e painel do usuario: HTML aqui; estilos, scripts e logo em static/
# (servidos pelo proprio FastAPI, sem CDN nem fontes externas).

LOGIN_HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#07100c">
<title>Entrar · ContagemSys</title>
<link rel="icon" href="/static/logo-rebano.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/app.css">
</head>
<body class="login-page">
<main class="login-card">
  <div class="login-brand">
    <img src="/static/logo-rebano.svg" alt="Rebano" width="68" height="68">
    <div><h1>ContagemSys</h1><p>Monitoramento de rebanhos · Rebano</p></div>
  </div>
  <p class="login-intro">Entre com o CPF e a senha da sua conta do Rebano.</p>
  <form id="form" novalidate>
    <label class="field" for="cpf">
      <span class="field-label">CPF</span>
      <input class="field-input tabular" id="cpf" name="cpf" inputmode="numeric" autocomplete="username"
             placeholder="000.000.000-00" maxlength="14" aria-describedby="alerta">
    </label>
    <label class="field" for="senha">
      <span class="field-label">Senha</span>
      <span class="password-wrap">
        <input class="field-input" id="senha" name="senha" type="password" autocomplete="current-password" aria-describedby="alerta">
        <button class="btn btn-ghost btn-icon password-toggle" id="toggleSenha" type="button" aria-label="Mostrar senha" aria-pressed="false">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M1 12s4-7 11-7 11 7 11 7-4 7-11 7S1 12 1 12z"/><circle cx="12" cy="12" r="3"/></svg>
        </button>
      </span>
    </label>
    <button class="btn btn-primary login-submit" id="entrar" type="submit">Entrar</button>
    <div class="login-alert hidden" id="alerta" role="alert" aria-live="assertive"></div>
  </form>
  <div class="login-foot"><span>A senha é verificada pelo Rebano.</span><a href="/admin">Administração</a></div>
</main>
<script src="/static/login.js"></script>
</body>
</html>'''

PANEL_HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="theme-color" content="#07100c">
<title>Painel · ContagemSys</title>
<link rel="icon" href="/static/logo-rebano.svg" type="image/svg+xml">
<link rel="stylesheet" href="/static/app.css">
</head>
<body>
<div class="app">
  <header class="topbar">
    <div class="brand">
      <img src="/static/logo-rebano.svg" alt="Rebano" width="44" height="44">
      <div><span class="brand-name">ContagemSys</span><span class="brand-sub">Central de monitoramento</span></div>
    </div>
    <div class="topbar-spacer"></div>
    <div class="clock tabular" aria-live="off"><div class="clock-time" id="clockTime">--:--:--</div><div class="clock-date" id="clockDate"></div></div>
    <div class="user-chip"><span class="avatar" id="avatar" aria-hidden="true"></span><span class="user-name" id="userName"></span></div>
    <div class="topbar-actions">
      <button class="btn" id="fullscreen" type="button" aria-pressed="false" title="Tela cheia">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/></svg><span class="btn-label">Tela cheia</span>
      </button>
      <button class="btn btn-ghost" id="logout" type="button" title="Sair">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="M16 17l5-5-5-5M21 12H9"/></svg><span class="btn-label">Sair</span>
      </button>
    </div>
  </header>

  <main class="main">
    <nav class="farm-tabs" id="farmTabs" role="tablist" aria-label="Fazendas"></nav>

    <section class="summary" aria-label="Resumo da seleção">
      <div class="stat">
        <div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg></div>
        <div><div class="stat-label">Câmeras online</div><div class="stat-value tabular" id="sumOnline">—</div></div>
      </div>
      <div class="stat">
        <div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19V5M4 19h16"/><path d="M8 15l4-4 3 3 5-6"/></svg></div>
        <div><div class="stat-label">Total contado</div><div class="stat-value tabular" id="sumTotal">—</div></div>
        <span class="stat-note">sessão atual</span>
      </div>
      <div class="stat">
        <div class="stat-icon"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 14l-5-5 5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/></svg></div>
        <div><div class="stat-label">Retornos</div><div class="stat-value tabular" id="sumRetornos">—</div></div>
        <span class="stat-note">sessão atual</span>
      </div>
    </section>

    <div class="notice hidden" id="syncNotice" role="status">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>
      <span>Não foi possível sincronizar as fazendas com o Rebano. Saia e entre novamente para atualizar o agrupamento.</span>
    </div>

    <div class="grid-wrap" id="gridWrap">
      <div class="cam-grid" id="loading" aria-hidden="true" style="--cols:2"><div class="skeleton"></div><div class="skeleton"></div></div>
      <div class="cam-grid" id="grid" aria-label="Câmeras"></div>
      <div class="empty-state hidden" id="emptyState">
        <div>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>
          <h2>Nenhuma câmera vinculada</h2>
          <p>Nenhuma câmera foi vinculada a esta conta. Solicite o vínculo ao administrador do ContagemSys.</p>
        </div>
      </div>
      <div class="empty-state hidden" id="loadError" role="alert">
        <div>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>
          <h2>Não foi possível carregar as câmeras</h2>
          <p>Verifique a conexão com o ContagemSys. O painel tenta novamente sozinho.</p>
          <p><button class="btn" id="retry" type="button">Tentar agora</button></p>
        </div>
      </div>
    </div>
  </main>
</div>

<section class="viewer hidden" id="viewer" role="dialog" aria-modal="true" aria-labelledby="vTitle">
  <header class="viewer-head">
    <button class="btn btn-ghost" id="vClose" type="button" title="Voltar à grade (Esc)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg><span class="btn-label">Voltar</span>
    </button>
    <div class="viewer-title"><h2 id="vTitle"></h2><p id="vSub"></p></div>
    <span class="badge connecting" id="vBadge">Conectando</span>
    <div class="topbar-spacer"></div>
    <button class="btn btn-icon" id="vPrev" type="button" aria-label="Câmera anterior" title="Câmera anterior (←)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>
    </button>
    <button class="btn btn-icon" id="vNext" type="button" aria-label="Próxima câmera" title="Próxima câmera (→)">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>
    </button>
  </header>
  <div class="viewer-body">
    <div class="viewer-video" id="vVideo">
      <div class="no-signal connecting" id="vNoSignal"></div>
      <div class="tile-bottom">
        <div class="tile-metrics"><span class="metric-chip tabular" id="vTotal"></span><span class="metric-chip tabular" id="vRetornos"></span></div>
        <span class="tile-time tabular" id="vTime"></span>
      </div>
    </div>
    <aside class="viewer-side">
      <section><h3 class="section-title">Agora</h3><div class="cards" id="vCards"></div></section>
      <section><h3 class="section-title">Histórico</h3><div class="cards" id="vStats"></div></section>
      <section><h3 class="section-title">Eventos recentes</h3><ul class="events" id="vEvents"></ul></section>
      <details class="raw">
        <summary>Ver JSON bruto <span class="muted" id="vRawTime"></span></summary>
        <pre id="vRaw"></pre>
      </details>
    </aside>
  </div>
</section>
<script src="/static/painel.js"></script>
</body>
</html>'''

ADMIN_HTML = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Admin - ContagemSys</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#0d1512;color:#edf5f1}.wrap{max-width:1100px;margin:auto;padding:24px}.box{background:#15211c;border:1px solid #2d4037;border-radius:14px;padding:20px;margin-bottom:18px}input,select{width:100%;padding:10px;background:#0e1713;color:white;border:1px solid #40564b;border-radius:8px}button{padding:10px 14px;border:0;border-radius:8px;background:#2b9b62;color:white;font-weight:700;cursor:pointer}.danger{background:#813a3a}.login{max-width:420px;margin:10vh auto}.field{margin:12px 0}.grid{display:grid;gap:12px}.cam{display:grid;grid-template-columns:1.2fr 1fr auto;gap:12px;align-items:end;padding:14px;border:1px solid #30443a;border-radius:10px}.cam small{color:#9caf9f}.hidden{display:none}.error{color:#ff8a8a}@media(max-width:700px){.cam{grid-template-columns:1fr}}
</style></head><body><main class="wrap"><section id="loginBox" class="box login"><h1>Administrador</h1><p>Vincule cada camera a um usuario do Rebano.</p><div class="field"><input id="adminUser" placeholder="Usuario admin"></div><div class="field"><input id="adminPass" type="password" placeholder="Senha"></div><button id="loginBtn">Entrar</button><p class="error" id="loginError"></p></section><section id="panel" class="hidden"><div class="box"><div style="display:flex;justify-content:space-between;align-items:center"><div><h1>Vinculos de cameras</h1><p>Escolha o usuario e clique em Salvar.</p></div><button class="danger" id="logout">Sair</button></div></div><div class="box"><div class="grid" id="cameras"></div><p class="error" id="error"></p></div></section></main>
<script>
let token=localStorage.getItem('contagem_admin_token');const loginBox=document.querySelector('#loginBox'),panel=document.querySelector('#panel'),error=document.querySelector('#error'),adminUserInput=document.querySelector('#adminUser'),adminPassInput=document.querySelector('#adminPass');
function show(){if(token){loginBox.classList.add('hidden');panel.classList.remove('hidden');load()}else{loginBox.classList.remove('hidden');panel.classList.add('hidden')}}
document.querySelector('#loginBtn').onclick=async()=>{document.querySelector('#loginError').textContent='';try{const r=await fetch('/api/auth/admin/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({usuario:adminUserInput.value,senha:adminPassInput.value})});const d=await r.json();if(!r.ok)throw new Error(d.detail||'Erro');token=d.token;localStorage.setItem('contagem_admin_token',token);show()}catch(e){document.querySelector('#loginError').textContent=e.message}};
document.querySelector('#logout').onclick=()=>{localStorage.removeItem('contagem_admin_token');token=null;show()};
async function req(url,opt={}){const r=await fetch(url,{...opt,headers:{'Authorization':'Bearer '+token,'Content-Type':'application/json',...(opt.headers||{})}});if(r.status===401||r.status===403){localStorage.removeItem('contagem_admin_token');token=null;show();throw new Error('Sessao expirada')}const d=await r.json().catch(()=>null);if(!r.ok)throw new Error((d&&d.detail)||'Erro');return d}
async function load(){try{error.textContent='';const [users,cams]=await Promise.all([req('/api/admin/usuarios'),req('/api/admin/cameras')]);const root=document.querySelector('#cameras');root.innerHTML='';cams.forEach(c=>{const el=document.createElement('div');el.className='cam';const options=['<option value="">Sem usuario</option>',...users.map(u=>`<option value="${u.id}" ${c.usuario_id===u.id?'selected':''}>#${u.id} - ${u.nome} (${u.email})</option>`)].join('');el.innerHTML=`<div><strong>${c.name}</strong><br><small>${c.id} | ${c.status}</small></div><div><label><small>Usuario</small><select>${options}</select></label></div><button>Salvar</button>`;const sel=el.querySelector('select');el.querySelector('button').onclick=async()=>{try{if(!sel.value){await req('/api/admin/cameras/'+encodeURIComponent(c.id)+'/vinculo',{method:'DELETE'})}else{const u=users.find(x=>x.id===Number(sel.value));await req('/api/admin/cameras/'+encodeURIComponent(c.id)+'/vinculo',{method:'PUT',body:JSON.stringify({usuario_id:u.id,nome:u.nome,email:u.email})})}await load()}catch(e){error.textContent=e.message}};root.appendChild(el)})}catch(e){error.textContent=e.message}}
show();
</script></body></html>'''
