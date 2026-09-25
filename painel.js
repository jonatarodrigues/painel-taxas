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
  const charts = {};
  const estado = {
    aba: 'series',
    selecionadas: ['selic_meta', 'ipca_12m', 'usd_brl'],
    modo: 'base100',
    periodo: '10a',
    categorias: new Set(ORDEM_CAT),
    janela: 'tudo',
    corte: 0.3,
    gruposCerebro: new Set(ORDEM_GRUPOS),
    noSelecionado: null,
    janelaHeat: 'tudo',
    filtroCat: new Set(ORDEM_CAT),
    busca: '',
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
  const unidadeVar = (id) => D.series[id].var_tipo === 'pct' ? '%' : ' p.p.';
  const classeVar = (v) => v == null ? 'muted' : (v > 0 ? 'var-pos' : v < 0 ? 'var-neg' : '');
  const fmtVar = (id, v) => v == null ? '—' : fmtSinal(v) + unidadeVar(id);
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

  // stubs substituídos nas Tasks 11–14
  const emConstrucao = (idEl) => () => { const d = document.getElementById(idEl); if (d) d.textContent = 'em construção'; };
  RENDER.series = emConstrucao('chart-series');
  RENDER.cerebro = emConstrucao('chart-cerebro');
  RENDER.correlacoes = emConstrucao('chart-heat');
  RENDER.timeline = emConstrucao('lista-eventos');

  // ---------- tema ----------
  function aplicarTema(t) {
    document.documentElement.dataset.theme = t;
    try { localStorage.setItem('tema', t); } catch (e) { /* armazenamento indisponível */ }
    $('#btn-tema').textContent = t === 'dark' ? '☀ Claro' : '☾ Escuro';
    if (D) { renderKpis(); renderAba(); }
  }

  // ---------- carregamento ----------
  async function carregar() {
    if (/^https?:$/.test(location.protocol)) {
      try {
        const r = await fetch('dados.json', { cache: 'no-store' });
        if (r.ok) return await r.json();
      } catch (e) { /* cai no fallback */ }
    }
    if (window.DADOS) return window.DADOS;
    throw new Error('Não encontrei dados.json nem dados.js. Rode "python atualizar.py" nesta pasta e recarregue.');
  }
  function validar(d) {
    for (const k of ['series', 'correlacao', 'arestas', 'eventos']) {
      if (!d || typeof d[k] !== 'object' || d[k] === null) throw new Error(`dados.json inválido: falta a chave "${k}"`);
    }
  }

  function montarControlesBase() {
    $$('[role=tab]').forEach((b) => b.addEventListener('click', () => ativarAba(b.dataset.aba)));
    if (D.avisos && D.avisos.length) {
      const b = $('#btn-avisos'), box = $('#avisos');
      b.hidden = false;
      $('#n-avisos').textContent = D.avisos.length;
      box.replaceChildren(...D.avisos.map((a) => el('div', { text: a })));
      b.addEventListener('click', () => { box.hidden = !box.hidden; });
    }
    $('#atualizado').textContent = 'Atualizado em ' + fmtData(D.gerado_em.slice(0, 10)) + ' às ' + D.gerado_em.slice(11, 16);
  }

  async function init() {
    let tema = 'dark';
    try { tema = localStorage.getItem('tema') || 'dark'; } catch (e) { /* ok */ }
    aplicarTema(tema);
    $('#btn-tema').addEventListener('click', () => aplicarTema(document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'));
    try { D = await carregar(); validar(D); } catch (e) { const box = $('#erro'); box.hidden = false; box.textContent = e.message; return; }
    montarControlesBase();
    if (typeof montarControles === 'function') montarControles();
    renderKpis();
    ativarAba('series');
    window.addEventListener('resize', () => Object.values(charts).forEach((c) => c.resize()));
  }

  // Ponto de extensão das Tasks 11–14: cada uma define funções aqui e registra em RENDER.
  let montarControles = null;
  // @@ABAS@@

  init();
})();
