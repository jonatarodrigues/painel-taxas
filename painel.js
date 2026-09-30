/* Painel de Taxas — sem build. ECharts via CDN; dados em dados.json (http) ou dados.js (file://). */
(function () {
  'use strict';

  // ---------- constantes ----------
  const GRUPOS = { juros: 'Juros Brasil', inflacao: 'Inflação Brasil', cambio: 'Câmbio', bolsa: 'Bolsa e commodities', macro: 'Macro Brasil', exterior: 'Exterior' };
  const ORDEM_GRUPOS = Object.keys(GRUPOS);
  const CATEGORIAS = { copom: 'Copom', fomc: 'Fed', crise: 'Crise', politica: 'Política', fiscal: 'Fiscal', externo: 'Externo', plano: 'Plano econômico' };
  const ORDEM_CAT = Object.keys(CATEGORIAS);
  const KPI_IDS = ['selic_meta', 'cdi', 'ipca_12m', 'usd_brl', 'fed_funds', 'ibovespa'];
  const JANELAS = { tudo: 'Tudo', '10a': '10 anos', '5a': '5 anos', '3a': '3 anos' };
  const PERIODOS = { '1a': 1, '5a': 5, '10a': 10, '20a': 20, tudo: null };
  const MAX_SERIES = 8;

  let D = null;
  let modo = 'publico';
  const charts = {};
  const estado = {
    aba: 'series',
    selecionadas: ['selic_meta', 'ipca_12m', 'usd_brl'],
    modo: 'variacao',
    periodo: '10a',
    categorias: new Set(ORDEM_CAT),
    janela: 'tudo',
    corte: 0.3,
    gruposCerebro: new Set(ORDEM_GRUPOS),
    noSelecionado: null,
    janelaHeat: 'tudo',
    filtroCat: new Set(ORDEM_CAT),
    busca: '',
    traj: 'selic',
  };
  const RENDER = {};

  // ---------- utilidades ----------
  const $ = (sel, raiz = document) => raiz.querySelector(sel);
  const $$ = (sel, raiz = document) => Array.from(raiz.querySelectorAll(sel));
  const cssVar = (nome) => getComputedStyle(document.documentElement).getPropertyValue(nome).trim();
  const corGrupo = (g) => cssVar('--g-' + g) || '#888888';
  const corSlot = (i) => cssVar('--s' + ((i % MAX_SERIES) + 1));
  const corCat = (c) => cssVar('--c-' + c) || cssVar('--muted');

  function el(tag, attrs = {}, ...filhos) {
    const e = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v === false || v == null) continue;
      if (k === 'class') e.className = v;
      else if (k === 'text') e.textContent = v;
      else if (k.startsWith('on')) e.addEventListener(k.slice(2), v);
      else e.setAttribute(k, v === true ? '' : v);
    }
    for (const f of filhos) if (f != null) e.append(f);
    return e;
  }
  const fmt = (v, casas = 2) => (v == null || Number.isNaN(v)) ? '—' : Number(v).toLocaleString('pt-BR', { minimumFractionDigits: casas, maximumFractionDigits: casas });
  const fmtSinal = (v, casas = 2) => v == null ? '—' : (v > 0 ? '+' : '') + fmt(v, casas);
  const fmtData = (iso) => { if (!iso) return '—'; const [a, m, d] = iso.split('-'); return d ? `${d}/${m}/${a}` : `${m}/${a}`; };
  const casasDe = (id) => { const u = (D.series[id] && D.series[id].unidade) || ''; return /pontos|índice/.test(u) ? 0 : (u === 'R$' ? 3 : 2); };
  // Taxas e percentuais (% a.a., % 12m, % a.m., % PIB, p.p.) cabem no mesmo eixo; as demais unidades ficam sozinhas.
  const familiaEixo = (u) => (u.startsWith('%') || u === 'p.p.') ? '%' : u;
  const unidadeVar = (id) => D.series[id].var_tipo === 'pct' ? '%' : ' p.p.';
  const classeVar = (v) => v == null ? 'muted' : (v > 0 ? 'var-pos' : v < 0 ? 'var-neg' : '');
  const fmtVar = (id, v) => v == null ? '—' : fmtSinal(v) + unidadeVar(id);
  const plural = (n, um, varios) => `${n} ${n === 1 ? um : varios}`;
  const addDias = (iso, dias) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCDate(d.getUTCDate() + dias); return d.toISOString().slice(0, 10); };
  const anosAtras = (iso, anos) => { const d = new Date(iso + 'T00:00:00Z'); d.setUTCFullYear(d.getUTCFullYear() - anos); return d.toISOString().slice(0, 10); };

  function pontos(id) {
    const s = D.series[id];
    if (!s) return [];
    return s.diario.length ? s.diario : s.mensal.map(([m, v]) => [m + '-01', v]);
  }
  function valorEm(id, iso) {
    const arr = pontos(id);
    let lo = 0, hi = arr.length - 1, res = null;
    while (lo <= hi) {
      const mid = (lo + hi) >> 1;
      if (arr[mid][0] <= iso) { res = arr[mid][1]; lo = mid + 1; } else hi = mid - 1;
    }
    return res;
  }
  function impacto(id, iso, dias) {
    const s = D.series[id];
    const arr = pontos(id);
    if (!s || !arr.length) return null;
    const fim = addDias(iso, dias);
    if (iso < arr[0][0] || fim > arr[arr.length - 1][0]) return null;
    const v0 = valorEm(id, iso), v1 = valorEm(id, fim);
    if (v0 == null || v1 == null) return null;
    return s.var_tipo === 'pct' ? (v0 ? (v1 / v0 - 1) * 100 : null) : v1 - v0;
  }

  // ---------- base ECharts ----------
  function grafico(idEl) {
    const dom = document.getElementById(idEl);
    if (charts[idEl]) charts[idEl].dispose();
    dom.replaceChildren();
    charts[idEl] = echarts.init(dom, null, { renderer: 'canvas' });
    return charts[idEl];
  }
  const textoBase = () => ({ color: cssVar('--text-2'), fontFamily: 'Inter, system-ui, sans-serif' });
  const eixoBase = () => ({ axisLine: { lineStyle: { color: cssVar('--axis') } }, axisTick: { show: false }, axisLabel: { color: cssVar('--muted'), fontSize: 11 }, splitLine: { lineStyle: { color: cssVar('--grid') } } });
  const tooltipBase = () => ({ backgroundColor: cssVar('--card'), borderColor: cssVar('--border-solid'), borderWidth: 1, textStyle: { color: cssVar('--text'), fontSize: 12 }, extraCssText: 'box-shadow:0 8px 24px rgba(0,0,0,.25);border-radius:8px;' });

  // ---------- KPIs ----------
  function renderKpis() {
    const box = $('#kpis');
    box.replaceChildren();
    for (const id of KPI_IDS) {
      const s = D.series[id];
      if (!s) continue;
      box.append(el('article', { class: 'kpi', style: `--cor:${corGrupo(s.grupo)}` },
        el('div', { class: 'kpi-nome', text: s.nome }),
        el('div', { class: 'kpi-valor', text: fmt(s.ultimo, casasDe(id)) }, el('span', { class: 'kpi-unid', text: ' ' + s.unidade })),
        el('div', { class: 'kpi-vars' },
          el('span', { class: classeVar(s.var_1m), text: '1m ' + fmtVar(id, s.var_1m) }),
          el('span', { class: classeVar(s.var_12m), text: '12m ' + fmtVar(id, s.var_12m) })),
        el('div', { class: 'kpi-spark', id: 'spark-' + id }),
        el('div', { class: 'kpi-data muted', text: 'até ' + fmtData(s.fim) })));
    }
    for (const id of KPI_IDS) {
      const s = D.series[id];
      if (!s) continue;
      const dados = s.mensal.slice(-24).map((p) => p[1]);
      grafico('spark-' + id).setOption({
        animation: false,
        grid: { left: 0, right: 0, top: 4, bottom: 4 },
        xAxis: { type: 'category', show: false, data: dados.map((_, k) => k) },
        yAxis: { type: 'value', show: false, min: 'dataMin', max: 'dataMax' },
        series: [{ type: 'line', data: dados, showSymbol: false, lineStyle: { width: 1.5, color: corGrupo(s.grupo) }, areaStyle: { color: corGrupo(s.grupo), opacity: 0.12 } }],
      });
    }
  }

  // ---------- abas ----------
  function ativarAba(nome) {
    estado.aba = nome;
    $$('[role=tab]').forEach((b) => b.setAttribute('aria-selected', String(b.dataset.aba === nome)));
    $$('.aba').forEach((s) => { const ativa = s.id === 'aba-' + nome; s.hidden = !ativa; s.classList.toggle('ativa', ativa); });
    renderAba();
  }
  function renderAba() { if (RENDER[estado.aba]) RENDER[estado.aba](); }

  // ---------- tema ----------
  function aplicarTema(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('tema', t); } catch (e) { /* armazenamento indisponível */ }
    $('#btn-tema').textContent = t === 'dark' ? '☀ Claro' : '☾ Escuro';
    if (D) { renderKpis(); renderAba(); }
  }

  // ---------- carregamento ----------
  function carregarDadosJs() {
    return new Promise((res, rej) => {
      const s = document.createElement('script');
      s.src = 'dados.js';
      s.onload = () => (window.DADOS ? res(window.DADOS) : rej(new Error('dados.js não definiu window.DADOS')));
      s.onerror = () => rej(new Error('dados.js não encontrado'));
      document.head.append(s);
    });
  }
  async function carregar() {
    if (/^https?:$/.test(location.protocol)) {
      try {
        const r = await fetch('dados.json', { cache: 'no-store' });
        if (r.ok) return await r.json();
      } catch (e) { /* cai no fallback */ }
    }
    try {
      return await carregarDadosJs();
    } catch (e) { /* cai no erro final */ }
    throw new Error('Não encontrei dados.json nem dados.js. Rode "python atualizar.py" nesta pasta e recarregue.');
  }
  function validar(d) {
    for (const k of ['series', 'correlacao', 'arestas', 'eventos']) {
      if (!d || typeof d[k] !== 'object' || d[k] === null) throw new Error(`dados.json inválido: falta a chave "${k}"`);
    }
  }

  function montarControlesBase() {
    $$('[role=tab]').forEach((b) => b.addEventListener('click', () => ativarAba(b.dataset.aba)));
    $('#btn-avisos').addEventListener('click', () => { const box = $('#avisos'); box.hidden = !box.hidden; });
    $('#btn-atualizar').addEventListener('click', aoClicarAtualizar);
    mostrarAvisos();
    $('#atualizado').textContent = textoAtualizado();
  }

  // ---------- atualizar ----------
  async function detectarModo() {
    if (location.protocol === 'file:') return 'arquivo';
    if (location.hostname !== '127.0.0.1' && location.hostname !== 'localhost') return 'publico';
    try {
      const r = await fetch('api/status', { cache: 'no-store' });
      if (r.ok) { const j = await r.json(); if (j && j.local === true) return 'local'; }
    } catch (e) { /* sem servidor local */ }
    return 'publico';
  }
  function textoAtualizado() {
    const base = 'Atualizado em ' + fmtData(D.gerado_em.slice(0, 10)) + ' às ' + D.gerado_em.slice(11, 16);
    return modo === 'publico' ? base + ' · atualização automática em dias úteis às 20h' : base;
  }
  function mostrarAvisos() {
    const lista = D.avisos || [];
    $('#btn-avisos').hidden = !lista.length;
    $('#n-avisos').textContent = lista.length;
    $('#avisos').replaceChildren(...lista.map((a) => el('div', { text: a })));
    if (!lista.length) $('#avisos').hidden = true;
  }
  function aplicarDados(novo) {
    validar(novo);
    D = novo;
    $('#atualizado').textContent = textoAtualizado();
    mostrarAvisos();
    renderKpis();
    renderAba();
  }
  function toast(msg, persistente = false) {
    const t = $('#toast');
    t.textContent = msg;
    t.hidden = false;
    clearTimeout(toast.timer);
    if (!persistente) toast.timer = setTimeout(() => { t.hidden = true; }, 4000);
  }
  function girando(sim) {
    const b = $('#btn-atualizar');
    b.disabled = sim;
    b.classList.toggle('girando', sim);
  }
  const esperar = (ms) => new Promise((r) => setTimeout(r, ms));
  async function atualizarLocal() {
    girando(true);
    toast('Atualizando… pode levar alguns minutos', true);
    try {
      const r = await fetch('api/atualizar', { method: 'POST', headers: { 'X-Painel': '1' } });
      if (r.status !== 202 && r.status !== 409) { toast(`Não foi possível atualizar (HTTP ${r.status})`); return; }
      let st;
      do {
        await esperar(3000);
        st = await (await fetch('api/status', { cache: 'no-store' })).json();
      } while (st.atualizando);
      // O atualizar.py grava os arquivos mesmo com falhas parciais; o código 1 só vem quando tudo falha.
      try { aplicarDados(await carregar()); } catch (e) { /* mantém os dados na tela */ }
      toast(st.ultimo_codigo === 0 ? 'Dados atualizados' : `A atualização falhou (código ${st.ultimo_codigo}); dados anteriores mantidos`);
    } catch (e) {
      toast('Servidor local indisponível; feche e abra o painel de novo');
    } finally {
      girando(false);
    }
  }
  async function atualizarPublico() {
    girando(true);
    try {
      const novo = await carregar();
      if (novo.gerado_em !== D.gerado_em) { aplicarDados(novo); toast('Dados atualizados'); }
      else toast(`Os dados já são os mais recentes (${fmtData(D.gerado_em.slice(0, 10)).slice(0, 5)} ${D.gerado_em.slice(11, 16)})`);
    } catch (e) {
      toast('Não foi possível buscar os dados: ' + e.message);
    } finally {
      girando(false);
    }
  }
  function aoClicarAtualizar() {
    if (modo === 'arquivo') location.reload();
    else if (modo === 'local') atualizarLocal();
    else atualizarPublico();
  }

  async function init() {
    let tema = 'light';
    try { tema = localStorage.getItem('tema') || 'light'; } catch (e) { /* ok */ }
    aplicarTema(tema);
    $('#btn-tema').addEventListener('click', () => aplicarTema(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    try {
      if (typeof echarts === 'undefined') throw new Error('Não foi possível carregar a biblioteca de gráficos (ECharts). O painel precisa de internet na primeira abertura para baixar o ECharts e a fonte Inter.');
      D = await carregar();
      validar(D);
    } catch (e) { const box = $('#erro'); box.hidden = false; box.textContent = e.message; return; }
    modo = await detectarModo();
    montarControlesBase();
    montarControles();
    renderKpis();
    ativarAba('series');
    window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));
  }

  function chips(container, opcoes, conjunto, cor, aoMudar) {
    container.replaceChildren(...Object.entries(opcoes).map(([chave, rotulo]) => {
      const b = el('button', { type: 'button', class: 'chip', style: `--cor:${cor(chave)}`, 'aria-pressed': String(conjunto.has(chave)) }, el('span', { class: 'ponto' }), rotulo);
      b.addEventListener('click', () => {
        if (conjunto.has(chave)) conjunto.delete(chave); else conjunto.add(chave);
        b.setAttribute('aria-pressed', String(conjunto.has(chave)));
        aoMudar();
      });
      return b;
    }));
  }
  function segmentosJanela(container, chave, aoMudar) {
    container.replaceChildren(...Object.entries(JANELAS).map(([j, rotulo]) => {
      const b = el('button', { type: 'button', class: 'seg', 'aria-pressed': String(estado[chave] === j), text: rotulo });
      b.addEventListener('click', () => { estado[chave] = j; $$('.seg', container).forEach((x) => x.setAttribute('aria-pressed', String(x === b))); aoMudar(); });
      return b;
    }));
  }
  function montarControles() {
    // seletor de séries agrupado
    const lista = $('#sel-lista');
    for (const g of ORDEM_GRUPOS) {
      const ids = Object.keys(D.series).filter((id) => D.series[id].grupo === g);
      if (!ids.length) continue;
      lista.append(el('div', { class: 'sel-grupo', text: GRUPOS[g] }));
      for (const id of ids) {
        const cb = el('input', { type: 'checkbox', value: id });
        cb.checked = estado.selecionadas.includes(id);
        cb.addEventListener('change', () => {
          if (cb.checked) {
            if (estado.selecionadas.length >= MAX_SERIES) {
              cb.checked = false;
              $('#sel-resumo').textContent = `Máximo de ${MAX_SERIES} séries`;
              setTimeout(atualizarResumoSel, 2000);
              return;
            }
            estado.selecionadas.push(id);
          } else estado.selecionadas = estado.selecionadas.filter((x) => x !== id);
          atualizarResumoSel();
          renderSeries();
        });
        lista.append(el('label', { style: `--cor:${corGrupo(g)}` }, cb, el('span', { class: 'ponto' }), D.series[id].nome));
      }
    }
    atualizarResumoSel();
    document.addEventListener('click', (ev) => { const det = $('.seletor'); if (det.open && !det.contains(ev.target)) det.open = false; });
    $$('[data-periodo]').forEach((b) => b.addEventListener('click', () => { estado.periodo = b.dataset.periodo; $$('[data-periodo]').forEach((x) => x.setAttribute('aria-pressed', String(x === b))); renderSeries(); }));
    $$('[data-modo]').forEach((b) => b.addEventListener('click', () => { if (b.disabled) return; estado.modo = b.dataset.modo; renderSeries(); }));
    chips($('#chips-cat'), CATEGORIAS, estado.categorias, corCat, renderSeries);
    montarControlesCerebro();
    montarControlesHeat();
    montarControlesTimeline();
  }
  function atualizarResumoSel() { $('#sel-resumo').textContent = `Séries (${estado.selecionadas.length}) ▾`; }
  // ---------- aba Previsões ----------
  const TRAJ = [['selic', 'Selic'], ['ipca', 'IPCA 12m'], ['cambio', 'Dólar'], ['pib', 'PIB']];
  const COR_TRAJ = { selic: 'juros', ipca: 'inflacao', cambio: 'cambio', pib: 'macro' };
  const TAG_SINAL = { copom: 'Copom', selic: 'Selic', revisao: 'Revisão', juro_real: 'Juro real', cambio: 'Câmbio', fomc: 'Agenda', ipca: 'Agenda', acerto: 'Retrospectiva' };
  const COR_AGENDA = { copom: 'copom', fomc: 'fomc', ipca: 'plano' };
  const TEXTO_SEM_FOCUS = 'Previsões indisponíveis: o Boletim Focus não pôde ser baixado nesta atualização.';
  const DICA_SEM_FOCUS = ' Rode python abrir_painel.py com internet para tentar de novo.';

  // "**x**" vira <strong>, sem innerHTML.
  function textoRico(texto) {
    const s = el('span');
    texto.split('**').forEach((parte, i) => s.append(i % 2 ? el('strong', { text: parte }) : document.createTextNode(parte)));
    return s;
  }

  function renderPrevisoes() {
    const P = D.previsoes || null;
    const hoje = D.gerado_em.slice(0, 10);
    const semFocus = !P || !P.focus_data;
    $('#prev-vazio').hidden = !semFocus;
    $('#prev-vazio').textContent = TEXTO_SEM_FOCUS + (modo !== 'publico' ? DICA_SEM_FOCUS : '');
    $('#focus-info').textContent = semFocus ? '' : `Boletim Focus de ${fmtData(P.focus_data)}` + (P.respondentes ? ` · ${P.respondentes} instituições` : '');
    $('#sinais').replaceChildren(...((P && P.sinais) || []).map((s) =>
      el('div', { class: 'sinal ' + s.nivel }, el('span', { class: 'sinal-tag', text: TAG_SINAL[s.tipo] || s.tipo }), textoRico(s.texto))));
    renderAgenda((P && P.agenda) || [], hoje);
    $('#card-traj').hidden = semFocus;
    if (!semFocus) renderTrajetoria(P.trajetorias, hoje);
  }

  function renderAgenda(agenda, hoje) {
    const prox = agenda.filter((a) => a.data >= hoje).slice(0, 8);
    $('#agenda-vazia').hidden = prox.length > 0;
    $('#agenda').replaceChildren(...prox.map((a) => {
      const dias = Math.round((Date.parse(a.data) - Date.parse(hoje)) / 864e5);
      let sub = null;
      if (a.espera) {
        const d = a.espera.dif;
        const v = d === 0 ? 'manter' : (d < 0 ? `cortar ${fmt(-d)}` : `subir ${fmt(d)}`);
        sub = el('div', { class: 'ag-sub', text: `${a.reuniao} · mercado espera ${v} → ${fmt(a.espera.mediana)}%` });
      } else if (a.contexto) sub = el('div', { class: 'ag-sub', text: a.contexto });
      return el('tr', {},
        el('td', { class: 'ag-data', text: fmtData(a.data).slice(0, 5) }),
        el('td', {}, el('span', { class: 'ag-tipo', style: `--cor:${corCat(COR_AGENDA[a.tipo])}` }), a.titulo, sub),
        el('td', { class: 'ag-dias', text: dias === 0 ? 'hoje' : `em ${dias} d` }));
    }));
  }

  function renderTrajetoria(trajetorias, hoje) {
    const seg = $('#seg-traj');
    if (!seg.children.length) {
      for (const [k, nome] of TRAJ) {
        seg.append(el('button', { type: 'button', class: 'seg', 'data-traj': k, text: nome, onclick: () => { estado.traj = k; renderPrevisoes(); } }));
      }
    }
    $$('[data-traj]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.traj === estado.traj)));
    const t = trajetorias[estado.traj];
    const c = grafico('chart-traj');
    if (!t || !t.proj.length) {
      $('#leg-traj').textContent = '';
      $('#leg-prev12').hidden = true;
      c.setOption({ title: { text: 'Sem projeções do Focus para este indicador', left: 'center', top: 'middle', textStyle: { color: cssVar('--muted'), fontWeight: 400, fontSize: 14 } } }, true);
      return;
    }
    const cor = corGrupo(COR_TRAJ[estado.traj]);
    const inicio = anosAtras(hoje, 3);
    const hist = t.serie_hist && D.series[t.serie_hist] ? pontos(t.serie_hist).filter((p) => p[0] >= inicio && p[1] != null) : [];
    const ultimo = hist.length ? hist[hist.length - 1] : null;
    // A projeção parte do último ponto real para a linha não ter buraco.
    const proj = (ultimo ? [[ultimo[0], ultimo[1], ultimo[1], ultimo[1], null, 'hoje']] : []).concat(t.proj);
    const degrau = estado.traj === 'selic' && t.proj[0] && t.proj[0][5].startsWith('R') ? 'end' : false;
    // O que a pesquisa de ~12 meses atrás previa, partindo do valor real daquela data.
    const p12 = t.proj_12m;
    const ini12 = p12 && t.serie_hist && D.series[t.serie_hist] ? valorEm(t.serie_hist, p12.data_pesquisa) : null;
    const prev12 = p12 ? (ini12 != null ? [[p12.data_pesquisa, ini12, null]] : []).concat(p12.pontos) : [];
    const degrau12 = p12 && p12.pontos.length && String(p12.pontos[0][2]).startsWith('R') ? 'end' : false;
    $('#leg-prev12').hidden = !prev12.length;
    if (prev12.length) $('#leg-prev12').textContent = `Cinza tracejado: o que o Focus previa em ${fmtData(p12.data_pesquisa)}.`;
    $('#leg-traj').textContent = `${t.nome} · ${t.unidade}` + (t.serie_hist ? '' : ' · sem histórico no painel, só projeções');
    c.setOption({
      textStyle: textoBase(), animation: false,
      grid: { left: 52, right: 20, top: 24, bottom: 30 },
      tooltip: Object.assign(tooltipBase(), {
        trigger: 'axis',
        formatter: (ps) => {
          const p = ps.find((q) => q.seriesId === 'proj' && q.data[4] != null) || ps.find((q) => q.seriesId === 'hist');
          const q12 = ps.find((q) => q.seriesId === 'prev12' && q.data[2] != null);
          if (!p && !q12) return '';
          const caixa = el('div', { class: 'tt' });
          if (p) {
            const d = p.data;
            caixa.append(el('div', { class: 'tt-titulo', text: p.seriesId === 'proj' ? `${d[5]} · ${fmtData(d[0])}` : fmtData(String(d[0]).slice(0, 10)) }),
              el('div', {}, el('strong', { text: `${fmt(d[1])} ${t.unidade}` }), el('span', { class: 'tt-nome', text: p.seriesId === 'proj' ? ' mediana' : '' })));
            if (p.seriesId === 'proj') caixa.append(el('div', { class: 'tt-nome', text: `Faixa ${fmt(d[2])} a ${fmt(d[3])} · ${d[4]} respostas` }));
          } else {
            caixa.append(el('div', { class: 'tt-titulo', text: `${q12.data[2]} · ${fmtData(q12.data[0])}` }));
          }
          if (q12) caixa.append(el('div', { class: 'tt-nome', text: `Previsto em ${fmtData(p12.data_pesquisa)} para ${q12.data[2]}: ${fmt(q12.data[1])} ${t.unidade}` }));
          return caixa;
        },
      }),
      xAxis: Object.assign({ type: 'time' }, eixoBase(), { splitLine: { show: false } }),
      yAxis: Object.assign({ type: 'value', scale: true }, eixoBase(), { axisLine: { show: false }, axisLabel: { color: cssVar('--muted'), fontSize: 11, formatter: (v) => v.toLocaleString('pt-BR') } }),
      series: [
        { id: 'hist', type: 'line', data: hist, showSymbol: false, sampling: 'lttb', lineStyle: { width: 2, color: cor }, itemStyle: { color: cor },
          markLine: ultimo ? { symbol: 'none', silent: true, label: { formatter: 'hoje', color: cssVar('--muted'), fontSize: 11 }, lineStyle: { color: cssVar('--muted'), type: 'dotted' }, data: [{ xAxis: ultimo[0] }] } : undefined },
        // Faixa: base invisível no mínimo + área com a diferença até o máximo.
        { id: 'faixa-base', type: 'line', data: proj.map((p) => [p[0], p[2]]), stack: 'faixa', step: degrau, lineStyle: { opacity: 0 }, showSymbol: false, silent: true, tooltip: { show: false } },
        { id: 'faixa', type: 'line', data: proj.map((p) => [p[0], p[3] - p[2]]), stack: 'faixa', step: degrau, lineStyle: { opacity: 0 }, showSymbol: false, silent: true, areaStyle: { color: cor, opacity: 0.16 }, tooltip: { show: false } },
        { id: 'proj', type: 'line', data: proj, step: degrau, showSymbol: true, symbolSize: 6, lineStyle: { width: 2, type: 'dashed', color: cor }, itemStyle: { color: cor } },
        { id: 'prev12', type: 'line', data: prev12, step: degrau12, showSymbol: true, symbolSize: 4, z: 1,
          lineStyle: { width: 1.5, type: 'dashed', color: cssVar('--muted') }, itemStyle: { color: cssVar('--muted') } },
      ],
    }, true);
  }
  RENDER.previsoes = renderPrevisoes;

  // ---------- aba Séries ----------
  function renderSeries() {
    const ids = estado.selecionadas.filter((id) => D.series[id]);
    if (!ids.length) {
      $('#evento-detalhe').hidden = true;
      grafico('chart-series').setOption({ title: { text: 'Selecione ao menos uma série', left: 'center', top: 'middle', textStyle: { color: cssVar('--muted'), fontWeight: 400, fontSize: 14 } } }, true);
      $('#modo-nivel').disabled = true;
      $('#aviso-modo').hidden = true;
      return;
    }
    // Unidades da mesma família dividem um eixo; o Nível aceita até duas famílias (eixo esquerdo e direito).
    const familias = [...new Set(ids.map((id) => familiaEixo(D.series[id].unidade)))];
    const misto = familias.length > 2;
    const modo = misto ? 'variacao' : estado.modo;
    const doisEixos = modo === 'nivel' && familias.length === 2;
    const nomeEixo = (f) => [...new Set(ids.filter((id) => familiaEixo(D.series[id].unidade) === f).map((id) => D.series[id].unidade))].join(' · ');
    estado.modoAtivo = modo;
    $('#modo-nivel').disabled = misto;
    $('#modo-nivel').title = misto ? 'Nível mostra no máximo duas unidades (uma em cada eixo). Tire séries para liberar.' : '';
    $('#aviso-modo').hidden = !misto;
    $$('[data-modo]').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.modo === modo)));

    const ultimo = ids.reduce((m, id) => (D.series[id].fim > m ? D.series[id].fim : m), '0000-00-00');
    const anos = PERIODOS[estado.periodo];
    const inicio = anos ? anosAtras(ultimo, anos) : '0000-00-00';

    const series = ids.map((id, i) => {
      const s = D.series[id];
      let dados = pontos(id).filter((p) => p[0] >= inicio);
      if (modo === 'variacao' && dados.length) {
        const base = dados.find((p) => p[1] != null && (s.var_tipo !== 'pct' || p[1] !== 0));
        // O terceiro elemento guarda o valor original para o tooltip; o ECharts desenha só x e y.
        dados = !base ? [] : dados.map(([d, v]) => [d, s.var_tipo === 'pct' ? (v / base[1] - 1) * 100 : v - base[1], v]);
      }
      const yAxisIndex = doisEixos && familiaEixo(s.unidade) === familias[1] ? 2 : 0;
      return { id, name: s.nome, type: 'line', yAxisIndex, showSymbol: false, symbolSize: 8, sampling: 'lttb', data: dados, lineStyle: { width: 2, color: corSlot(i) }, itemStyle: { color: corSlot(i) }, emphasis: { focus: 'series' } };
    });
    const eventos = D.eventos.filter((e) => estado.categorias.has(e.categoria) && e.data >= inicio && e.data <= ultimo);
    series.push({
      name: 'Eventos', type: 'scatter', xAxisIndex: 1, yAxisIndex: 1, symbolSize: 10,
      data: eventos.map((e) => ({ value: [e.data, ORDEM_CAT.indexOf(e.categoria)], evento: e, itemStyle: { color: corCat(e.categoria), borderColor: cssVar('--card'), borderWidth: 2 } })),
    });

    const c = grafico('chart-series');
    c.setOption({
      textStyle: textoBase(), animation: false,
      legend: { data: ids.map((id) => D.series[id].nome), top: 0, type: 'scroll', textStyle: { color: cssVar('--text-2') }, icon: 'path://M0,5 L20,5 L20,7 L0,7 Z', itemWidth: 18 },
      grid: [{ left: 60, right: doisEixos ? 64 : 24, top: 44, height: '58%' }, { left: 60, right: doisEixos ? 64 : 24, top: '76%', height: 44 }],
      axisPointer: { link: [{ xAxisIndex: 'all' }], lineStyle: { color: cssVar('--muted') } },
      tooltip: Object.assign(tooltipBase(), { trigger: 'axis', formatter: tooltipSeries }),
      xAxis: [
        Object.assign({ type: 'time' }, eixoBase(), { splitLine: { show: false } }),
        Object.assign({ type: 'time', gridIndex: 1 }, eixoBase(), { axisLabel: { show: false }, splitLine: { show: false }, axisLine: { show: false } }),
      ],
      yAxis: [
        Object.assign({ type: 'value', scale: true, name: modo === 'variacao' ? 'Variação desde o início (% ou p.p.)' : nomeEixo(familias[0]), nameTextStyle: { color: cssVar('--muted'), align: 'left' } }, eixoBase(), { axisLine: { show: false } }),
        { type: 'value', gridIndex: 1, min: -1, max: ORDEM_CAT.length, show: false },
      ].concat(doisEixos ? [Object.assign({ type: 'value', scale: true, position: 'right', name: nomeEixo(familias[1]), nameTextStyle: { color: cssVar('--muted'), align: 'right' } }, eixoBase(), { axisLine: { show: false }, splitLine: { show: false } })] : []),
      dataZoom: [
        { type: 'inside', xAxisIndex: [0, 1] },
        { type: 'slider', xAxisIndex: [0, 1], bottom: 6, height: 22, borderColor: 'transparent', backgroundColor: cssVar('--bg'), fillerColor: 'rgba(120,120,140,.18)', handleStyle: { color: cssVar('--muted') }, textStyle: { color: cssVar('--muted') }, dataBackground: { lineStyle: { color: cssVar('--muted') }, areaStyle: { color: cssVar('--grid') } } },
      ],
      series,
    }, true);
    c.on('click', (p) => { if (p.seriesType === 'scatter' && p.data && p.data.evento) mostrarEvento(p.data.evento); });
  }

  function tooltipSeries(params) {
    const lista = Array.isArray(params) ? params : [params];
    const caixa = el('div', { class: 'tt' });
    const linhas = lista.filter((p) => p.seriesType === 'line');
    if (linhas.length) {
      caixa.append(el('div', { class: 'tt-titulo', text: fmtData(String(linhas[0].value[0]).slice(0, 10)) }));
      for (const p of linhas) {
        const id = p.seriesId;
        const v = p.value[1];
        const s = id && D.series[id];
        const variacao = estado.modoAtivo === 'variacao' && s;
        const texto = s ? `${fmt(variacao ? p.value[2] : v, casasDe(id))} ${s.unidade}` : fmt(v, 2);
        caixa.append(el('div', { class: 'tt-linha' }, el('span', { class: 'tt-chave', style: `background:${p.color}` }), el('strong', { text: texto }),
          variacao ? el('span', { class: 'tt-var', text: `(${fmtSinal(v)}${unidadeVar(id)})` }) : null,
          el('span', { class: 'tt-nome', text: p.seriesName })));
      }
    }
    for (const p of lista.filter((q) => q.seriesType === 'scatter' && q.data && q.data.evento)) {
      const e = p.data.evento;
      caixa.append(el('div', { class: 'tt-evento' }, el('div', { class: 'tt-titulo', text: `${fmtData(e.data)} · ${e.titulo}` }), el('div', { class: 'tt-desc', text: e.descricao })));
    }
    return caixa;
  }

  function tabelaImpactos(e) {
    const corpo = el('tbody');
    for (const id of e.series) {
      if (!D.series[id]) continue;
      const i30 = impacto(id, e.data, 30), i90 = impacto(id, e.data, 90);
      corpo.append(el('tr', {}, el('td', { text: D.series[id].nome }), el('td', { class: classeVar(i30), text: fmtVar(id, i30) }), el('td', { class: classeVar(i90), text: fmtVar(id, i90) })));
    }
    return el('table', { class: 'impactos' }, el('thead', {}, el('tr', {}, el('th', { text: 'Série' }), el('th', { text: '30 dias' }), el('th', { text: '90 dias' }))), corpo);
  }
  function cabecalhoEvento(e) {
    return el('div', { class: 'evento-cab' },
      el('time', { datetime: e.data, text: fmtData(e.data) }),
      el('span', { class: 'chip cat', style: `--cor:${corCat(e.categoria)}`, text: CATEGORIAS[e.categoria] || e.categoria }),
      e.auto ? el('span', { class: 'chip', text: 'detectado na série' }) : null);
  }
  function mostrarEvento(e) {
    const box = $('#evento-detalhe');
    box.hidden = false;
    box.replaceChildren(cabecalhoEvento(e), el('h3', { text: e.titulo }), el('p', { text: e.descricao }), tabelaImpactos(e));
    box.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }
  RENDER.series = renderSeries;

  // ---------- aba Cérebro ----------
  function montarControlesCerebro() {
    segmentosJanela($('[data-janela-grupo=cerebro]'), 'janela', renderCerebro);
    const slider = $('#corte');
    slider.addEventListener('input', () => { estado.corte = Number(slider.value); $('#corte-valor').textContent = fmt(estado.corte, 2); renderCerebro(); });
    chips($('#chips-grupo'), GRUPOS, estado.gruposCerebro, corGrupo, renderCerebro);
  }

  function renderCerebro() {
    const domCerebro = document.getElementById('chart-cerebro');
    const escala = Math.max(0.6, Math.min(1.8, Math.sqrt(Math.max(1, domCerebro.clientWidth * domCerebro.clientHeight)) / 580));
    const visivel = (id) => D.series[id] && estado.gruposCerebro.has(D.series[id].grupo);
    const ar = (D.arestas[estado.janela] || []).filter((a) => Math.abs(a.r) >= estado.corte && visivel(a.a) && visivel(a.b));
    const peso = {};
    for (const a of ar) { peso[a.a] = (peso[a.a] || 0) + Math.abs(a.r); peso[a.b] = (peso[a.b] || 0) + Math.abs(a.r); }
    const ids = ((D.correlacao[estado.janela] || {}).ids || []).filter(visivel);
    const maxPeso = Math.max(0.01, ...Object.values(peso));
    const nodes = ids.map((id) => ({
      id, name: D.series[id].nome, category: ORDEM_GRUPOS.indexOf(D.series[id].grupo), value: peso[id] || 0,
      symbolSize: 12 + 36 * ((peso[id] || 0) / maxPeso), itemStyle: { opacity: peso[id] ? 1 : 0.35 },
    }));
    const links = ar.map((a) => ({ source: a.a, target: a.b, value: a.r, n: a.n, lineStyle: { width: 1 + 6 * Math.abs(a.r), color: a.r > 0 ? cssVar('--pos') : cssVar('--neg'), opacity: 0.7, curveness: 0.12 } }));
    const c = grafico('chart-cerebro');
    c.setOption({
      textStyle: textoBase(),
      tooltip: Object.assign(tooltipBase(), { formatter: tooltipCerebro }),
      legend: { data: ORDEM_GRUPOS.map((g) => GRUPOS[g]), top: 0, textStyle: { color: cssVar('--text-2') } },
      series: [{
        type: 'graph', layout: 'force', roam: true, draggable: true, data: nodes, links,
        categories: ORDEM_GRUPOS.map((g) => ({ name: GRUPOS[g], itemStyle: { color: corGrupo(g) } })),
        label: { show: true, position: 'right', color: cssVar('--text'), fontSize: 11 },
        force: { repulsion: 230 * escala, gravity: 0.22, edgeLength: [40 * escala, 160 * escala], friction: 0.2 },
        top: 44,
        emphasis: { focus: 'adjacency', lineStyle: { opacity: 1 } },
        lineStyle: { opacity: 0.7 }, edgeSymbol: ['none', 'none'],
        selectedMode: 'single',
        select: { itemStyle: { borderColor: cssVar('--text'), borderWidth: 3 }, label: { fontWeight: 'bold' } },
      }],
    }, true);
    c.on('click', (p) => {
      if (p.dataType !== 'node') return;
      estado.noSelecionado = p.data.id;
      c.dispatchAction({ type: 'downplay', seriesIndex: 0 });
      c.dispatchAction({ type: 'highlight', seriesIndex: 0, dataIndex: p.dataIndex });
      renderPainelNo();
    });
    if (estado.noSelecionado && ids.includes(estado.noSelecionado)) {
      c.dispatchAction({ type: 'select', seriesIndex: 0, dataIndex: ids.indexOf(estado.noSelecionado) });
    }
    $('#n-arestas').textContent = `${plural(ar.length, 'conexão', 'conexões')} · ${plural(nodes.length, 'variável', 'variáveis')} · janela ${JANELAS[estado.janela].toLowerCase()}`;
    renderPainelNo();
  }

  function tooltipCerebro(p) {
    const caixa = el('div', { class: 'tt' });
    if (p.dataType === 'edge') {
      caixa.append(el('div', { class: 'tt-titulo', text: `${D.series[p.data.source].nome} ↔ ${D.series[p.data.target].nome}` }),
        el('div', {}, el('strong', { text: 'r = ' + fmt(p.data.value, 2) }), el('span', { class: 'tt-nome', text: ` · ${p.data.n} meses` })));
    } else {
      const s = D.series[p.data.id];
      caixa.append(el('div', { class: 'tt-titulo', text: s.nome }), el('div', { class: 'tt-nome', text: `${GRUPOS[s.grupo]} · ${s.unidade} · desde ${fmtData(s.inicio)}` }),
        el('div', { text: `Conectividade ${fmt(p.data.value, 2)}` }));
    }
    return caixa;
  }

  function renderPainelNo() {
    const box = $('#painel-no');
    const m = D.correlacao[estado.janela];
    const id = estado.noSelecionado;
    if (!id || !m || !m.ids.includes(id)) { box.replaceChildren(el('h3', { text: 'Correlações' }), el('p', { class: 'muted', text: 'Clique num nó para ver com quem ele se correlaciona nesta janela.' })); return; }
    const i = m.ids.indexOf(id);
    const linhas = m.ids.map((outro, j) => ({ outro, r: m.matriz[i][j], n: m.n[i][j] })).filter((x) => x.outro !== id && x.r != null).sort((a, b) => Math.abs(b.r) - Math.abs(a.r));
    box.replaceChildren(
      el('h3', { text: D.series[id].nome }),
      el('p', { class: 'muted', text: `${linhas.length} pares com pelo menos 24 meses em comum · janela ${JANELAS[estado.janela].toLowerCase()}` }),
      ...linhas.map((x) => {
        const barra = el('div', { class: 'corr-barra' });
        const pct = Math.abs(x.r) * 50;
        barra.append(el('i', { style: `left:${x.r < 0 ? 50 - pct : 50}%;width:${pct}%;background:${x.r > 0 ? cssVar('--pos') : cssVar('--neg')}` }));
        return el('div', { class: 'corr-linha', title: `${x.n} meses` },
          el('div', { class: 'corr-nome' }, el('span', { class: 'ponto', style: `width:8px;height:8px;border-radius:50%;background:${corGrupo(D.series[x.outro].grupo)};flex:none` }), el('span', { text: D.series[x.outro].nome }), barra),
          el('div', { class: 'corr-valor ' + classeVar(x.r), text: fmtSinal(x.r, 2) }));
      }));
  }
  RENDER.cerebro = renderCerebro;

  // ---------- aba Correlações ----------
  function montarControlesHeat() { segmentosJanela($('[data-janela-grupo=heat]'), 'janelaHeat', renderHeat); }

  function renderHeat() {
    const m = D.correlacao[estado.janelaHeat];
    const dom = document.getElementById('chart-heat');
    if (!m || !m.ids.length) { dom.textContent = 'Sem dados para esta janela.'; return; }
    const ordem = m.ids.map((_, i) => i).sort((a, b) => ORDEM_GRUPOS.indexOf(D.series[m.ids[a]].grupo) - ORDEM_GRUPOS.indexOf(D.series[m.ids[b]].grupo) || a - b);
    const ids = ordem.map((i) => m.ids[i]);
    const nomes = ids.map((id) => D.series[id].nome);
    const data = [];
    ordem.forEach((oi, x) => ordem.forEach((oj, y) => {
      const r = m.matriz[oi][oj];
      if (r != null) data.push({ value: [x, y, r], n: m.n[oi][oj], label: { color: Math.abs(r) > 0.55 ? '#ffffff' : cssVar('--text') } });
    }));
    const tam = ids.length;
    dom.style.height = Math.max(520, Math.min(980, tam * 28 + 200)) + 'px';
    const c = grafico('chart-heat');
    c.setOption({
      textStyle: textoBase(), animation: false,
      tooltip: Object.assign(tooltipBase(), {
        position: 'top',
        formatter: (p) => el('div', { class: 'tt' }, el('div', { class: 'tt-titulo', text: `${nomes[p.value[0]]} × ${nomes[p.value[1]]}` }), el('div', {}, el('strong', { text: 'r = ' + fmt(p.value[2], 2) }), el('span', { class: 'tt-nome', text: ` · ${p.data.n} meses` }))),
      }),
      grid: { left: 190, right: 24, top: 12, bottom: 170 },
      xAxis: Object.assign({ type: 'category', data: nomes }, eixoBase(), { splitLine: { show: false }, axisLabel: { rotate: 55, fontSize: 10, color: cssVar('--muted') } }),
      yAxis: Object.assign({ type: 'category', data: nomes, inverse: true }, eixoBase(), { splitLine: { show: false }, axisLabel: { fontSize: 10, color: cssVar('--muted') } }),
      visualMap: { min: -1, max: 1, calculable: true, orient: 'horizontal', left: 'center', bottom: 4, itemWidth: 12, itemHeight: 180, textStyle: { color: cssVar('--muted') }, inRange: { color: [cssVar('--neg'), cssVar('--mid'), cssVar('--pos')] } },
      series: [{ type: 'heatmap', data, label: { show: tam <= 24, fontSize: 9, formatter: (p) => p.value[2].toFixed(2) }, itemStyle: { borderColor: cssVar('--card'), borderWidth: 2 }, emphasis: { itemStyle: { borderColor: cssVar('--text') } } }],
    }, true);
  }
  RENDER.correlacoes = renderHeat;

  // ---------- aba Linha do tempo ----------
  function montarControlesTimeline() {
    chips($('#chips-timeline'), CATEGORIAS, estado.filtroCat, corCat, renderTimeline);
    const busca = $('#busca');
    let timer = null;
    busca.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { estado.busca = busca.value; renderTimeline(); }, 150); });
  }

  function renderTimeline() {
    const lista = $('#lista-eventos');
    const q = estado.busca.trim().toLowerCase();
    const evs = D.eventos
      .filter((e) => estado.filtroCat.has(e.categoria) && (!q || (e.titulo + ' ' + e.descricao).toLowerCase().includes(q)))
      .slice().sort((a, b) => b.data.localeCompare(a.data));
    $('#n-eventos').textContent = plural(evs.length, 'evento', 'eventos');
    lista.replaceChildren(...evs.map(cardEvento));
    if (!evs.length) lista.append(el('p', { class: 'muted', text: 'Nenhum evento com esses filtros.' }));
  }

  function cardEvento(e) {
    return el('article', { class: 'evento' }, cabecalhoEvento(e), el('h3', { text: e.titulo }), el('p', { text: e.descricao }), tabelaImpactos(e));
  }
  RENDER.timeline = renderTimeline;

  init();
})();
