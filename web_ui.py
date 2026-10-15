from __future__ import annotations

LOGIN_HTML = r'''<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>ContagemSys - Login</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#0f1714;color:#ecf5f0;min-height:100vh;display:grid;place-items:center}.card{width:min(420px,92vw);background:#17231e;border:1px solid #2d4037;border-radius:16px;padding:28px;box-shadow:0 18px 50px #0007}h1{margin:0 0 8px;font-size:25px}p{color:#a9bbb2}.field{display:block;margin:16px 0}.field span{display:block;margin-bottom:6px;font-size:12px;color:#b6c7be;font-weight:700}.field input{width:100%;padding:12px;border:1px solid #3b5146;border-radius:9px;background:#0f1714;color:white}button{width:100%;padding:12px;border:0;border-radius:9px;background:#2b9b62;color:white;font-weight:700;cursor:pointer}.error{min-height:22px;color:#ff8585;margin-top:12px}.links{margin-top:18px;text-align:center}.links a{color:#85d8ad;text-decoration:none;font-size:13px}
</style></head>
<body><main class="card"><h1>ContagemSys</h1><p>Use o mesmo login do Rebano.</p><form id="form"><label class="field"><span>E-MAIL / CPF / TELEFONE</span><input id="login" required></label><label class="field"><span>SENHA</span><input id="senha" type="password" required></label><button>Entrar</button><div class="error" id="erro"></div></form><div class="links"><a href="/admin">Acesso do administrador</a></div></main>
<script>
const form=document.querySelector('#form'),erro=document.querySelector('#erro'),loginInput=document.querySelector('#login'),senhaInput=document.querySelector('#senha');
form.addEventListener('submit',async e=>{e.preventDefault();erro.textContent='';try{const r=await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({login:loginInput.value,senha:senhaInput.value})});const data=await r.json();if(!r.ok)throw new Error(data.detail||'Falha no login');localStorage.setItem('contagem_token',data.token);localStorage.setItem('contagem_usuario',JSON.stringify(data.usuario));location.href='/painel';}catch(ex){erro.textContent=ex.message}})
</script></body></html>'''

