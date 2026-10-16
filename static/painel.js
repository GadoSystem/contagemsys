'use strict';
(() => {
  // ------------------------------------------------------------------ sessao
  let token = null;
  try { token = localStorage.getItem('contagem_token'); } catch { /* sem storage */ }
  if (!token) { location.replace('/'); return; }
  let usuario = {};
  try { usuario = JSON.parse(localStorage.getItem('contagem_usuario') || '{}') || {}; } catch { /* ignora */ }

  const $ = (s, root = document) => root.querySelector(s);
  const enc = encodeURIComponent;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  const AUTH = { Authorization: 'Bearer ' + token };

  // Intervalos (ms). A grade usa o frame.jpg ja produzido pelo worker da camera:
  // nenhuma captura nova e aberta no servidor e nenhum MJPEG fica aberto na grade.
  const POLL_DADOS = 3000;
  const FRAME_LIVE = 1000;
  const FRAME_LIVE_MUITAS = 1600;   // mais de 9 cameras visiveis
  const FRAME_RETRY = 3000;
  const LIVE_MAX_IDADE = 4500;
  const MIN_TILE_PX = 300;

  const ICON = {
    noSignal: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M2 2l20 20"/><path d="M10.7 5H14a2 2 0 0 1 2 2v3.3l1 1L22 8v8"/><path d="M16 16a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V7a2 2 0 0 1 2-2h1"/></svg>',
    connecting: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12.5a10 10 0 0 1 14 0"/><path d="M8.5 16a5 5 0 0 1 7 0"/><path d="M12 19.5h.01"/><path d="M1.5 9a15 15 0 0 1 21 0"/></svg>',
    camera: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M23 7l-7 5 7 5V7z"/><rect x="1" y="5" width="15" height="14" rx="2"/></svg>',
    count: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 19V5M4 19h16"/><path d="M8 15l4-4 3 3 5-6"/></svg>',
    back: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M9 14l-5-5 5-5"/><path d="M4 9h11a5 5 0 0 1 0 10h-3"/></svg>',
    warn: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z"/><path d="M12 9v4M12 17h.01"/></svg>',
    expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/></svg>',
    shrink: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3"/></svg>',
  };

  // ------------------------------------------------------------------ estado
  let grupos = [];                 // [{id, nome, cameras:[summary]}]
  let sincronizadas = true;
  let carregado = false;
  let filtro = 'todas';
  try { filtro = localStorage.getItem('contagem_fazenda') || 'todas'; } catch { /* ignora */ }
  const tiles = new Map();         // camera_id -> estado do bloco
  let layoutChave = '';
  let viewer = null;               // {id, gen, timer}
  let saindo = false;

  function sair() {
    if (saindo) return;
    saindo = true;
    fecharViewer();
    try {
      localStorage.removeItem('contagem_token');
      localStorage.removeItem('contagem_usuario');
    } catch { /* ignora */ }
    location.replace('/');
  }

  // As permissoes vem somente do token: nenhuma rota recebe usuario ou CPF da tela.
  async function api(url, opt = {}) {
    const r = await fetch(url, { ...opt, headers: AUTH, cache: 'no-store' });
    if (r.status === 401) { sair(); throw new Error('Sessão expirada'); }
    return r;
  }

  const chaveGrupo = (g) => (g.id == null ? 'outras' : 'f' + g.id);
  const todasCameras = () => grupos.flatMap((g) => g.cameras.map((c) => ({ ...c, fazenda: g.nome })));
  function camerasVisiveis() {
    if (filtro === 'todas') return todasCameras();
    const g = grupos.find((x) => chaveGrupo(x) === filtro);
    return g ? g.cameras.map((c) => ({ ...c, fazenda: g.nome })) : [];
  }
  const fmtHora = (d) => d.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
  const fmtNum = (v) => (typeof v === 'number' ? v.toLocaleString('pt-BR') : '—');
  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text != null) e.textContent = text;
    return e;
  }

  // ------------------------------------------------------------------ cabecalho
  const nome = String(usuario.nome || 'Usuário');
  $('#userName').textContent = nome;
  $('#userName').title = nome;
  $('#avatar').textContent = nome.split(/\s+/).filter(Boolean).slice(0, 2).map((p) => p[0]).join('').toUpperCase() || '?';
  $('#logout').addEventListener('click', sair);

  function relogio() {
    const agora = new Date();
    $('#clockTime').textContent = fmtHora(agora);
    const data = agora.toLocaleDateString('pt-BR', { weekday: 'long', day: '2-digit', month: 'long' });
    $('#clockDate').textContent = data.charAt(0).toUpperCase() + data.slice(1);
  }
  relogio();
  setInterval(relogio, 1000);

  const btnFull = $('#fullscreen');
  if (!document.documentElement.requestFullscreen) btnFull.classList.add('hidden');
  btnFull.addEventListener('click', () => {
    if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
    else document.documentElement.requestFullscreen().catch(() => {});
  });
  document.addEventListener('fullscreenchange', () => {
    const cheio = !!document.fullscreenElement;
    btnFull.innerHTML = (cheio ? ICON.shrink : ICON.expand) + `<span class="btn-label">${cheio ? 'Sair da tela cheia' : 'Tela cheia'}</span>`;
    btnFull.setAttribute('aria-pressed', String(cheio));
    requestAnimationFrame(ajustarGrade);
  });

  // ------------------------------------------------------------------ abas e resumo
  function renderAbas() {
    const nav = $('#farmTabs');
    const itens = [{ chave: 'todas', nome: 'Todas', cameras: todasCameras() }]
      .concat(grupos.map((g) => ({ chave: chaveGrupo(g), nome: g.nome, cameras: g.cameras })));
    if (!itens.some((i) => i.chave === filtro)) filtro = 'todas';
    nav.textContent = '';
    for (const item of itens) {
      const online = item.cameras.filter((c) => c.status === 'online').length;
      const b = el('button', 'farm-tab');
      b.type = 'button';
      b.setAttribute('role', 'tab');
      b.setAttribute('aria-selected', String(item.chave === filtro));
      b.append(el('span', null, item.nome));
      const count = el('span', 'count tabular' + (online === 0 && item.cameras.length ? ' none' : ''));
      count.title = `${online} de ${item.cameras.length} câmeras online`;
      const b1 = el('b', null, String(online));
      count.append(b1, document.createTextNode(`/${item.cameras.length}`));
      b.append(count);
      b.addEventListener('click', () => {
        filtro = item.chave;
        try { localStorage.setItem('contagem_fazenda', filtro); } catch { /* ignora */ }
        render();
      });
      nav.append(b);
    }
  }

  function renderResumo() {
    const cams = camerasVisiveis();
    const online = cams.filter((c) => c.status === 'online').length;
    const soma = (k) => cams.reduce((t, c) => t + (Number(c[k]) || 0), 0);
    $('#sumOnline').innerHTML = '';
    $('#sumOnline').append(document.createTextNode(String(online)), el('small', null, ` / ${cams.length}`));
    $('#sumTotal').textContent = fmtNum(soma('total_contado'));
    $('#sumRetornos').textContent = fmtNum(soma('retornos_esquerda_para_direita'));
  }

  // ------------------------------------------------------------------ grade
  function criarTile(cam) {
    const b = el('button', 'tile');
    b.type = 'button';
    b.dataset.id = cam.id;
    const img = el('img');
    img.alt = '';
    img.decoding = 'async';
    img.classList.add('hidden');
    const ns = el('div', 'no-signal connecting');
    const top = el('div', 'tile-top');
    const name = el('span', 'tile-name');
    const badge = el('span', 'badge connecting', 'Conectando');
    top.append(name, badge);
    const bottom = el('div', 'tile-bottom');
    const metrics = el('div', 'tile-metrics');
    const chipTotal = el('span', 'metric-chip tabular');
    const chipRet = el('span', 'metric-chip tabular');
    const time = el('span', 'tile-time tabular', '—');
    metrics.append(chipTotal, chipRet);
    bottom.append(metrics, time);
    b.append(img, ns, top, bottom);
    b.addEventListener('click', () => abrirViewer(cam.id));
    const t = {
      el: b, img, ns, name, badge, chipTotal, chipRet, time,
      cam, url: null, ultimoFrame: 0, tentativas: 0, proxima: 0, buscando: false, estado: '',
    };
    img.addEventListener('load', () => { if (t.antigo) { URL.revokeObjectURL(t.antigo); t.antigo = null; } });
    return t;
  }

  function chip(span, valor, rotulo) {
    span.textContent = '';
    span.append(el('b', null, fmtNum(valor)), el('span', null, rotulo));
  }

  function estadoTile(t) {
    if (t.ultimoFrame && Date.now() - t.ultimoFrame < LIVE_MAX_IDADE) return 'live';
    if (t.cam.status === 'online' && t.tentativas < 3) return 'connecting';
    return 'offline';
  }

  function atualizarTile(t) {
    const cam = t.cam;
    t.name.textContent = cam.name || cam.id;
    t.el.setAttribute('aria-label', `Abrir ${cam.name || cam.id}`);
    chip(t.chipTotal, cam.total_contado, 'contados');
    chip(t.chipRet, cam.retornos_esquerda_para_direita, 'retornos');
    t.time.textContent = t.ultimoFrame ? 'Atualizado ' + fmtHora(new Date(t.ultimoFrame)) : 'Sem atualização';
    const estado = estadoTile(t);
    if (estado === t.estado) return;
    t.estado = estado;
    t.badge.className = 'badge ' + estado;
    t.badge.textContent = estado === 'live' ? 'Ao vivo' : estado === 'offline' ? 'Sem sinal' : 'Conectando';
    t.el.classList.toggle('is-offline', estado === 'offline');
    t.img.classList.toggle('hidden', estado !== 'live');
    t.ns.classList.toggle('hidden', estado === 'live');
    t.ns.className = 'no-signal' + (estado === 'connecting' ? ' connecting' : '') + (estado === 'live' ? ' hidden' : '');
    t.ns.innerHTML = estado === 'offline' ? ICON.noSignal : ICON.connecting;
    t.ns.append(
      el('strong', null, estado === 'offline' ? 'Sem sinal — tentando reconectar' : 'Conectando…'),
      el('span', null, estado === 'offline' ? 'A imagem volta sozinha quando a câmera responder.' : 'Aguardando a primeira imagem da câmera.'),
    );
  }

  function renderGrade() {
    const grid = $('#grid');
    const cams = camerasVisiveis();
    const comTitulos = filtro === 'todas' && grupos.length > 1;
    const chave = filtro + '|' + (comTitulos ? grupos.map((g) => chaveGrupo(g) + ':' + g.cameras.map((c) => c.id).join(',')).join(';') : cams.map((c) => c.id).join(','));

    // Remove blocos de cameras que deixaram de ser autorizadas.
    const ids = new Set(todasCameras().map((c) => c.id));
    for (const [id, t] of tiles) {
      if (!ids.has(id)) { if (t.url) URL.revokeObjectURL(t.url); tiles.delete(id); }
    }
    for (const cam of todasCameras()) {
      let t = tiles.get(cam.id);
      if (!t) { t = criarTile(cam); tiles.set(cam.id, t); }
      t.cam = cam;
      atualizarTile(t);
    }

    $('#emptyState').classList.toggle('hidden', !carregado || cams.length > 0);
    $('#loading').classList.toggle('hidden', carregado);
    if (chave !== layoutChave) {
      layoutChave = chave;
      grid.textContent = '';
      if (comTitulos) {
        for (const g of grupos) {
          const h = el('h2', 'farm-heading', g.nome);
          grid.append(h);
          for (const c of g.cameras) grid.append(tiles.get(c.id).el);
        }
      } else {
        for (const c of cams) grid.append(tiles.get(c.id).el);
      }
      ajustarGrade();
    }
  }

  function colunasIdeais(n) {
    if (n <= 1) return 1;
    if (n <= 4) return 2;
    if (n <= 9) return 3;
    if (n <= 16) return 4;
    return 5;
  }

  // Colunas pela quantidade e pela largura; em telas grandes, encolhe a grade para
  // que todas as linhas caibam na altura (TV/projetor em tela cheia, sem rolagem).
  function ajustarGrade() {
    const grid = $('#grid');
    const wrap = $('#gridWrap');
    const n = camerasVisiveis().length;
    if (!n) return;
    const largura = wrap.clientWidth;
    const gap = parseFloat(getComputedStyle(grid).columnGap) || 16;
    const porLargura = Math.max(1, Math.floor((largura + gap) / (MIN_TILE_PX + gap)));
    const cols = Math.min(colunasIdeais(n), porLargura);
    grid.style.setProperty('--cols', String(cols));
    grid.style.maxWidth = '';
    const comTitulos = filtro === 'todas' && grupos.length > 1;
    if (comTitulos || window.innerWidth < 700) return;
    const linhas = Math.ceil(n / cols);
    const altura = window.innerHeight - wrap.getBoundingClientRect().top - 20;
    const alturaTile = (altura - gap * (linhas - 1)) / linhas;
    if (alturaTile < 170) return;
    const larguraMax = cols * alturaTile * 16 / 9 + gap * (cols - 1);
    if (larguraMax < largura) grid.style.maxWidth = Math.floor(larguraMax) + 'px';
  }
  new ResizeObserver(() => ajustarGrade()).observe($('#gridWrap'));
  window.addEventListener('resize', ajustarGrade);

  function render() {
    renderAbas();
    renderResumo();
    $('#syncNotice').classList.toggle('hidden', sincronizadas || !carregado);
    renderGrade();
  }

  // ------------------------------------------------------------------ dados
  async function carregarDados() {
    try {
      const r = await api('/api/minhas-fazendas');
      const data = await r.json().catch(() => null);
      if (!r.ok || !data || !Array.isArray(data.grupos)) throw new Error('Resposta inválida');
      grupos = data.grupos.filter((g) => Array.isArray(g.cameras) && g.cameras.length);
      sincronizadas = !!data.fazendas_sincronizadas;
      carregado = true;
      $('#loadError').classList.add('hidden');
      render();
      if (viewer && !todasCameras().some((c) => c.id === viewer.id)) fecharViewer();
      if (viewer) atualizarNavViewer();
    } catch (e) {
      if (saindo) return;
      if (!carregado) {
        $('#loading').classList.add('hidden');
        $('#loadError').classList.remove('hidden');
      }
    }
  }

  // Um unico laco agenda os frames da grade; no maximo uma requisicao por camera.
  async function buscarFrame(t) {
    t.buscando = true;
    try {
      const r = await api(`/api/minhas-cameras/${enc(t.cam.id)}/frame.jpg`);
      if (r.ok) {
        const blob = await r.blob();
        const url = URL.createObjectURL(blob);
        t.antigo = t.url;
        t.url = url;
        t.img.src = url;
        t.ultimoFrame = Date.now();
        t.tentativas = 0;
      } else {
        t.tentativas++;
        if (r.status === 404) carregarDados();
      }
    } catch {
      t.tentativas++;
    } finally {
      t.buscando = false;
      const vivo = t.tentativas === 0;
      const visiveis = camerasVisiveis().length;
      t.proxima = Date.now() + (vivo ? (visiveis > 9 ? FRAME_LIVE_MUITAS : FRAME_LIVE) : FRAME_RETRY);
      atualizarTile(t);
    }
  }

  setInterval(() => {
    if (document.hidden || viewer || saindo) return;   // a visao ampliada usa o MJPEG
    const agora = Date.now();
    for (const cam of camerasVisiveis()) {
      const t = tiles.get(cam.id);
      if (!t) continue;
      // Camera offline no servidor: nao pede frame (evita 503); volta sozinha
      // quando o status (atualizado a cada POLL_DADOS) ficar online.
      if (t.cam.status === 'online' && !t.buscando && agora >= t.proxima) buscarFrame(t);
      else atualizarTile(t);
    }
  }, 250);

  // ------------------------------------------------------------------ visao ampliada
  const vw = {
    root: $('#viewer'), title: $('#vTitle'), sub: $('#vSub'), badge: $('#vBadge'), video: $('#vVideo'),
    ns: $('#vNoSignal'), total: $('#vTotal'), ret: $('#vRetornos'), time: $('#vTime'),
    cards: $('#vCards'), stats: $('#vStats'), events: $('#vEvents'), raw: $('#vRaw'), rawTime: $('#vRawTime'),
    prev: $('#vPrev'), next: $('#vNext'),
  };
  let ultimoFoco = null;

  function vEstado(estado) {
    vw.badge.className = 'badge ' + estado;
    vw.badge.textContent = estado === 'live' ? 'Ao vivo' : estado === 'offline' ? 'Sem sinal' : 'Conectando';
    vw.ns.classList.toggle('hidden', estado === 'live');
    vw.ns.className = 'no-signal' + (estado === 'connecting' ? ' connecting' : '') + (estado === 'live' ? ' hidden' : '');
    vw.ns.innerHTML = estado === 'offline' ? ICON.noSignal : ICON.connecting;
    vw.ns.append(el('strong', null, estado === 'offline' ? 'Sem sinal — tentando reconectar' : 'Conectando ao vídeo…'));
  }

  function pararVideo() {
    const old = $('img', vw.video);
    if (old) { old.onerror = null; old.src = ''; old.remove(); }
  }

  // Um unico <img> MJPEG por vez. O servidor so reenvia os frames ja capturados.
  function tocarUmaVez(url, gen) {
    return new Promise((resolve) => {
      pararVideo();
      const img = el('img');
      img.alt = 'Vídeo ao vivo da câmera';
      let mostrou = false;
      const inicio = Date.now();
      const fim = () => { clearInterval(timer); img.onerror = null; img.src = ''; img.remove(); resolve(mostrou); };
      img.onerror = fim;
      const timer = setInterval(() => {
        if (!viewer || gen !== viewer.gen) return fim();
        if (!mostrou && img.naturalWidth > 0) { mostrou = true; vEstado('live'); }
        if (!mostrou && Date.now() - inicio > 10000) return fim();
      }, 300);
      img.src = url;
      vw.video.prepend(img);
    });
  }

  async function rodarStream(id, gen) {
    let falhas = 0;
    while (viewer && viewer.gen === gen) {
      vEstado(falhas ? 'offline' : 'connecting');
      let mostrou = false;
      try {
        const r = await api(`/api/minhas-cameras/${enc(id)}/stream-ticket`, { method: 'POST' });
        if (!viewer || viewer.gen !== gen) return;
        if (r.status === 404) { fecharViewer(); carregarDados(); return; }
        if (!r.ok) throw new Error('ticket');
        const d = await r.json();
        mostrou = await tocarUmaVez(`/api/minhas-cameras/${enc(id)}/stream.mjpg?ticket=${enc(d.ticket)}`, gen);
      } catch { /* tenta de novo */ }
      if (!viewer || viewer.gen !== gen) return;
      falhas = mostrou ? 1 : Math.min(falhas + 1, 5);
      vEstado('offline');
      await sleep(Math.min(1000 * falhas, 5000));
    }
  }

  function dataHora(v) {
    if (!v) return '—';
    const d = new Date(v);
    return isNaN(d) ? String(v) : d.toLocaleString('pt-BR');
  }
  const decimal = (v, casas = 1) => (typeof v === 'number' ? v.toLocaleString('pt-BR', { maximumFractionDigits: casas }) : '—');

  // Somente campos que existem na resposta; nada e inventado.
  function card(destino, obj, chave, rotulo, fmt = fmtNum, opts = {}) {
    if (!obj || !(chave in obj)) return;
    const c = el('div', 'card' + (opts.cls ? ' ' + opts.cls : ''));
    c.title = chave;
    const valor = obj[chave] == null ? '—' : fmt(obj[chave]);
    const v = el('div', 'card-value tabular' + (opts.texto ? ' text' : ''), valor);
    if (opts.unidade && obj[chave] != null) v.append(el('small', null, opts.unidade));
    c.append(el('div', 'card-label', rotulo), v);
    destino.append(c);
  }

  function renderDetalhes(data) {
    const cam = data.camera || {};
    const est = data.estatisticas || {};
    chip(vw.total, cam.total_contado, 'contados');
    chip(vw.ret, cam.retornos_esquerda_para_direita, 'retornos');

    vw.cards.textContent = '';
    if (cam.ultimo_erro) {
      const a = el('div', 'card wide alert');
      a.append(el('div', 'card-label', 'Último erro informado pela câmera'), el('div', 'card-value', String(cam.ultimo_erro)));
      vw.cards.append(a);
    }
    card(vw.cards, cam, 'total_contado', 'Total contado (sessão)', fmtNum, { cls: 'highlight' });
    card(vw.cards, cam, 'retornos_esquerda_para_direita', 'Retornos (sessão)');
    card(vw.cards, cam, 'animais_no_frame_agora', 'Detecções no frame');
    card(vw.cards, cam, 'fps_camera', 'FPS da câmera', (v) => decimal(v));
    card(vw.cards, cam, 'fps_ia', 'FPS da IA', (v) => decimal(v));
    card(vw.cards, cam, 'latencia_ia_ms', 'Latência da IA', (v) => decimal(v, 0), { unidade: 'ms' });
    card(vw.cards, cam, 'espera_fila_ia_ms', 'Espera na fila da IA', (v) => decimal(v, 0), { unidade: 'ms' });
    card(vw.cards, cam, 'resolucao_camera', 'Resolução', (v) => (Array.isArray(v) ? v.join(' × ') : String(v)), { texto: true });

    vw.stats.textContent = '';
    card(vw.stats, est, 'total_hoje', 'Contados hoje', fmtNum, { cls: 'highlight' });
    card(vw.stats, est, 'total_historico', 'Total histórico');
    card(vw.stats, est, 'total_retornos', 'Retornos (histórico)');
    card(vw.stats, est, 'sessao_id', 'Sessão', (v) => '#' + v, { texto: true });
    card(vw.stats, est, 'ultimo_registro', 'Última contagem', dataHora, { texto: true, cls: 'wide' });
    card(vw.stats, est, 'primeiro_registro', 'Primeira contagem', dataHora, { texto: true, cls: 'wide' });
    card(vw.stats, est, 'sessao_iniciada_em', 'Sessão iniciada em', dataHora, { texto: true, cls: 'wide' });

    vw.events.textContent = '';
    const eventos = Array.isArray(data.eventos) ? data.eventos.slice(0, 10) : [];
    if (!eventos.length) vw.events.append(el('li', 'muted', 'Nenhum evento registrado ainda.'));
    for (const ev of eventos) {
      const contado = !!ev.counted;
      const li = el('li', 'event' + (contado ? '' : ' retorno'));
      li.append(el('span', 'event-dot'));
      let texto = contado ? 'Contado' : 'Retorno';
      if (ev.track_id != null) texto += ` · ID ${ev.track_id}`;
      if (typeof ev.confidence === 'number') texto += ` · ${Math.round(ev.confidence * 100)}%`;
      li.append(el('span', null, texto));
      const d = new Date(ev.timestamp);
      li.append(el('span', 'event-time tabular', isNaN(d) ? '' : d.toLocaleTimeString('pt-BR')));
      vw.events.append(li);
    }

    vw.raw.textContent = JSON.stringify(data, null, 2);
    const agora = new Date();
    vw.rawTime.textContent = 'Consultado às ' + fmtHora(agora);
    vw.time.textContent = 'Atualizado ' + fmtHora(agora);
  }

  async function carregarDetalhes() {
    if (!viewer || viewer.busy) return;
    const id = viewer.id;
    viewer.busy = true;
    try {
      const r = await api(`/api/minhas-cameras/${enc(id)}/detalhes?offset_minutos=${-new Date().getTimezoneOffset()}`);
      if (!viewer || viewer.id !== id) return;
      if (r.status === 404) { fecharViewer(); carregarDados(); return; }
      if (!r.ok) throw new Error();
      const data = await r.json();
      if (viewer && viewer.id === id && data && typeof data === 'object') renderDetalhes(data);
    } catch { /* mantem os ultimos dados; tenta no proximo ciclo */ }
    finally { if (viewer && viewer.id === id) viewer.busy = false; }
  }

  function atualizarNavViewer() {
    const lista = camerasVisiveis();
    const i = lista.findIndex((c) => c.id === viewer.id);
    const cam = todasCameras().find((c) => c.id === viewer.id);
    if (cam) {
      vw.title.textContent = cam.name || cam.id;
      vw.sub.textContent = `${cam.fazenda} · ${cam.id}`;
    }
    const multi = lista.length > 1 && i >= 0;
    vw.prev.classList.toggle('hidden', !multi);
    vw.next.classList.toggle('hidden', !multi);
  }

  function abrirViewer(id) {
    if (viewer && viewer.id === id) return;
    const gen = viewer ? viewer.gen + 1 : 1;
    if (viewer) { clearInterval(viewer.timer); pararVideo(); }
    if (!viewer) ultimoFoco = document.activeElement;
    viewer = { id, gen, busy: false, timer: setInterval(carregarDetalhes, 2000) };
    vw.root.classList.remove('hidden');
    document.body.style.overflow = 'hidden';
    vw.cards.textContent = '';
    vw.stats.textContent = '';
    vw.events.textContent = '';
    vw.raw.textContent = '';
    vw.rawTime.textContent = '';
    vw.time.textContent = '';
    const cam = todasCameras().find((c) => c.id === id);
    if (cam) { chip(vw.total, cam.total_contado, 'contados'); chip(vw.ret, cam.retornos_esquerda_para_direita, 'retornos'); }
    atualizarNavViewer();
    vEstado('connecting');
    carregarDetalhes();
    rodarStream(id, gen);
    $('#vClose').focus();
  }

  function fecharViewer() {
    if (!viewer) return;
    clearInterval(viewer.timer);
    viewer = null;
    pararVideo();
    vw.root.classList.add('hidden');
    document.body.style.overflow = '';
    if (ultimoFoco && ultimoFoco.isConnected) ultimoFoco.focus();
  }

  function navegar(passo) {
    if (!viewer) return;
    const lista = camerasVisiveis();
    const i = lista.findIndex((c) => c.id === viewer.id);
    if (i < 0 || lista.length < 2) return;
    abrirViewer(lista[(i + passo + lista.length) % lista.length].id);
  }

  $('#vClose').addEventListener('click', fecharViewer);
  vw.prev.addEventListener('click', () => navegar(-1));
  vw.next.addEventListener('click', () => navegar(1));
  document.addEventListener('keydown', (e) => {
    if (!viewer) return;
    if (e.key === 'Escape' && !document.fullscreenElement) fecharViewer();
    else if (e.key === 'ArrowLeft') navegar(-1);
    else if (e.key === 'ArrowRight') navegar(1);
  });

  // ------------------------------------------------------------------ inicio
  $('#retry').addEventListener('click', () => { $('#loadError').classList.add('hidden'); $('#loading').classList.remove('hidden'); carregarDados(); });
  document.addEventListener('visibilitychange', () => { if (!document.hidden) carregarDados(); });
  carregarDados();
  setInterval(() => { if (!document.hidden) carregarDados(); }, POLL_DADOS);
})();