PANEL_HTML = r'''<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Minhas cameras - ContagemSys</title>
<style>
*{box-sizing:border-box}body{margin:0;font-family:Arial,sans-serif;background:#0d1512;color:#edf5f1}.top{display:flex;justify-content:space-between;align-items:center;padding:16px 24px;background:#14201b;border-bottom:1px solid #2a3a32}.top button{background:#25372f;color:white;border:1px solid #3b5146;border-radius:8px;padding:9px 12px;cursor:pointer}.wrap{max-width:1250px;margin:auto;padding:24px}h1{font-size:24px}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:18px}.camera{background:#15211c;border:1px solid #2d4037;border-radius:14px;overflow:hidden}.camera img{width:100%;aspect-ratio:16/9;object-fit:cover;background:#050706;display:block}.meta{padding:14px}.row{display:flex;justify-content:space-between;gap:12px}.status{font-size:12px;font-weight:700}.online{color:#63d89b}.offline{color:#f48b8b}.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-top:12px}.metric{background:#0e1713;border-radius:8px;padding:8px}.metric small{display:block;color:#91a59a}.empty{padding:30px;border:1px dashed #40564b;border-radius:12px;color:#a9bbb2}.error{color:#ff8585}
</style></head><body><header class="top"><strong>ContagemSys</strong><div><span id="user"></span> <button id="logout">Sair</button></div></header><main class="wrap"><h1>Minhas cameras</h1><div id="message"></div><section class="grid" id="grid"></section></main>
<script>
const token=localStorage.getItem('contagem_token');if(!token)location.href='/';
try{const u=JSON.parse(localStorage.getItem('contagem_usuario')||'{}');document.querySelector('#user').textContent=u.nome||''}catch{}
document.querySelector('#logout').onclick=()=>{localStorage.removeItem('contagem_token');localStorage.removeItem('contagem_usuario');location.href='/'};
const auth={'Authorization':'Bearer '+token};const grid=document.querySelector('#grid'),msg=document.querySelector('#message');
function card(c){
 const el=document.createElement('article');el.className='camera';el.dataset.camera=c.id;
 const img=document.createElement('img');img.alt=c.name;img.loading='eager';
 const meta=document.createElement('div');meta.className='meta';
 const row=document.createElement('div');row.className='row';
 const title=document.createElement('strong');title.textContent=c.name;
 const status=document.createElement('span');status.className='status '+(c.status==='online'?'online':'offline');status.textContent=c.status.toUpperCase();
 row.append(title,status);meta.append(row);
 const id=document.createElement('small');id.textContent=c.id;meta.append(id);
 const metrics=document.createElement('div');metrics.className='metrics';
 for (const [key,value] of [['Contados',c.total_contado],['No frame',c.animais_no_frame_agora],['FPS IA',Number(c.fps_ia||0).toFixed(1)]]) {
   const metric=document.createElement('div');metric.className='metric';
   const label=document.createElement('small');label.textContent=key;
   const number=document.createElement('b');number.textContent=String(value);
   metric.append(label,number);metrics.append(metric);
 }
 meta.append(metrics);el.append(img,meta);grid.appendChild(el);runStream(c.id,img);
}
async function runStream(id,img){
 let falhas=0;
 while(document.body.contains(img)){
   try{
     const r=await fetch(`/api/minhas-cameras/${encodeURIComponent(id)}/stream-ticket`,{method:'POST',headers:auth,cache:'no-store'});
     if(r.status===401){localStorage.removeItem('contagem_token');location.href='/';return}
     if(!r.ok)throw new Error('Ticket indisponivel');
     const d=await r.json();
     const url=`/api/minhas-cameras/${encodeURIComponent(id)}/stream.mjpg?ticket=${encodeURIComponent(d.ticket)}`;
     await new Promise((resolve,reject)=>{
       img.onerror=()=>{img.onerror=null;reject(new Error('Stream interrompido'))};
       img.onload=()=>{falhas=0};
       img.src=url;
       // O stream MJPEG nao encerra normalmente; aguarda erro ou saida da pagina.
       const timer=setInterval(()=>{if(!document.body.contains(img)){clearInterval(timer);img.src='';resolve()}},500);
       const old=img.onerror;
       img.onerror=()=>{clearInterval(timer);old&&old();};
     });
   }catch(e){falhas=Math.min(falhas+1,5)}
   if(document.body.contains(img)) await new Promise(r=>setTimeout(r,Math.min(1000*falhas,5000)));
 }
}
(async()=>{try{const r=await fetch('/api/minhas-cameras',{headers:auth});if(r.status===401){localStorage.removeItem('contagem_token');location.href='/';return}const data=await r.json();if(!r.ok)throw new Error(data.detail||'Erro');if(!data.length){msg.innerHTML='<div class="empty">Nenhuma camera foi vinculada a este usuario.</div>';return}data.forEach(card);
  setInterval(async()=>{
    try{
      const resp=await fetch('/api/minhas-cameras',{headers:auth,cache:'no-store'});
      if(!resp.ok)return;
      (await resp.json()).forEach(c=>{
        const el=[...grid.children].find(el=>el.dataset.camera===c.id);
        if(!el)return;
        const nums=el.querySelectorAll('.metric b');
        if(nums[0])nums[0].textContent=c.total_contado;
        if(nums[1])nums[1].textContent=c.animais_no_frame_agora;
        if(nums[2])nums[2].textContent=Number(c.fps_ia||0).toFixed(1);
        const status=el.querySelector('.status');
        if(status){status.textContent=c.status.toUpperCase();status.className='status '+(c.status==='online'?'online':'offline')}
      });
    }catch{}
  },2500);
 }catch(e){msg.textContent='Nao foi possivel carregar as cameras.'}})();
</script></body></html>'''

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
