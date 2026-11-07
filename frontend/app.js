/* BotBene · painel (JavaScript simples, sem build). Fala com o backend em /api e /ws/live. */
(function () {
  'use strict';

  // Ordem fixa: a cor segue o script, nunca a posição na lista.
  var STRATEGY_ORDER = ['ldp_v13', 'ldp_v13_linhas', 'wiki_pro_v21', 'ldp_apostila', 'retracao_comando',
    'retracao_lote', 'reversao_forca', 'reversao_indecisao', 'score_ldp'];
  var SCORE = 'score_ldp';  // o combo: várias estratégias e padrões juntos decidem a entrada
  var LABELS = {
    ldp_v13: 'LDP v1.3', ldp_v13_linhas: 'LDP v1.3 + regra das linhas', wiki_pro_v21: 'WIKI PRO V2.1',
    ldp_apostila: 'Apostila · marcações', retracao_comando: 'Apostila · retração no comando',
    retracao_lote: 'Estudo · retração no lote', reversao_forca: 'Estudo · reversão A (força trava)',
    reversao_indecisao: 'Estudo · reversão B (força rompe indecisão)', score_ldp: 'Score LDP v1 (combo)',
    manual: 'Entrada manual'
  };
  var MANUAL = 'manual';  // ordem que você fez na mão: não é estratégia e não entra nas estatísticas delas
  var TRIGGER_LABELS = { retracao: 'Retração', reversao: 'Reversão', throwback: 'Throwback', comando: 'Retração no comando', score: 'Score' };
  var CONF_LABELS = {
    gatilho: 'gatilho', forca: 'marcação forte', contexto: 'nova alta/baixa + nova posição',
    espaco: 'espaço até a barreira', tendencia: 'tendência EMA',
    marcacao: 'comando ou taxa dividida', indecisao: 'dupla/tripla posição',
    registro: 'primeiro registro + nova posição', juntas: 'marcações juntas',
    nao_rompeu: 'comando dentro das 10 velas', recorrencia: 'recorrência do par'
  };
  var CLASS_LABELS = {
    comando_n1: 'Comando nível 1 (careca)', comando_unico: 'Comando único (nível 2)',
    expirado: 'Expirado / fim de taxa (nível 3)', vela_de_forca: 'Vela de força',
    indecisao: 'Indecisão', doji: 'Doji (sem cor)'
  };
  var STRUCT_LABELS = {
    comando_n1: 'Comando nível 1', comando_unico: 'Comando único', expirado: 'Expirado',
    vela_de_forca: 'Vela de força', pavio_grande: 'Pavio grande',
    td_n1: 'Taxa dividida N1', td_n2: 'Taxa dividida N2', td_n3: 'Taxa dividida N3',
    td_intermediaria: 'TD intermediária', td_forte: 'TD forte', td_media: 'TD média', td_fraca: 'TD fraca',
    divisao_preco: 'Divisão de preço', td_topo_n1: 'TD de topo N1', td_topo_n2: 'TD de topo N2',
    td_fundo_n1: 'TD de fundo N1', td_fundo_n2: 'TD de fundo N2', dupla_posicao: 'Dupla posição',
    tripla_posicao: 'Tripla posição', futuro_alta: 'Futuro de alta', futuro_baixa: 'Futuro de baixa',
    nova_alta: 'Nova alta', nova_baixa: 'Nova baixa', nova_posicao: 'Nova posição',
    nano_lote: 'Nano-lote', defesa: 'Defesa'
  };
  var RESULT_INFO = {
    win: { icon: '✓', text: 'Win' }, loss: { icon: '✗', text: 'Loss' }, empate: { icon: '=', text: 'Empate' },
    pendente: { icon: '…', text: 'Pendente' }, cancelado: { icon: '—', text: 'Cancelado' }
  };
  var STATUS_INFO = {
    parado: { icon: '■', text: 'Parado' }, conectando: { icon: '●', text: 'Conectando…' },
    rodando: { icon: '●', text: 'Rodando' }, reconectando: { icon: '↻', text: 'Reconectando…' },
    parando: { icon: '■', text: 'Parando…' }, erro: { icon: '✗', text: 'Erro' }
  };
  // Bot ligado (mesmo que conectando, reconectando sozinho ou terminando de parar).
  function isBusy(s) {
    return !!s && (s.status === 'rodando' || s.status === 'conectando' || s.status === 'reconectando' || s.status === 'parando');
  }
  var PAGE_TITLES = { painel: 'Painel', entradas: 'Entradas', desempenho: 'Desempenho', config: 'Configuração' };
  var PAGES = ['painel', 'entradas', 'desempenho', 'config'];
  var TF_TEXT = { 60: '1 minuto', 120: '2 minutos', 300: '5 minutos' };
  var MODE_TEXT = {
    sinais: 'Modo: só sinais (sem ordens)', aprovacao: 'Modo: aprovação',
    automatico: 'Modo: automático', automatico_veto: 'Modo: automático com veto'
  };
  var REAL_WARNING = 'CONTA REAL: as ordens passam a usar DINHEIRO DE VERDADE.\n\n' +
    'A retração no comando ainda não tem vantagem comprovada: em dados que ela nunca viu ficou em ~54%, ' +
    'igual ao empate. A recomendação é continuar na demo até ~200 entradas ao vivo.\n\n' +
    'Para usar a conta real mesmo assim, digite REAL:';
  // Na IQ, a binária dos pares normais é o instrumento com sufixo "-op".
  var DEFAULT_PAIRS = ['EURUSD-op', 'GBPUSD-op', 'USDJPY-op', 'AUDUSD-op', 'EURJPY-op', 'EURGBP-op', 'AUDJPY-op', 'NZDUSD-op'];
  var OTC_PAIRS = ['EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'AUDUSD-OTC', 'EURJPY-OTC', 'EURGBP-OTC', 'AUDCAD-OTC', 'NZDUSD-OTC'];
  var CHART_BARS = 240, CHART_BARS_MAX = 1500;  // com o retroativo à vista, o gráfico vai até a meia-noite
  var OPEN_APPROVAL = ['aguardando', 'aprovado', 'disparou'];
  var APPROVAL_STATE = {
    aguardando: { cls: 'warn', icon: '●', text: 'Aguardando sua decisão' },
    aprovado: { cls: 'ok', icon: '✓', text: 'Aprovado: a ordem sai quando o gatilho disparar' },
    disparou: { cls: 'warn', icon: '▲', text: 'O gatilho disparou! Aprovar agora entra no preço do momento' },
    'ordem enviada': { cls: 'ok', icon: '✓', text: 'Ordem enviada' },
    rejeitado: { cls: '', icon: '—', text: 'Rejeitado: sem ordem' },
    'não disparou': { cls: '', icon: '—', text: 'O preço não chegou ao gatilho a tempo: sem ordem (é o normal, a maioria dos pedidos termina assim)' },
    'expirou sem resposta': { cls: 'bad', icon: '✗', text: 'A janela fechou sem resposta: sem ordem' },
    bloqueada: { cls: 'bad', icon: '✗', text: 'Bloqueada pela gestão de risco' },
    'cancelado: conexão caiu': { cls: 'bad', icon: '↻', text: 'A conexão com a IQ caiu: sem ordem (o bot reconecta sozinho)' },
    'exemplo concluído': { cls: 'ok', icon: '✓', text: 'Exemplo: aprovado e o preço tocou o gatilho. Num pedido de verdade, a ordem iria agora para a corretora; aqui nada foi enviado' }
  };
  var ORDER_INFO = {
    enviando: { icon: '…', text: 'Enviando' }, aberta: { icon: '…', text: 'Aberta' },
    bloqueada: { icon: '—', text: 'Bloqueada' }, erro: { icon: '✗', text: 'Erro' }, sem_resultado: { icon: '?', text: 'Sem resultado' }
  };
  var PERIOD_TEXT = { hoje: 'de hoje', '7d': 'nos últimos 7 dias', mes: 'no mês', geral: 'geral' };
  var GRAN_TITLE = { hora: 'Resultado por hora', dia: 'Resultado por dia', mes: 'Resultado por mês' };
  var MIN_SAMPLE = 30;

  var tz = 'America/Sao_Paulo';
  var timeFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: tz, hour: '2-digit', minute: '2-digit' });
  var clockFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: tz, hour: '2-digit', minute: '2-digit', second: '2-digit' });
  var dateTimeFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: tz, day: '2-digit', month: '2-digit', hour: '2-digit', minute: '2-digit' });
  var dayFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: tz, day: '2-digit', month: '2-digit' });
  var pctFmt = new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var unitsFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var intFmt = new Intl.NumberFormat('pt-BR');
  var moneyFmts = {};

  // ------------------------------------------------------------------ utilitários
  function $(sel) { return document.querySelector(sel); }
  function root() { return document.querySelector('.viz-root'); }
  function cssVar(name) { return getComputedStyle(root()).getPropertyValue(name).trim(); }
  function strategyColor(name) {
    // São 8 cores: o score usa a da "LDP v1.3 + regra das linhas", que só existe na ferramenta de pesquisa.
    var i = name === SCORE ? 1 : STRATEGY_ORDER.indexOf(name);
    return cssVar('--series-' + (i >= 0 ? i + 1 : 4));
  }
  function label(name) { return LABELS[name] || name; }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  function precision(p) { return p > 20 ? 3 : 5; }
  function fmtPrice(p) { return p == null ? '—' : Number(p).toFixed(precision(p)); }
  function pip(p) { return p > 20 ? 0.01 : 0.0001; }
  function fmtPct(v) { return v == null ? '—' : pctFmt.format(v); }
  function fmtUnits(v) {
    if (v == null) return '—';
    return (v > 0 ? '+' : v < 0 ? '−' : '') + unitsFmt.format(Math.abs(v));
  }
  function signClass(v) { return v > 0 ? 'up' : v < 0 ? 'down' : ''; }
  function fmtTime(ts) { return timeFmt.format(new Date(ts * 1000)); }
  function fmtMoney(v, signed) {
    if (v == null) return '—';
    var cur = (state.status && state.status.currency) || 'USD';  // a demo da IQ costuma ser em dólar
    if (!moneyFmts[cur]) {
      try { moneyFmts[cur] = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: cur }); }
      catch (e) { moneyFmts[cur] = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
    }
    var s = moneyFmts[cur].format(Math.abs(v));
    return signed ? (v > 0 ? '+' : v < 0 ? '−' : '') + s : s;
  }
  function normalizeAsset(v) {
    v = String(v || '').trim();
    var i = v.indexOf('-');
    if (i < 0) return v.toUpperCase();
    var suffix = v.slice(i + 1);
    return v.slice(0, i).toUpperCase() + '-' + (suffix.toLowerCase() === 'op' ? 'op' : suffix.toUpperCase());
  }
  function isOtc(asset) { return /-OTC$/i.test(asset || ''); }
  // Horário da IQ (o relógio do computador pode estar fora): diferença medida a cada status.
  function serverNow() { return Date.now() / 1000 + (state.clockOffset || 0); }
  function fmtDateTime(ts) { return dateTimeFmt.format(new Date(ts * 1000)); }
  function hexA(hex, a) {
    var h = hex.replace('#', '');
    if (h.length !== 6) return hex;
    return 'rgba(' + parseInt(h.slice(0, 2), 16) + ',' + parseInt(h.slice(2, 4), 16) + ',' + parseInt(h.slice(4, 6), 16) + ',' + a + ')';
  }
  function dirHtml(d) { return d === 'call' ? '<span class="dir">▲ CALL</span>' : '<span class="dir">▼ PUT</span>'; }
  function resHtml(r) {
    var info = RESULT_INFO[r] || { icon: '?', text: r };
    return '<span class="res ' + esc(r) + '"><span class="icon" aria-hidden="true">' + info.icon + '</span>' + info.text + '</span>';
  }
  function dotHtml(name) { return '<span class="dot" style="background:' + strategyColor(name) + '"></span>'; }
  function stratHtml(name) { return '<span class="key">' + dotHtml(name) + esc(label(name)) + '</span>'; }
  function originText(o) { return o === 'ao_vivo' ? 'Ao vivo' : 'Backtest'; }
  function sourceLabel(src) {
    var parts = String(src).split(':');
    return (STRUCT_LABELS[parts[0]] || parts[0]) + (parts[1] ? ' · ' + parts[1].replace(/_/g, ' ') : '');
  }
  function elapsed(sinceTs) {
    var min = Math.max(0, Math.round((Date.now() / 1000 - sinceTs) / 60));
    if (min < 60) return 'há ' + min + ' min';
    return 'há ' + Math.floor(min / 60) + ' h ' + (min % 60) + ' min';
  }
  function api(path, opts) {
    return fetch(path, opts).then(function (r) {
      if (r.ok) return r.json();
      return r.json().catch(function () { return {}; }).then(function (j) {
        var msg = j.detail || r.statusText;
        if (Array.isArray(msg)) msg = msg.map(function (d) { return d.msg; }).join('; ');
        throw new Error(msg);
      });
    });
  }
  function debounce(fn, ms) {
    var t = null;
    return function () { clearTimeout(t); t = setTimeout(fn, ms); };
  }

  // ------------------------------------------------------------------ estado
  var state = {
    page: 'painel', status: null, chartData: null, chartKey: null, priceLines: [], armedLines: [], markersByTime: {},
    visible: {}, showBacktest: false, ePeriod: 'hoje', dPeriod: 'mes', connected: false, shuttingDown: false,
    config: null, cfgPairs: [], forming: {}, seenOpen: {}, beeped: {}, doneAt: {}, audio: null,
    uiVersion: null, ordersById: {}, resolvedAt: {}, apInit: false, entryLines: [], entriesByTime: {}, scriptMarksByTime: {},
    showReading: false, readingData: null, readingByTime: {}, retroData: null, retroSeq: 0, chartExpanded: false, chartOwnsFullscreen: false,
    pairs: null, pairList: [], pairsError: null, pickerCat: 'Todos', manualSending: false, manualError: null, manualLastId: null
  };
  try { state.showReading = localStorage.getItem('botbene-leitura') === '1'; } catch (e) { /* sem armazenamento */ }
  // Cada estratégia está desligada (off), observando (observe: anota sem ordem) ou operando (operate).
  function strategyState(name) {
    return (state.config && state.config.strategies && state.config.strategies[name]) || 'off';
  }
  function strategiesIn(states) {
    return STRATEGY_ORDER.filter(function (n) { return states.indexOf(strategyState(n)) >= 0; });
  }
  // Os números do Painel contam quem opera; sem ninguém operando, quem observa.
  function mainStrategies() {
    var operating = strategiesIn(['operate']);
    return operating.length ? operating : strategiesIn(['observe']);
  }
  function scopeQuery() {
    var main = mainStrategies();
    return '&strategy=' + encodeURIComponent(main.length ? main.join(',') : 'nenhuma');
  }
  function syncVisible() {
    STRATEGY_ORDER.forEach(function (n) { state.visible[n] = strategyState(n) !== 'off'; });
  }
  // Scripts são só desenho no gráfico, ligados na Configuração.
  function scriptOn(name) {
    var scripts = state.config && state.config.chart_scripts;
    return scripts ? !!scripts[name] : name !== 'wiki_pro';
  }
  var tipData = new WeakMap();

  // ------------------------------------------------------------------ tema
  function applyTheme(theme) {
    root().dataset.theme = theme;
    try { localStorage.setItem('botbene-theme', theme); } catch (e) { /* sem armazenamento */ }
    $('#btn-theme-text').textContent = theme === 'dark' ? 'Tema claro' : 'Tema escuro';
    rethemeCharts();
  }

  // ------------------------------------------------------------------ gráficos (lightweight-charts)
  var LWC = window.LightweightCharts;
  var mainChart, candleSeries, buySeries, sellSeries, eqChart, eqSeries;

  function themeOptions() {
    return {
      layout: { background: { type: 'solid', color: cssVar('--surface-1') }, textColor: cssVar('--text-muted'),
        fontFamily: 'system-ui, -apple-system, "Segoe UI", sans-serif' },
      grid: { vertLines: { color: cssVar('--grid') }, horzLines: { color: cssVar('--grid') } },
      rightPriceScale: { borderColor: cssVar('--axis') },
      timeScale: { borderColor: cssVar('--axis') }
    };
  }
  function candleColors() {
    var up = cssVar('--candle-up'), down = cssVar('--candle-down');
    return { upColor: up, downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down };
  }
  // Linhas de 50% e setas CALL/PUT do script LDP v1.3, nas cores dele. Só desenho: o bot não opera nelas.
  function ldpLineOptions(colorVar) {
    return { color: cssVar(colorVar), lineWidth: 2, lineType: LWC.LineType.WithSteps, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
  }
  function scriptMarker(m) {
    var call = m.direction === 'call';
    return { time: m.time, position: call ? 'belowBar' : 'aboveBar', color: cssVar(call ? '--line-buy' : '--line-sell'),
      shape: call ? 'arrowUp' : 'arrowDown', text: call ? 'CALL' : 'PUT' };
  }
  // Ordem que foi para a corretora: a marca maior do gráfico, na cor do texto para não parecer script nem estratégia.
  function entryMarker(o) {
    var call = o.direction === 'call';
    var icon = (RESULT_INFO[o.status] || ORDER_INFO[o.status] || { icon: '' }).icon;
    return { time: o.time, position: call ? 'belowBar' : 'aboveBar', color: cssVar('--text-primary'), size: 2,
      shape: call ? 'arrowUp' : 'arrowDown',
      text: (o.strategy === MANUAL ? 'MANUAL ' : 'ENTRADA ') + (call ? 'CALL' : 'PUT') + (o.price != null ? ' ' + fmtPrice(o.price) : '') + (icon ? ' ' + icon : '') };
  }
  function byTime(a, b) { return a.time - b.time; }
  function tickFormatter(t, type) {
    // type >= 3: marcação de hora; abaixo disso: dia/mês/ano.
    return type >= 3 ? fmtTime(t) : dayFmt.format(new Date(t * 1000));
  }
  function makeChart(el) {
    var c = LWC.createChart(el, {
      autoSize: true,
      crosshair: { mode: LWC.CrosshairMode.Normal },
      localization: { locale: 'pt-BR', timeFormatter: function (t) { return fmtDateTime(t); } },
      timeScale: { timeVisible: true, secondsVisible: false, tickMarkFormatter: tickFormatter }
    });
    c.applyOptions(themeOptions());
    return c;
  }

  // Botões do gráfico, como na IQ Option: − e + (zoom, mantendo a vela da direita no lugar) e foco no preço atual.
  var ZOOM_STEP = 1.4, ZOOM_MIN_BARS = 12, FOCUS_MARGIN_BARS = 8;  // folga à direita: a marca de ENTRADA da vela atual cabe inteira
  function chartZoom(chart, series, factor) {
    var ts = chart.timeScale(), r = ts.getVisibleLogicalRange();
    if (!r) return;
    var maxBars = Math.max(ZOOM_MIN_BARS, series.data().length + FOCUS_MARGIN_BARS);
    var width = Math.max(ZOOM_MIN_BARS, Math.min(maxBars, (r.to - r.from) * factor));
    ts.setVisibleLogicalRange({ from: r.to - width, to: r.to });
  }
  function chartFocus(chart, series) {
    var ts = chart.timeScale(), r = ts.getVisibleLogicalRange(), last = series.data().length - 1;
    if (!r || last < 0) return;
    var width = r.to - r.from;  // mantém o zoom; só traz a vela atual de volta
    ts.setVisibleLogicalRange({ from: last + FOCUS_MARGIN_BARS - width, to: last + FOCUS_MARGIN_BARS });
    chart.priceScale('right').applyOptions({ autoScale: true });  // desfaz o arrasto na escala de preço
  }
  function addChartNav(box, chart, series) {
    var nav = document.createElement('div');
    nav.className = 'chart-nav';
    nav.setAttribute('role', 'group');
    nav.setAttribute('aria-label', 'Zoom e posição do gráfico');
    nav.innerHTML =
      '<button type="button" data-nav="out" title="Afastar (ver mais velas)" aria-label="Afastar o gráfico"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14"/></svg></button>' +
      '<button type="button" data-nav="in" title="Aproximar (ver menos velas)" aria-label="Aproximar o gráfico"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M5 12h14M12 5v14"/></svg></button>' +
      '<button type="button" data-nav="focus" title="Voltar para o preço atual" aria-label="Voltar para o preço atual"><svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="6"/><circle cx="12" cy="12" r="1.2"/><path d="M12 2v4M12 18v4M2 12h4M18 12h4"/></svg></button>';
    box.appendChild(nav);
    nav.addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.nav === 'in') chartZoom(chart, series, 1 / ZOOM_STEP);
      else if (b.dataset.nav === 'out') chartZoom(chart, series, ZOOM_STEP);
      else chartFocus(chart, series);
    });
    // O botão de foco acende quando a vela atual saiu da tela.
    var focus = nav.querySelector('[data-nav="focus"]');
    chart.timeScale().subscribeVisibleLogicalRangeChange(function (r) {
      var last = series.data().length - 1;
      focus.classList.toggle('away', !!r && last >= 0 && r.to < last);
    });
  }

  function initCharts() {
    if (!LWC) {
      $('#chart').innerHTML = '<p class="empty-state">Não foi possível carregar a biblioteca do gráfico (precisa de internet).</p>';
      return;
    }
    mainChart = makeChart($('#chart'));
    candleSeries = mainChart.addCandlestickSeries(candleColors());
    buySeries = mainChart.addLineSeries(ldpLineOptions('--line-buy'));
    sellSeries = mainChart.addLineSeries(ldpLineOptions('--line-sell'));
    candleSeries.attachPrimitive(readingPrimitive);
    mainChart.subscribeCrosshairMove(onCrosshair);
    addChartNav($('#chart-box'), mainChart, candleSeries);

    eqChart = makeChart($('#d-equity'));
    eqSeries = eqChart.addAreaSeries({ lineWidth: 2, priceLineVisible: false, lastValueVisible: true,
      priceFormat: { type: 'custom', formatter: function (v) { return fmtUnits(v); } } });
    eqSeries.createPriceLine({ price: 0, color: cssVar('--axis'), lineWidth: 1, lineStyle: LWC.LineStyle.Solid, axisLabelVisible: false });
  }
  function rethemeCharts() {
    renderToggles();
    renderLineLegend();
    if (!mainChart) return;
    mainChart.applyOptions(themeOptions());
    candleSeries.applyOptions(candleColors());
    buySeries.applyOptions({ color: cssVar('--line-buy') });
    sellSeries.applyOptions({ color: cssVar('--line-sell') });
    eqChart.applyOptions(themeOptions());
    if (state.abChart) {
      state.abChart.applyOptions(themeOptions());
      state.abSeries.applyOptions(candleColors());
      state.abBuy.applyOptions({ color: cssVar('--line-buy') });
      state.abSell.applyOptions({ color: cssVar('--line-sell') });
    }
    if (state.chartData) renderChart(state.chartData);
    if (state.page === 'desempenho') refreshDesempenho();
  }

  // ------------------------------------------------------------------ status e controle do bot
  function renderStatus(s) {
    state.status = s;
    // O horário do servidor só vem da IQ com preço chegando (bot rodando ou par da tela ao vivo).
    if (s.server_time && (s.status === 'rodando' || (s.watch && s.watch.state === 'ao_vivo'))) state.clockOffset = s.server_time - Date.now() / 1000;
    var info = STATUS_INFO[s.status] || { icon: '?', text: s.status };
    var chip = $('#status-chip');
    chip.dataset.status = s.status;
    chip.querySelector('.status-icon').textContent = info.icon;
    chip.querySelector('.status-text').textContent = info.text;
    updateStatusSub();
    if (s.chosen_account && s.chosen_account !== state.chosenAccount) { state.chosenAccount = s.chosen_account; renderAccount(state.accountInfo); }
    $('#mode-text').textContent = MODE_TEXT[s.mode] || 'Modo: só sinais (sem ordens)';

    var busy = isBusy(s);
    var btn = $('#btn-toggle');
    var stopping = s.status === 'parando';
    btn.textContent = stopping ? 'Parando…' : busy ? 'Parar bot' : 'Iniciar bot';
    btn.classList.toggle('stop', busy);
    btn.disabled = stopping;
    renderToolbarAssets();

    if (s.status === 'erro' && s.error) showBanner(s.error);
    else if (s.status === 'reconectando') showBanner(reconnectText(s.connection || {}), 'warn');
    else if (state.connected) hideBanner();

    var price = s.forming ? s.forming.close : (s.last_candle ? s.last_candle.close : null);
    if (price != null) $('#p-price').textContent = fmtPrice(price);
    if (s.payout) $('#p-be-sub').textContent = 'payout de ' + fmtPct(s.payout) + (s.asset ? ' no ' + s.asset : '');
    renderPairTabs();
    renderManual();
    renderArmed(s);
    renderApprovals(s);
    renderRisk(s.risk);
  }

  function renderToolbarAssets() {
    var s = state.status, cfg = state.config;
    var busy = isBusy(s);
    var assets = busy && s.assets && s.assets.length ? s.assets.map(function (a) { return a.asset; }) : (cfg ? cfg.assets : []);
    var tf = busy ? s.timeframe : (cfg ? cfg.timeframe : 60);
    $('#assets-text').textContent = assets.length ? assets.join(' · ') : '—';
    $('#tf-text').textContent = TF_TEXT[tf] || (tf / 60) + ' min';
  }

  // ------------------------------------------------------------------ par do gráfico: abas e lista de todos os pares
  // Olhar um par não muda o que o bot opera. Com o bot parado (ou num par fora da lista dele), o servidor
  // mantém o par da tela ao vivo só para o gráfico.
  var RECENT_MAX = 4;
  var PAIR_CATS = ['Todos', 'Moedas', 'Cripto', 'Ações', 'Índices', 'Outros'];
  function loadStored(key, fallback) {
    try { var v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  }
  function saveStored(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* sem armazenamento */ }
  }
  state.recentPairs = loadStored('botbene-recent-pairs', []);
  state.manualMinutes = loadStored('botbene-manual-min', 1);
  state.manualAmount = loadStored('botbene-manual-valor', null);

  function focusAsset() {
    var s = state.status;
    return (s && s.asset) || (state.chartData && state.chartData.asset) || null;
  }
  function botAssets() {
    var s = state.status;
    if (isBusy(s) && s.assets && s.assets.length) return s.assets.map(function (a) { return a.asset; });
    return state.config ? state.config.assets : [];
  }
  function pairInfo(asset) { return (state.pairs && asset && state.pairs[asset]) || null; }
  function payoutPct(p) { return Math.round(p * 100) + '%'; }

  function refreshPairs() {
    return api('/api/pairs').then(function (d) {
      state.pairs = {};
      (d.pairs || []).forEach(function (p) { state.pairs[p.asset] = p; });
      state.pairList = d.pairs || [];
      state.pairsError = d.error;
      renderPairTabs();
      renderManual();
      if (!$('#pair-picker').hidden) renderPicker();
    }).catch(function () {});
  }

  // "ao vivo" só quando o preço está chegando de verdade.
  function chartLiveText() {
    var s = state.status, asset = focusAsset();
    if (!s || !asset) return 'horário de Brasília';
    var botLive = s.status === 'rodando' && (s.assets || []).some(function (a) { return a.asset === asset && !a.error; });
    var w = s.watch && s.watch.asset === asset ? s.watch : null;
    var text = botLive || (w && w.state === 'ao_vivo') ? 'ao vivo'
      : w && w.state === 'carregando' ? 'carregando ' + asset + '…'
      : w && w.state === 'sem_conexao' ? 'sem conexão com a IQ: tentando de novo'
      : 'parado: últimas velas guardadas';
    var p = pairInfo(asset);
    if (p && !p.open) text += ' · fechado para binária agora';
    return text + ' · horário de Brasília';
  }

  function renderPairTabs() {
    var el = $('#pair-tabs');
    if (!el) return;
    $('#chart-sub').textContent = chartLiveText();
    var current = focusAsset();
    var bot = botAssets();
    var recent = state.recentPairs.filter(function (a) { return bot.indexOf(a) < 0; });
    if (current && bot.indexOf(current) < 0 && recent.indexOf(current) < 0) recent.unshift(current);
    var armed = {};
    ((state.status && state.status.assets) || []).forEach(function (a) { if (a.armed) armed[a.asset] = true; });
    function tab(asset, removable) {
      var p = pairInfo(asset), on = asset === current;
      // Fora da lista da IQ = sem binária de até 5 min nesse par agora.
      var pay = p ? (p.open ? (p.payout != null ? payoutPct(p.payout) : '') : 'fechado') : (state.pairList.length ? 'sem binária' : '');
      var title = p ? p.label + (p.open ? '' : ' · fechado para binária agora') : asset;
      return '<span class="pair-tab' + (on ? ' on' : '') + ((p ? !p.open : state.pairList.length) ? ' closed' : '') + '">' +
        '<button type="button" data-pair="' + esc(asset) + '" aria-pressed="' + on + '" title="' + esc(title) + '">' +
        (armed[asset] ? '<span class="armed-dot" title="entrada armada"></span>' : '') + esc(asset) +
        (pay ? '<span class="pt-pay">' + pay + '</span>' : '') + '</button>' +
        (removable && !on ? '<button type="button" class="pt-x" data-unpin="' + esc(asset) + '" aria-label="Tirar ' + esc(asset) + ' das abas">×</button>' : '') +
        '</span>';
    }
    var html = (bot.length ? '<span class="pt-cap">Bot</span>' + bot.map(function (a) { return tab(a, false); }).join('') : '') +
      (recent.length ? '<span class="pt-cap">Olhando</span>' + recent.map(function (a) { return tab(a, true); }).join('') : '') +
      '<button type="button" class="pt-all" id="pt-all">+ Todos os pares</button>';
    if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
  }

  function choosePair(asset) {
    asset = normalizeAsset(asset);
    closePicker();
    if (!asset) return;
    if (botAssets().indexOf(asset) < 0) {
      state.recentPairs = [asset].concat(state.recentPairs.filter(function (a) { return a !== asset; })).slice(0, RECENT_MAX);
      saveStored('botbene-recent-pairs', state.recentPairs);
    }
    saveStored('botbene-focus', asset);
    state.manualError = null;
    focusOn(asset).catch(function (err) { showBanner(err.message); });
  }
  function focusOn(asset) {
    return api('/api/bot/focus', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset: asset }) })
      .then(function (s) { renderStatus(s); state.chartKey = null; refreshChart(); });
  }
  function unpinPair(asset) {
    state.recentPairs = state.recentPairs.filter(function (a) { return a !== asset; });
    saveStored('botbene-recent-pairs', state.recentPairs);
    renderPairTabs();
  }
  // Ao abrir o painel (ou o servidor voltar): o par da tela fica ao vivo mesmo com o bot parado.
  function ensureWatching() {
    var s = state.status;
    if (!s || s.status === 'parando') return;
    var asset = s.asset || loadStored('botbene-focus', null) || (state.chartData && state.chartData.asset) || botAssets()[0];
    if (!asset) return;
    var botHasIt = s.status === 'rodando' && (s.assets || []).some(function (a) { return a.asset === asset && !a.error; });
    if (botHasIt || (s.watch && s.watch.asset === asset)) return;
    focusOn(asset).catch(function () {});
  }

  function openPicker() {
    $('#pair-picker').hidden = false;
    $('#pp-search').value = '';
    renderPickerCats();
    renderPicker();
    $('#pp-search').focus();
    refreshPairs();
  }
  function closePicker() {
    var el = $('#pair-picker');
    if (el.hidden) return false;
    el.hidden = true;
    return true;
  }
  function renderPickerCats() {
    $('#pp-cats').innerHTML = PAIR_CATS.map(function (c) {
      return '<button type="button" data-cat="' + esc(c) + '" aria-pressed="' + (c === state.pickerCat) + '">' + esc(c) + '</button>';
    }).join('');
  }
  function knownPairs() {  // sem conexão com a IQ: os pares de sempre, sem payout
    return DEFAULT_PAIRS.concat(OTC_PAIRS).map(function (a) {
      return { asset: a, label: a, category: 'Moedas', payout: null, open: null, reason: null };
    });
  }
  function squash(text) { return String(text).toUpperCase().replace(/[\s/.()-]/g, ''); }
  function renderPicker() {
    var all = state.pairList.length ? state.pairList : knownPairs();
    var q = squash($('#pp-search').value.trim());
    var onlyOpen = $('#pp-open').checked;
    var bot = botAssets(), current = focusAsset();
    var items = all.filter(function (p) {
      if (state.pickerCat !== 'Todos' && p.category !== state.pickerCat) return false;
      if (onlyOpen && p.open === false) return false;
      return !q || squash(p.asset + ' ' + p.label).indexOf(q) >= 0;
    }).sort(function (a, b) {
      var ab = bot.indexOf(a.asset) >= 0, bb = bot.indexOf(b.asset) >= 0;
      if (ab !== bb) return ab ? -1 : 1;
      if (!!a.open !== !!b.open) return a.open ? -1 : 1;
      return (b.payout || 0) - (a.payout || 0) || a.asset.localeCompare(b.asset);
    });
    var open = all.filter(function (p) { return p.open; }).length;
    $('#pp-note').textContent = state.pairsError
      ? 'Sem conexão com a IQ agora: mostrando os pares de sempre, sem payout.'
      : (state.pairList.length ? intFmt.format(open) + ' pares abertos agora, de ' + intFmt.format(all.length) + '.' : 'Carregando a lista da IQ…');
    $('#pp-list').innerHTML = items.length ? items.map(function (p) {
      var right = p.open === false ? '<span class="pp-closed">fechado</span>' : (p.payout != null ? '<span class="pp-pay">' + payoutPct(p.payout) + '</span>' : '');
      return '<li><button type="button" data-pair="' + esc(p.asset) + '"' + (p.asset === current ? ' aria-current="true"' : '') + '>' +
        '<span class="pp-name">' + esc(p.asset) + (bot.indexOf(p.asset) >= 0 ? ' <span class="pp-tag">bot</span>' : '') + '</span>' +
        '<span class="pp-label">' + esc(p.label !== p.asset ? p.label : '') + '</span>' + right + '</button></li>';
    }).join('') : '<li class="empty">Nenhum par com esse filtro.</li>';
  }

  // ------------------------------------------------------------------ entrada manual
  // Os stops e os filtros do bot não valem aqui: só o que a IQ exige (par aberto, valor e expiração do par).
  function fmtAmount(v) { return unitsFmt.format(v); }
  function manualAmount() {
    var raw = String($('#m-amount').value).trim();
    // "1.000,50" (com vírgula, o ponto separa milhar) ou "2.5" (sem vírgula, o ponto é decimal)
    if (raw.indexOf(',') >= 0) raw = raw.replace(/\./g, '').replace(',', '.');
    var v = parseFloat(raw);
    return isFinite(v) ? Math.round(v * 100) / 100 : NaN;
  }
  // Mesma regra da IQ: faltando 30 s ou menos para virar o minuto, vale o minuto seguinte.
  function expiryFor(now, minutes) {
    var end = (Math.floor(now / 60) + 1) * 60;
    if (end - now <= 30) end += 60;
    return end + 60 * (minutes - 1);
  }
  function manualBlock(asset, p, amount) {
    var s = state.status;
    if (!asset) return 'Escolha um par acima do gráfico.';
    if (s && s.status === 'reconectando') return 'O bot está reconectando à IQ: espere alguns segundos.';
    if (!p) return state.pairsError ? 'Sem conexão com a IQ agora.' : (state.pairs ? asset + ' não está na lista de binárias da IQ.' : 'Carregando a lista de pares…');
    if (!p.open) return p.reason || asset + ' está fechado para binária agora.';
    if (!isFinite(amount) || amount <= 0) return 'Digite o valor da entrada.';
    if (p.min != null && amount < p.min) return 'Valor mínimo neste par: ' + fmtMoney(p.min) + '.';
    if (p.max != null && amount > p.max) return 'Valor máximo neste par: ' + fmtMoney(p.max) + '.';
    return '';
  }
  function manualOrderText(o) {
    var st = orderState(o);
    var money = o.profit != null && st.kind === 'sent' && o.status !== 'aberta' ? ' ' + fmtMoney(o.profit, true) : '';
    return '<div class="m-last ' + (st.kind === 'fail' ? 'bad' : (st.cls || '')) + '">' + dirHtml(o.direction) + ' ' + esc(o.asset) + ' ' + fmtMoney(o.amount) +
      ' · ' + esc(st.label) + (st.detail ? ' · ' + esc(st.detail) : '') + money +
      (o.status === 'aberta' && o.expires_at ? ' · vence ' + clockFmt.format(new Date(o.expires_at * 1000)) : '') +
      (st.kind === 'fail' && o.error ? ': ' + esc(o.error) : '') + '</div>';
  }
  function renderManual() {
    var card = $('#manual-card');
    if (!card) return;
    var asset = focusAsset(), p = pairInfo(asset);
    var real = isReal();
    card.classList.toggle('real', real);
    $('#m-acct').textContent = real ? 'CONTA REAL' : 'CONTA DEMO';
    $('#m-asset').textContent = asset || '—';
    $('#m-payout').textContent = p && p.payout != null ? payoutPct(p.payout) : '—';
    var exps = p && p.expiries && p.expiries.length ? p.expiries : [1, 2, 3, 4, 5];
    var minutes = exps.indexOf(state.manualMinutes) >= 0 ? state.manualMinutes : exps[0];
    var expHtml = exps.map(function (m) {
      return '<button type="button" data-min="' + m + '" aria-pressed="' + (m === minutes) + '">' + m + ' min</button>';
    }).join('');
    var expEl = $('#m-exp');
    if (expEl.dataset.html !== expHtml) { expEl.innerHTML = expHtml; expEl.dataset.html = expHtml; }
    var input = $('#m-amount');
    if (!input.value && document.activeElement !== input) {
      input.value = fmtAmount(state.manualAmount != null ? state.manualAmount : (state.config ? state.config.stake : 2));
    }
    var amount = manualAmount();
    $('#m-win').textContent = p && p.payout != null && isFinite(amount) && amount > 0 ? 'se ganhar: ' + fmtMoney(amount * p.payout, true) : '';
    var why = manualBlock(asset, p, amount);
    $('#m-call').disabled = $('#m-put').disabled = !!why || state.manualSending;
    var last = state.manualLastId != null ? state.ordersById[state.manualLastId] : null;
    var msg = state.manualSending ? '<div class="m-last">Enviando…</div>'
      : state.manualError ? '<div class="m-last bad">✗ ' + esc(state.manualError) + '</div>'
      : last ? manualOrderText(last) : '';
    if (why) msg = '<div class="m-why">' + esc(why) + '</div>' + msg;
    var msgEl = $('#m-msg');
    if (msgEl.dataset.html !== msg) { msgEl.innerHTML = msg; msgEl.dataset.html = msg; }
    updateManualClock();
    renderManualToday();
  }
  function manualMinutesNow() {
    var b = document.querySelector('#m-exp button[aria-pressed="true"]');
    return b ? Number(b.dataset.min) : 1;
  }
  function updateManualClock() {
    var el = $('#m-expiry');
    if (!el) return;
    var now = serverNow(), end = expiryFor(now, manualMinutesNow());
    var left = Math.max(0, Math.round(end - now));
    el.textContent = 'vence ' + clockFmt.format(new Date(end * 1000)) + ' · faltam ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
  }
  function renderManualToday() {
    var start = Math.floor((Date.now() / 1000 - 10800) / 86400) * 86400 + 10800;  // meia-noite de Brasília
    var list = Object.keys(state.ordersById).map(function (k) { return state.ordersById[k]; }).filter(function (o) {
      return o.strategy === MANUAL && o.requested_at >= start && orderState(o).kind === 'sent';
    });
    var el = $('#m-today');
    if (!list.length) { el.textContent = 'Nenhuma entrada manual hoje.'; return; }
    var profit = 0, open = 0, closed = 0;
    list.forEach(function (o) {
      if (RESULT_INFO[o.status]) { profit += o.profit || 0; closed += 1; }
      else if (o.status === 'aberta' || o.status === 'enviando') open += 1;
    });
    profit = Math.round(profit * 100) / 100;
    el.innerHTML = 'Hoje: ' + list.length + (list.length > 1 ? ' manuais' : ' manual') +
      (closed ? ' · <span class="' + signClass(profit) + '">' + fmtMoney(profit, true) + '</span>' : '') +
      (open ? ' · ' + open + (open > 1 ? ' abertas' : ' aberta') : '');
  }
  function stepAmount(dir) {
    var p = pairInfo(focusAsset());
    var v = manualAmount();
    if (!isFinite(v)) v = p && p.min != null ? p.min : 1;
    v = Math.max(p && p.min != null ? p.min : 1, Math.floor(v) + dir);
    if (p && p.max != null) v = Math.min(p.max, v);
    $('#m-amount').value = fmtAmount(v);
    state.manualAmount = v;
    saveStored('botbene-manual-valor', v);
    state.manualError = null;
    renderManual();
  }
  function sendManual(direction) {
    var asset = focusAsset(), p = pairInfo(asset), amount = manualAmount(), minutes = manualMinutesNow();
    if (state.manualSending || manualBlock(asset, p, amount)) return;
    state.manualSending = true;
    state.manualError = null;
    state.manualAmount = amount;
    saveStored('botbene-manual-valor', amount);
    saveStored('botbene-manual-min', minutes);
    renderManual();
    api('/api/orders/manual', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset: asset, direction: direction, amount: amount, minutes: minutes }) })
      .then(function (row) { state.ordersById[row.id] = row; state.manualLastId = row.id; })
      .catch(function (e) { state.manualLastId = null; state.manualError = e.message; })
      .then(function () { state.manualSending = false; renderManual(); });
  }

  // ------------------------------------------------------------------ próxima entrada (apostila)
  function capitalize(text) { return text.charAt(0).toUpperCase() + text.slice(1); }

  // Par fechado para binária não manda ordem: melhor avisar logo do que deixar parecer que o bot parou.
  function openPairsNote(s) {
    var assets = s.assets || [];
    var closed = assets.filter(function (a) { return !a.tradable; });
    if (!closed.length) return '';
    if (closed.length === assets.length) {
      return '<div class="pairs-note warn">' + (assets.length > 1 ? 'Nenhum par aberto' : 'Par fechado') + ' para binária agora: as entradas ficam só anotadas.</div>';
    }
    return '<div class="pairs-note"><strong>' + (assets.length - closed.length) + ' de ' + assets.length + '</strong> pares abertos para binária · fechados: ' +
      esc(closed.map(function (a) { return a.asset; }).join(', ')) + '</div>';
  }

  // O bot registra uma linha por acontecimento. Na tela, cada setup aparece uma vez, com o desfecho.
  function recentSetups(s) {
    var groups = [], byKey = {};
    function group(x) {
      var key = [x.target_ts, x.asset, x.strategy, x.direction].join('|');
      if (!byKey[key]) {
        byKey[key] = { target_ts: x.target_ts, asset: x.asset, strategy: x.strategy, direction: x.direction, outcomes: [], approval: null };
        groups.push(byKey[key]);
      }
      return byKey[key];
    }
    (s.armed_log || []).forEach(function (l) { group(l).outcomes.push(l.outcome); });
    (s.approvals || []).forEach(function (a) { if (!a.demo) group(a).approval = a; });
    return groups.filter(function (g) {  // ainda armado e sem novidade: já aparece no quadro acima
      return g.outcomes.length || !g.approval || !isOpenApproval(g.approval);
    }).sort(function (x, y) { return y.target_ts - x.target_ts; });
  }
  function noOrderReason(outcome, asset) {
    var reason = outcome.replace(/^sem ordem:\s*/, '');
    return capitalize(reason.indexOf(asset) === 0 ? 'par' + reason.slice(asset.length) : reason);
  }
  // pill vazio = desfecho comum (não disparou): a linha fica discreta, e o que importa se destaca.
  function setupOutcome(g, s) {
    function find(prefix) { return g.outcomes.filter(function (o) { return o.indexOf(prefix) === 0; })[0]; }
    var a = g.approval;
    if (a && isOpenApproval(a)) return { pill: 'none', text: 'Aguardando você' };
    if (a) {
      var oc = approvalOutcome(a);
      if (oc.kind === 'sent') return { pill: 'sent', text: 'Ordem enviada', result: oc.result };
      if (oc.kind === 'fail') return { pill: 'fail', text: 'Não enviada', note: capitalize(oc.reason.split(' · ').slice(1).join(' · ')) };
      if (a.status === 'não disparou') return { text: 'não disparou' };
      return { pill: 'none', text: 'Sem ordem', note: capitalize(a.status) };
    }
    var blocked = find('sem ordem:');
    var reason = blocked ? noOrderReason(blocked, g.asset) : null;
    if (find('ENTROU')) {
      return { pill: 'note', text: 'Só anotada', note: reason ||
        (s.mode === 'sinais' ? 'Modo só sinais' : strategyState(g.strategy) === 'observe' ? 'Estratégia em Observar' : '') };
    }
    var skipped = find('pulou');  // o score avaliou e não entrou: mostra quais padrões faltaram
    if (skipped) return { pill: 'none', text: 'Pulou', note: capitalize(skipped.replace(/^pulou:\s*/, '')) };
    var canceled = find('cancelado');
    if (canceled) return { pill: 'none', text: 'Cancelada', note: capitalize(canceled.replace(/^cancelado:\s*/, '')) };
    if (find('não ')) return { text: 'não disparou' };
    return reason ? { pill: 'none', text: 'Sem ordem', note: reason } : { text: 'armada' };
  }
  function setupRow(g, s, multi) {
    var oc = setupOutcome(g, s);
    var side = oc.pill ? '<span class="oc-pill ' + oc.pill + '">' + esc(oc.text) + '</span>' : '<span class="setup-quiet">' + esc(oc.text) + '</span>';
    if (oc.result) side += '<span class="oc-res ' + oc.result.cls + '">' + esc(shortResult(oc.result.text)) + '</span>';
    return '<div class="setup-row' + (oc.pill ? '' : ' quiet') + '" title="' + esc(label(g.strategy)) + '">' +
      '<span class="when">' + fmtTime(g.target_ts) + '</span>' +
      '<span class="setup-what">' + (shownStrategies().length > 1 ? dotHtml(g.strategy) : '') + dirHtml(g.direction) +
        (multi ? '<span class="oc-asset">' + esc(g.asset) + '</span>' : '') + '</span>' +
      '<span class="oc-side">' + side + '</span>' +
      (oc.note ? '<div class="setup-note">' + esc(oc.note) + '</div>' : '') +
    '</div>';
  }

  function renderArmed(s) {
    var el = $('#armed-body');
    var list = (s && s.armed) || [];
    if (!s || s.status !== 'rodando') {
      el.innerHTML = '<p class="muted">Com o bot rodando, aqui aparecem as entradas armadas para a próxima vela.</p>';
      updateArmedLines([]);
      return;
    }
    var html;
    var multi = (s.assets || []).length > 1;
    if (!list.length) {
      var reasons = s.plan_reasons || [];
      var oneStrategy = shownStrategies().length === 1;  // aí o nome dela na frente de cada motivo é repetição
      html = '<p class="armed-none">Nenhuma entrada armada nesta vela.</p>' +
        (reasons.length ? '<div class="armed-why">' + (multi ? '<strong>' + esc(s.asset) + '</strong>' : '') + reasons.map(function (r) {
          var cut = r.indexOf(': ');
          return '<div>' + esc(capitalize(oneStrategy && cut >= 0 ? r.slice(cut + 2) : r)) + '</div>';
        }).join('') + '</div>' : '');
    } else {
      html = list.map(function (a) {
        var head = '<div class="armed" style="border-left-color:' + strategyColor(a.strategy) + '">' +
          '<div class="armed-top">' + dirHtml(a.direction) + (multi ? '<strong>' + esc(a.asset) + '</strong>' : '') +
            '<span>' + esc(TRIGGER_LABELS[a.trigger] || a.trigger) + '</span>' +
            '<span class="countdown" data-start="' + a.target_ts + '" data-end="' + a.window_end + '"></span></div>';
        if (a.strategy === SCORE) {
          var marks = Object.keys(a.confluences || {}).map(function (k) {
            return '<span class="chip ' + (a.confluences[k] ? 'ok' : 'no') + '">' + (a.confluences[k] ? '✓ ' : '✗ ') + esc(CONF_LABELS[k] || k) + '</span>';
          }).join('');
          return head +
            '<div class="armed-level">Gatilho <strong>' + fmtPrice(a.level_price) + '</strong> <span class="muted">· ' +
              esc(a.level_sources[0] || '') + '</span></div>' +
            '<div class="armed-conf">' + marks + '</div>' +
            '<div class="muted small">Retração no comando com ' + a.score + ' de 4 padrões. Entra ' + (a.direction === 'call' ? 'CALL' : 'PUT') +
              ' no primeiro toque em ' + esc(a.level_sources.slice(1).join(', ')) + ' nos primeiros ' + a.window_seconds +
              ' s da vela das ' + fmtTime(a.target_ts) + '.</div>' +
          '</div>';
        }
        if (a.strategy === 'retracao_comando') {
          return head +
            '<div class="armed-level">Gatilho <strong>' + fmtPrice(a.level_price) + '</strong> <span class="muted">· ' +
              esc(a.level_sources[0] || '') + ' a partir da abertura</span></div>' +
            '<div class="muted small">A vela anterior fechou forte. Entra ' + (a.direction === 'call' ? 'CALL' : 'PUT') +
              ' se a vela das ' + fmtTime(a.target_ts) + ' recuar até o gatilho nos primeiros ' + a.window_seconds + ' s.</div>' +
          '</div>';
        }
        var conf = Object.keys(a.confluences || {}).map(function (k) {
          return '<span class="chip ' + (a.confluences[k] ? 'ok' : 'no') + '">' + esc(CONF_LABELS[k] || k) + '</span>';
        }).join('');
        var study = STUDY_STRATEGIES.indexOf(a.strategy) >= 0;  // as do estudo já mandam o nome e a página de cada região
        return head +
          '<div class="armed-level">Marcação <strong>' + fmtPrice(a.level_price) + '</strong> <span class="muted">· ' +
            (study ? '' : 'força ' + a.level_strength + ' · ') +
            esc(a.level_sources.slice(0, study ? 3 : 2).map(study ? String : sourceLabel).join(' · ')) + '</span></div>' +
          '<div class="armed-conf">' + conf + '</div>' +
          '<div class="muted small">' + esc(LABELS[a.strategy] || '') + ': ' + a.score + ' confluências. Entra se o preço tocar a marcação nos primeiros ' +
            a.window_seconds + ' s da vela das ' + fmtTime(a.target_ts) + '.</div>' +
        '</div>';
      }).join('');
    }
    var setups = recentSetups(s).slice(0, 8);
    if (setups.length) {
      html += '<div class="armed-log"><div class="muted">Últimos setups</div>' +
        setups.map(function (g) { return setupRow(g, s, multi); }).join('') + '</div>';
    }
    el.innerHTML = openPairsNote(s) + html;
    updateCountdowns();
    updateArmedLines(list);
  }

  function updateCountdowns() {
    var now = serverNow();
    Array.prototype.forEach.call(document.querySelectorAll('.countdown'), function (c) {
      var start = parseFloat(c.dataset.start), end = parseFloat(c.dataset.end);
      if (now < start) c.textContent = 'aguardando a vela das ' + fmtTime(start);
      else if (now <= end) c.textContent = 'janela: ' + Math.ceil(end - now) + ' s';
      else c.textContent = 'janela encerrada';
    });
  }

  function updateArmedLines(list) {
    if (!candleSeries) return;
    state.armedLines.forEach(function (pl) { candleSeries.removePriceLine(pl); });
    var chartAsset = state.chartData ? state.chartData.asset : null;
    state.armedLines = list.filter(function (a) { return !a.asset || a.asset === chartAsset; }).map(function (a) {
      return candleSeries.createPriceLine({
        price: a.level_price, color: strategyColor(a.strategy || 'ldp_apostila'), lineWidth: 2, lineStyle: LWC.LineStyle.Dashed,
        axisLabelVisible: true, title: (a.direction === 'call' ? 'CALL' : 'PUT') + ' armado'
      });
    });
  }
  // ------------------------------------------------------------------ pedidos de aprovação (ordem na demo)
  function isOpenApproval(a) { return OPEN_APPROVAL.indexOf(a.status) >= 0; }
  function apState(st) {
    if (APPROVAL_STATE[st]) return APPROVAL_STATE[st];
    return { cls: '', icon: '—', text: st.charAt(0).toUpperCase() + st.slice(1) };
  }

  // O pedido aberto aparece GRANDE: o gráfico (60 velas, vela de comando, gatilho e abertura) é o centro;
  // ao lado, o que importa para decidir e os botões. Vários pedidos ao mesmo tempo viram abas.
  // Como um pedido terminou, em linguagem direta: a ordem foi enviada ou não?
  function approvalOutcome(a) {
    var st = a.status || '';
    var acct = a.demo ? 'CONTA DEMO' : (isReal() ? 'CONTA REAL' : 'CONTA DEMO');
    var what = (a.direction === 'call' ? '▲ CALL ' : '▼ PUT ') + a.asset;
    if (st === 'ordem enviada' || st === 'exemplo concluído') {
      var o = a.order_id != null ? state.ordersById[a.order_id] : null;
      if (o && (o.status === 'erro' || o.status === 'bloqueada')) {
        return { kind: 'fail', icon: '✗', title: 'A ORDEM NÃO FOI ENVIADA', reason: what + ' · a corretora recusou: ' + (o.error || 'erro'), resolved: true };
      }
      var res, resolved = false;
      if (o && o.status === 'win') { res = { cls: 'good', text: 'GANHOU ' + fmtMoney(o.profit, true) }; resolved = true; }
      else if (o && o.status === 'loss') { res = { cls: 'bad', text: 'PERDEU ' + fmtMoney(o.profit, true) }; resolved = true; }
      else if (o && o.status === 'empate') { res = { cls: '', text: 'EMPATE · valor devolvido' }; resolved = true; }
      else if (o && o.status === 'sem_resultado') { res = { cls: 'warn', text: 'a IQ não informou o resultado' }; resolved = true; }
      else if (a.demo) { res = { cls: 'warn', text: 'exemplo: nada foi enviado' }; resolved = true; }
      else res = { cls: 'warn', text: 'aguardando o resultado · vence ' + fmtTime((o && o.expires_at) || a.target_ts + (a.timeframe || 60)) };
      var stake = o ? fmtMoney(o.amount) : '';
      return { kind: 'sent', icon: '✓', title: a.demo ? 'EXEMPLO: AQUI A ORDEM SERIA ENVIADA' : 'ORDEM ENVIADA NA ' + acct,
               reason: what + (stake ? ' · ' + stake : '') + (a.trigger_price != null ? ' · entrou em ' + fmtPrice(a.trigger_price) : ''),
               result: res, resolved: resolved };
    }
    if (st === 'bloqueada') {
      return { kind: 'fail', icon: '✗', title: 'A ORDEM NÃO FOI ENVIADA', reason: what + ' · a gestão de risco bloqueou' + (a.note ? ': ' + a.note : ''), resolved: true };
    }
    var why = {
      'não disparou': 'o preço não chegou ao gatilho a tempo. É o normal: a maioria dos pedidos termina assim',
      'rejeitado': 'você rejeitou', 'cancelado por você': 'você cancelou',
      'cancelado: conexão caiu': 'a conexão com a IQ caiu antes do gatilho (o bot reconecta sozinho)',
      'expirou sem resposta': 'a janela fechou sem aprovação'
    }[st] || st;
    return { kind: 'none', icon: '—', title: 'NENHUMA ORDEM FOI ENVIADA', reason: what + ' · ' + why, resolved: true };
  }
  // Versão curta do resultado, para listas estreitas ("GANHOU +US$ 1,68" -> "ganhou +US$ 1,68").
  function shortResult(text) {
    return String(text).replace(/^aguardando o resultado.*$/, 'aguardando…').replace(/^GANHOU/, 'ganhou').replace(/^PERDEU/, 'perdeu')
      .replace(/^EMPATE.*$/, 'empate').replace(/^a IQ não informou.*$/, 'sem resultado');
  }
  // Quanto tempo o cartão de resultado fica na tela (segundos depois de o pedido terminar).
  function outcomeUntil(a, oc) {
    var t = state.doneAt[a.id] || 0;
    if (oc.kind === 'sent' && !oc.resolved) return t + 180;  // até sair o resultado
    if (oc.kind === 'sent') { if (!state.resolvedAt[a.id]) state.resolvedAt[a.id] = Date.now() / 1000; return state.resolvedAt[a.id] + 40; }
    return t + (oc.kind === 'fail' ? 40 : 15);
  }

  function renderApprovals(s) {
    var tray = $('#approvals');
    var all = ((s && s.approvals) || []).concat(state.demoApproval ? [state.demoApproval] : []);
    var now = Date.now() / 1000;
    if (!state.apInit) {  // ao abrir o painel, pedidos que já tinham terminado não reaparecem
      all.forEach(function (a) { if (!isOpenApproval(a)) state.doneAt[a.id] = -1; });
      state.apInit = true;
    }
    // No modo automático puro o bot entra sozinho: o cartão não aparece antes; só o resultado, se a ordem saiu.
    var pureAuto = function (a) { return a.auto && !a.veto; };
    all.forEach(function (a) {
      if (isOpenApproval(a)) {
        if (pureAuto(a)) return;
        if (!state.seenOpen[a.id]) { state.seenOpen[a.id] = true; alertApproval(a, 'novo'); }
        if (a.status === 'disparou' && !state.beeped[a.id]) { state.beeped[a.id] = true; alertApproval(a, 'disparou'); }
      } else if (state.doneAt[a.id] == null && (state.seenOpen[a.id] || (pureAuto(a) && approvalOutcome(a).kind !== 'none'))) {
        state.doneAt[a.id] = now;
      }
    });
    var open = all.filter(function (a) { return isOpenApproval(a) && !pureAuto(a); });
    var done = all.filter(function (a) {
      if (isOpenApproval(a) || !(state.doneAt[a.id] > 0)) return false;
      return now < outcomeUntil(a, approvalOutcome(a));
    });
    if (!open.length && !done.length) { tray.hidden = true; state.approvalSelObj = null; resetTitle(); return; }
    tray.hidden = false;
    ensureApprovalTray();
    var isSel = function (a) { return String(a.id) === String(state.approvalSel); };
    if (!open.some(isSel)) {
      var urgent = open.slice().sort(function (x, y) { return x.deadline - y.deadline; })[0];
      state.approvalSel = urgent ? String(urgent.id) : null;
    }
    var sel = open.filter(isSel)[0] || null;
    state.approvalSelObj = sel;
    $('#ab-chips').innerHTML = open.length > 1 ? open.map(approvalChipHtml).join('') : '';
    $('#ab-big').hidden = !sel;
    if (sel) {
      $('#ab-big').style.borderLeftColor = strategyColor(sel.strategy);
      $('#ab-side').innerHTML = approvalSideHtml(sel);
      renderApprovalChart(sel);
    }
    $('#ab-done').innerHTML = done.map(approvalDoneHtml).join('');
    var waiting = open.filter(function (a) { return a.status === 'aguardando' || a.status === 'disparou'; }).length;
    if (waiting) document.title = '● Aprovar entrada · BotBene'; else resetTitle();
    updateApprovalClocks();
  }
  function resetTitle() { if (document.title !== 'BotBene') document.title = 'BotBene'; }

  function ensureApprovalTray() {
    if ($('#ab-big')) return;
    $('#approvals').innerHTML =
      '<div class="ab-chips" id="ab-chips"></div>' +
      '<div class="approval-big" id="ab-big">' +
        '<div class="ab-chart-wrap"><div class="ab-chart-head" id="ab-chart-head"></div>' +
          '<div class="chart-box" id="ab-chart-box"><div id="ab-chart" class="ab-chart"></div></div>' +
          '<div class="ab-legend" id="ab-legend"></div></div>' +
        '<div class="ab-side" id="ab-side"></div>' +
      '</div>' +
      '<div class="ab-done" id="ab-done"></div>';
    if (LWC) {
      state.abChart = makeChart($('#ab-chart'));
      state.abSeries = state.abChart.addCandlestickSeries(candleColors());
      state.abBuy = state.abChart.addLineSeries(ldpLineOptions('--line-buy'));
      state.abSell = state.abChart.addLineSeries(ldpLineOptions('--line-sell'));
      state.abLines = [];
      addChartNav($('#ab-chart-box'), state.abChart, state.abSeries);
    }
  }

  function approvalBars(a) {
    var bars = (a.excerpt || []).slice();
    var f = state.forming[a.asset];
    if (f && f.time === a.target_ts && (!bars.length || f.time > bars[bars.length - 1].time)) bars.push(f);
    return bars;
  }

  function renderApprovalChart(a) {
    var bars = approvalBars(a);
    var color = strategyColor(a.strategy);
    $('#ab-chart-head').innerHTML = '<strong>' + esc(a.asset) + ' · M' + ((a.timeframe || 60) / 60) + '</strong> <span class="muted small">últimas ' + bars.length +
      ' velas · vela de comando marcada · a vela da entrada se mexe ao vivo</span>';
    $('#ab-legend').innerHTML =
      '<span class="key"><span class="line-key dashed" style="border-color:' + color + '"></span>Gatilho ' + fmtPrice(a.level_price) + '</span>' +
      (a.open_price != null ? '<span class="key"><span class="dotted-key"></span>Abertura da vela da entrada ' + fmtPrice(a.open_price) + '</span>' : '') +
      '<span class="key">' + (a.direction === 'call' ? '▲' : '▼') + ' vela de comando (' + fmtTime(a.target_ts - (a.timeframe || 60)) + ')</span>' +
      (scriptOn('ldp_lines') || scriptOn('ldp_arrows') ? '<span class="key">Linhas e CALL/PUT: script LDP v1.3 (só desenho, não decide entrada)</span>' : '');
    if (!state.abSeries || !bars.length) return;
    var prec = precision(bars[bars.length - 1].close);
    state.abSeries.applyOptions({ priceFormat: { type: 'price', precision: prec, minMove: Math.pow(10, -prec) } });
    state.abSeries.setData(bars);
    var overlay = a.overlay || {};
    var showLines = scriptOn('ldp_lines');
    state.abBuy.applyOptions({ visible: showLines });
    state.abSell.applyOptions({ visible: showLines });
    state.abBuy.setData(overlay.buy_line || []);
    state.abSell.setData(overlay.sell_line || []);
    state.abLines.forEach(function (pl) { state.abSeries.removePriceLine(pl); });
    state.abLines = [state.abSeries.createPriceLine({
      price: a.level_price, color: color, lineWidth: 2, lineStyle: LWC.LineStyle.Dashed, axisLabelVisible: true, title: 'Gatilho'
    })];
    if (a.open_price != null) {
      state.abLines.push(state.abSeries.createPriceLine({
        price: a.open_price, color: cssVar('--level'), lineWidth: 1, lineStyle: LWC.LineStyle.Dotted, axisLabelVisible: true, title: 'Abertura'
      }));
    }
    var cmdTime = a.target_ts - (a.timeframe || 60);
    var marks = scriptOn('ldp_arrows') ? (overlay.script_marks || []).map(scriptMarker) : [];
    if (bars.some(function (b) { return b.time === cmdTime; })) {
      marks.push({
        time: cmdTime, position: a.direction === 'call' ? 'belowBar' : 'aboveBar', color: color,
        shape: a.direction === 'call' ? 'arrowUp' : 'arrowDown', text: 'comando'
      });
    }
    state.abSeries.setMarkers(marks.sort(byTime));
    if (state.abKey !== String(a.id)) {
      state.abKey = String(a.id);
      state.abChart.timeScale().setVisibleLogicalRange({ from: bars.length - 48, to: bars.length + FOCUS_MARGIN_BARS });
    }
  }

  function approvalNowText(a) {
    var f = state.forming[a.asset];
    if (a.trigger_price != null) return 'tocou o gatilho em <strong>' + fmtPrice(a.trigger_price) + '</strong>';
    if (!f || f.time !== a.target_ts) return '<span class="muted">esperando a vela da entrada abrir</span>';
    var gap = a.direction === 'call' ? f.close - a.level_price : a.level_price - f.close;
    var pips = gap / pip(f.close);
    return '<strong>' + fmtPrice(f.close) + '</strong> · ' + (pips > 0
      ? 'faltam <strong>' + unitsFmt.format(pips) + ' pip</strong> até o gatilho'
      : '<strong>no gatilho</strong>');
  }

  function approvalSideHtml(a) {
    var st = apState(a.status);
    var risk = state.status && state.status.risk;
    var stake = a.demo ? fmtMoney(2) : risk ? fmtMoney(risk.next_stake) + (risk.gale_level ? ' (gale ' + risk.gale_level + ')' : '') : '—';
    var call = a.direction === 'call';
    var verb = a.strategy === 'retracao_comando' || a.strategy === SCORE
      ? (call ? 'recuar (descer) até o gatilho' : 'recuar (subir) até o gatilho') : 'tocar a marcação';
    var mode = a.demo ? 'EXEMPLO · não envia ordem' : a.auto ? 'automático com veto' : 'aprovação';
    var buttons;
    if (a.status === 'aprovado') {
      buttons = '<button class="reject big" data-act="rejeitar" data-id="' + a.id + '">' + (a.auto ? 'Cancelar esta entrada' : 'Cancelar aprovação') + '</button>';
    } else {
      buttons = '<button class="approve" data-act="aprovar" data-id="' + a.id + '">✓ Aprovar ' + (call ? 'CALL' : 'PUT') +
        (a.status === 'disparou' ? ' agora' : '') + '</button>' +
        '<button class="reject" data-act="rejeitar" data-id="' + a.id + '">Rejeitar</button>';
    }
    return '<div class="ab-head"><span class="dir big">' + (call ? '▲ CALL' : '▼ PUT') + '</span><strong>' + esc(a.asset) + '</strong></div>' +
      '<div class="muted small">' + esc(label(a.strategy)) + ' · <span class="tag">' + esc(mode) + '</span></div>' +
      (a.strategy === SCORE && a.setup ? '<div class="muted small">' + esc(capitalize(a.setup)) + '</div>' : '') +
      '<div class="ab-clock"><span class="clock" data-deadline="' + a.deadline + '">—</span><span class="clock-sub">para a janela de ' +
        a.window_seconds + ' s fechar</span></div>' +
      '<dl class="ab-facts">' +
        '<dt>Entra se</dt><dd>a vela das <strong>' + fmtTime(a.target_ts) + '</strong> ' + verb + '</dd>' +
        '<dt>Gatilho</dt><dd><strong>' + fmtPrice(a.level_price) + '</strong></dd>' +
        '<dt>Preço agora</dt><dd id="ab-now">' + approvalNowText(a) + '</dd>' +
        '<dt>Valor</dt><dd>' + stake + ' · ' + (a.demo ? 'conta demo' : accountLabel()) + '</dd>' +
        '<dt>Vencimento</dt><dd>' + fmtTime(a.target_ts + (a.timeframe || 60)) + ' (fim desta vela)</dd>' +
      '</dl>' +
      '<div class="state ' + st.cls + '"><span class="icon" aria-hidden="true">' + st.icon + '</span>' +
        esc(a.auto && a.status === 'aprovado' ? 'Automático: a ordem sai sozinha se o gatilho disparar. Cancele se não quiser.' : st.text) +
        (a.note ? ' · ' + esc(a.note) : '') + '</div>' +
      (a.strategy === 'retracao_comando' && !a.demo
        ? '<div class="muted small">Na pesquisa, só ~8 em cada 100 pedidos viram entrada: o recuo precisa vir nos 15 s. Aprovar autoriza; se o recuo não vier, nada acontece.</div>'
        : '') +
      '<div class="ab-buttons">' + buttons + '</div>' +
      (a.demo ? '<div class="muted small">Exemplo para ver como funciona: estes botões não enviam nada.</div>' : '');
  }

  function approvalChipHtml(a) {
    return '<button class="ab-chip" data-sel="' + esc(a.id) + '" aria-pressed="' + (String(a.id) === String(state.approvalSel) ? 'true' : 'false') + '">' +
      dotHtml(a.strategy) + (a.direction === 'call' ? '▲ ' : '▼ ') + esc(a.asset) +
      ' <span class="clock" data-deadline="' + a.deadline + '">—</span></button>';
  }

  // Cartão de resultado: grande e sem ambiguidade (verde = ordem enviada, cinza = nenhuma ordem, vermelho = não enviada).
  function approvalDoneHtml(a) {
    var oc = approvalOutcome(a);
    var res = oc.result ? '<div class="oc-result ' + oc.result.cls + '">' + esc(oc.result.text) + '</div>' : '';
    return '<div class="outcome ' + oc.kind + '" data-until="' + outcomeUntil(a, oc) + '" role="status">' +
      '<div class="oc-icon" aria-hidden="true">' + oc.icon + '</div>' +
      '<div class="oc-text"><div class="oc-title">' + esc(oc.title) + '</div><div class="oc-sub">' + esc(oc.reason) +
        ' · vela das ' + fmtTime(a.target_ts) + '</div></div>' + res +
    '</div>';
  }

  function updateApprovalClocks() {
    var now = Date.now() / 1000, iq = serverNow();
    Array.prototype.forEach.call(document.querySelectorAll('#approvals .clock'), function (c) {
      var left = Math.ceil(parseFloat(c.dataset.deadline) - iq);
      c.textContent = left > 0 ? left + ' s' : '0 s';
    });
    var removed = false;
    Array.prototype.forEach.call(document.querySelectorAll('#approvals .outcome'), function (el) {
      if (now >= parseFloat(el.dataset.until)) { el.remove(); removed = true; }
    });
    var big = $('#ab-big');
    if (removed && (!big || big.hidden) && !document.querySelector('#approvals .outcome')) $('#approvals').hidden = true;
  }

  function unlockAudio() {
    try {
      if (!state.audio) state.audio = new (window.AudioContext || window.webkitAudioContext)();
      if (state.audio.state === 'suspended') state.audio.resume();
    } catch (e) { state.audio = null; }
  }
  function beep(times) {
    var ctx = state.audio;
    if (!ctx) return;
    for (var i = 0; i < times; i++) {
      var o = ctx.createOscillator(), g = ctx.createGain(), t = ctx.currentTime + i * 0.22;
      o.frequency.value = 880; o.type = 'sine';
      g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.25, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.16);
      o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(t + 0.18);
    }
  }
  function alertApproval(a, kind) {
    if (a.status === 'aprovado' && kind === 'novo' && !a.veto) return;
    beep(kind === 'disparou' ? 3 : 2);
  }

  // ------------------------------------------------------------------ pedido de EXEMPLO (só na tela: nunca fala com a corretora)
  function showDemoApproval() {
    unlockAudio();
    var data = state.chartData;
    var realCandles = !!(data && data.candles && data.candles.length >= 15);
    var candles = realCandles ? data.candles.slice(-60) : syntheticCandles();
    var since = function (p) { return p.time >= candles[0].time; };
    var overlay = realCandles ? { buy_line: data.buy_line.filter(since), sell_line: data.sell_line.filter(since),
      script_marks: (data.script_marks || []).filter(since) } : null;
    var asset = (data && data.asset) || (state.config && state.config.assets[0]) || 'EURUSD-op';
    var last = candles[candles.length - 1];
    var ranges = candles.slice(-15, -1).map(function (c) { return c.high - c.low; });
    var atr = ranges.reduce(function (x, y) { return x + y; }, 0) / Math.max(1, ranges.length) || 0.0002;
    var dir = last.close >= last.open ? 'call' : 'put';
    clearTimeout(state.demoTimer);
    state.demoSeq = (state.demoSeq || 0) + 1;
    state.demoApproval = {
      id: 'exemplo-' + state.demoSeq, demo: true, asset: asset, timeframe: 60, strategy: 'retracao_comando', direction: dir,
      level_price: dir === 'call' ? last.close - 0.8 * atr : last.close + 0.8 * atr, target_ts: last.time + 60,
      deadline: serverNow() + 45, window_seconds: 15, status: 'aguardando', excerpt: candles, overlay: overlay, trigger_price: null, note: null,
      open_price: last.close
    };
    state.abKey = null;
    renderApprovals(state.status);
    window.scrollTo(0, 0);
    state.demoTimer = setTimeout(function () { finishDemo('expirou sem resposta', 'exemplo: no pedido de verdade, nada seria enviado'); }, 45000);
  }
  function syntheticCandles() {
    var out = [], p = 1.1190, t = Math.floor(Date.now() / 60000) * 60 - 60 * 60;
    for (var i = 0; i < 60; i++) {
      var o = p, c = o + (Math.random() - 0.48) * 0.0003;
      out.push({ time: t + i * 60, open: o, close: c, high: Math.max(o, c) + Math.random() * 0.0001, low: Math.min(o, c) - Math.random() * 0.0001 });
      p = c;
    }
    return out;
  }
  function decideDemo(act) {
    var a = state.demoApproval;
    if (!a || !isOpenApproval(a)) return;
    clearTimeout(state.demoTimer);
    if (act === 'rejeitar') { finishDemo('rejeitado', 'exemplo: nada foi enviado'); return; }
    a.status = 'aprovado';
    renderApprovals(state.status);
    state.demoTimer = setTimeout(function () {  // simula o preço tocando o gatilho
      a.trigger_price = a.level_price;
      finishDemo('exemplo concluído', null);
    }, 4000);
  }
  function finishDemo(status, note) {
    var a = state.demoApproval;
    if (!a) return;
    a.status = status;
    a.note = note;
    renderApprovals(state.status);
    setTimeout(function () { if (state.demoApproval === a) state.demoApproval = null; }, 13000);
  }

  function decideApproval(id, act, btn) {
    if (String(id).indexOf('exemplo-') === 0) { decideDemo(act); return; }
    unlockAudio();
    Array.prototype.forEach.call(document.querySelectorAll('#approvals button[data-id="' + id + '"]'), function (b) { b.disabled = true; });
    api('/api/approvals/' + id + '/' + act, { method: 'POST' }).catch(function (e) {
      showBanner(e.message);
      if (btn) btn.disabled = false;
    });
  }

  // ------------------------------------------------------------------ conta demo × real
  function isReal() { return state.chosenAccount === 'REAL'; }
  function accountLabel() { return isReal() ? '<span class="acct-real">conta REAL</span>' : 'conta demo'; }

  function refreshAccount() {
    return api('/api/account').then(function (info) { state.chosenAccount = info.chosen; renderAccount(info); })
      .catch(function () { renderAccount(null); });
  }

  function renderAccount(info) {
    if (info) state.accountInfo = info;
    info = state.accountInfo;
    var chosen = state.chosenAccount || (info && info.chosen) || 'PRACTICE';
    Array.prototype.forEach.call(document.querySelectorAll('#acct-switch button'), function (b) {
      b.setAttribute('aria-pressed', b.dataset.acct === chosen ? 'true' : 'false');
    });
    var real = chosen === 'REAL';
    root().classList.toggle('real-mode', real);
    $('#real-badge').hidden = !real;
    $('#chart-real-badge').hidden = !real;  // com o gráfico expandido, a barra de cima some: o aviso da conta real não
    var mini = $('#acct-mini');
    mini.textContent = real ? 'R' : 'D';
    mini.className = 'acct-mini' + (real ? ' real' : '');
    $('#side-mini').title = (real ? 'Conta REAL' : 'Conta demo') + (info && info.balance != null ? ' · saldo ' + fmtMoney(info.balance) : '') +
      (state.connected ? ' · servidor conectado' : ' · sem conexão');
    $('#orders-title').textContent = real ? 'Ordens na conta REAL' : 'Ordens na conta demo';
    renderManual();
    var el = $('#acct-balance');
    if (!info) { el.textContent = 'Saldo —'; return; }
    if (info.error) { el.textContent = 'Sem conexão com a IQ'; el.title = info.error; return; }
    el.title = '';
    if (info.balance == null) { el.textContent = 'Saldo —'; return; }
    var cur = info.currency || 'USD', fmt;
    try { fmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: cur }); }
    catch (e) { fmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2 }); }
    var sameAccount = info.account === chosen;
    el.innerHTML = 'Saldo ' + (real ? '<span class="acct-real">real</span>' : 'demo') + ': <strong>' + fmt.format(info.balance) + '</strong>' +
      (sameAccount ? '' : ' <span class="muted">(conectando na conta escolhida…)</span>');
  }

  function chooseAccount(acct) {
    var s = state.status;
    if (isBusy(s)) { showBanner('Pare o bot antes de trocar de conta.'); return; }
    if (acct === (state.chosenAccount || 'PRACTICE')) return;
    var body = { account: acct };
    if (acct === 'REAL') {
      var typed = window.prompt(REAL_WARNING, '');
      if (typed == null) return;
      if (typed.trim().toUpperCase() !== 'REAL') { showBanner('Conta real não ativada: era preciso digitar REAL.'); return; }
      body.confirm = 'REAL';
    }
    $('#acct-balance').textContent = 'Trocando de conta…';
    api('/api/account', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
      .then(function (info) {
        state.chosenAccount = info.chosen;
        renderAccount(info);
        hideBanner();
        loadConfig(state.page === 'config');
      })
      .catch(function (e) { showBanner(e.message); refreshAccount(); });
  }

  // ------------------------------------------------------------------ ordens
  function renderRisk(risk) {
    var el = $('#risk-body');
    if (!risk) { el.innerHTML = ''; return; }
    var c = risk.config;
    var cells = [
      ['Resultado', '<span class="' + signClass(risk.pnl) + '">' + fmtMoney(risk.pnl, true) + '</span>'],
      ['Ordens', intFmt.format(risk.trades) + (risk.open_orders ? ' + ' + risk.open_orders + ' aberta' + (risk.open_orders > 1 ? 's' : '') : '')],
      ['W · L', risk.wins + ' · ' + risk.losses]
    ];
    var html = '<div class="orders-cap">Nesta sessão</div>' +
      cells.map(function (x) { return '<div class="cell"><div class="v">' + x[1] + '</div><div class="l">' + x[0] + '</div></div>'; }).join('');
    html += '<div class="risk-line muted small">Entrada ' + fmtMoney(c.stake) + ' · stop win ' + (c.stop_win ? fmtMoney(c.stop_win) : 'desligado') +
      ' · stop loss ' + (c.stop_loss ? fmtMoney(c.stop_loss) : 'desligado') +
      (c.martingale ? ' · martingale até ' + c.gale_levels + ' gale' + (c.gale_levels > 1 ? 's' : '') : '') + filtersText() + '</div>';
    if (c.martingale && risk.gale_level > 0) {
      html += '<div class="blocked">Próxima entrada aprovada é o gale ' + risk.gale_level + ': ' + fmtMoney(risk.next_stake) + '</div>';
    }
    if (!risk.can_trade) html += '<div class="blocked">Novas ordens bloqueadas: ' + esc(risk.reason) + '</div>';
    var mode = state.status && state.status.mode;
    if (mode === 'sinais' && !risk.trades && !risk.open_orders) {
      html += '<div class="risk-line muted small">No modo "só sinais" nenhuma ordem é enviada. Escolha aprovação ou automático na Configuração.</div>';
    } else if (mode === 'automatico') {
      html += '<div class="risk-line muted small">Modo automático: as ordens saem sozinhas na ' + accountLabel() + ', sem cartão na tela.</div>';
    }
    el.innerHTML = html;
  }

  // Situação de uma ordem em palavras simples: enviada ou não, e o resultado.
  // label = selo curto (enviada ou não); detail = o que aconteceu depois.
  function orderState(o) {
    switch (o.status) {
      case 'enviando': return { kind: 'sent', label: 'Enviando…', detail: '' };
      case 'aberta': return { kind: 'sent', label: 'Enviada', detail: 'aguardando…', cls: 'warn' };
      case 'win': return { kind: 'sent', label: 'Enviada', detail: 'ganhou', cls: 'good' };
      case 'loss': return { kind: 'sent', label: 'Enviada', detail: 'perdeu', cls: 'bad' };
      case 'empate': return { kind: 'sent', label: 'Enviada', detail: 'empate', cls: '' };
      case 'sem_resultado': return { kind: 'sent', label: 'Enviada', detail: 'sem resultado', cls: 'warn' };
      default: return { kind: 'fail', label: 'Não enviada', detail: '' };  // bloqueada / erro
    }
  }

  // Filtros de entrada da Configuração, para a linha da gestão de risco ("payout mín. 80% · das 09:00 às 17:00").
  function filtersText() {
    var cfg = state.config;
    if (!cfg) return '';
    var out = '';
    if (cfg.min_payout != null) out += ' · payout mín. ' + Math.round(cfg.min_payout * 100) + '%';
    if (cfg.hours_start && cfg.hours_end) out += ' · opera das ' + cfg.hours_start + ' às ' + cfg.hours_end;
    return out;
  }

  function refreshOrders() {
    api('/api/orders?period=hoje&limit=100').then(function (rows) {
      rows.forEach(function (o) { state.ordersById[o.id] = o; });
      var el = $('#orders');
      if (!rows.length) {
        el.innerHTML = '<li class="empty">Nenhuma ordem hoje.</li>';
        return;
      }
      el.innerHTML = rows.map(function (o) {
        var st = orderState(o);
        var money = o.profit != null && st.kind !== 'fail' ? ' ' + fmtMoney(o.profit, true) : '';
        var profit = st.detail ? '<div class="oc-res ' + (st.cls || '') + '">' + esc(st.detail + money) + '</div>' : '';
        return '<li title="' + esc(o.error || '') + '"><span class="when">' + fmtTime(o.requested_at) + '</span>' +
          '<div class="what"><div class="line1">' + dirHtml(o.direction) + ' <span class="muted small">' + esc(o.asset) + '</span>' +
            (o.strategy === MANUAL ? ' <span class="manual-tag">MANUAL</span>' : '') + '</div>' +
          '<div class="line2">' + fmtMoney(o.amount) + (o.account === 'REAL' ? ' · <span class="acct-real">REAL</span>' : ' · demo') +
            (o.gale ? ' · gale ' + o.gale : '') + (o.status === 'aberta' && o.expires_at ? ' · vence ' + fmtTime(o.expires_at) : '') +
            (st.kind === 'fail' && o.error ? ' · ' + esc(o.error) : '') + '</div></div>' +
          '<div class="right"><span class="oc-pill ' + st.kind + '">' + esc(st.label) + '</span>' + profit + '</div></li>';
      }).join('');
      if (state.status) { renderApprovals(state.status); renderArmed(state.status); }
      renderManual();
    }).catch(function () {});
  }

  function updateStatusSub() {
    var s = state.status;
    var el = $('#status-sub');
    if (!isBusy(s)) { el.textContent = ''; return; }
    if (s.progress) { el.textContent = s.progress; return; }
    var n = (s.assets || []).length;
    var what = n > 1 ? n + ' pares' : (s.asset || '');
    el.textContent = what + ' · M' + (s.timeframe / 60) + (s.status === 'rodando' && s.started_at ? ' · ' + elapsed(s.started_at) : '') +
      reconnectNote(s.connection);
    var d = s.connection && s.connection.last_drop;
    el.title = d ? 'Última queda: ' + fmtTime(d.at) + ' (' + d.reason + '). Voltou sozinho às ' + fmtTime(d.back_at) +
      ' na tentativa ' + d.attempts + '.' : '';
  }
  function toggleBot() {
    var s = state.status;
    var busy = isBusy(s);
    var btn = $('#btn-toggle');
    btn.disabled = true;
    if (busy) {
      btn.textContent = 'Parando…';
      api('/api/bot/stop', { method: 'POST' }).then(function (st) { renderStatus(st); refreshCurrent(); })
        .catch(function (e) { showBanner(e.message); btn.disabled = false; });
      return;
    }
    unlockAudio();
    // Sem corpo: o bot usa os pares e a vela da Configuração.
    api('/api/bot/start', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: '{}' })
      .then(renderStatus)
      .catch(function (e) { showBanner(e.message); btn.disabled = false; });
  }
  function showBanner(msg, kind) { var b = $('#banner'); b.textContent = msg; b.classList.toggle('warn', kind === 'warn'); b.hidden = false; }
  function hideBanner() { $('#banner').hidden = true; }

  // Aviso enquanto o bot reconecta sozinho (não é erro: ninguém precisa fazer nada).
  function reconnectText(c) {
    var text = c.initial
      ? 'A IQ Option não respondeu ao entrar. O bot está tentando de novo sozinho' + (c.attempt ? ', tentativa ' + c.attempt : '') +
        '. Assim que conectar, ele começa; não precisa fazer nada.'
      : 'A conexão com a IQ Option caiu' + (c.since ? ' às ' + fmtTime(c.since) : '') +
        (c.reason ? ' (' + c.reason + ')' : '') + '. O bot está reconectando sozinho' +
        (c.attempt ? ', tentativa ' + c.attempt : '') + '. Nenhuma ordem sai até voltar; não precisa fazer nada.';
    if (c.last_error && c.attempt > 1) text += ' Última tentativa: ' + c.last_error;
    return text;
  }
  // "reconectou 2× · última às 03:14 (fora 1 min)" no status, depois que voltou.
  function reconnectNote(c) {
    if (!c || !c.drops || c.state !== 'ok' || !c.last_drop) return '';
    var d = c.last_drop, away = Math.max(1, Math.round((d.back_at - d.at) / 60));
    return ' · reconectou ' + c.drops + '× (última às ' + fmtTime(d.back_at) + ', ' + away + ' min fora)';
  }

  // ------------------------------------------------------------------ indicadores (Painel e Desempenho)
  function renderKpis(prefix, st) {
    var t = st.total;
    var count = t.n + t.draws;
    var profit = $('#' + prefix + '-profit');
    profit.textContent = count ? fmtUnits(t.profit) : '—';
    profit.className = 'hero-value ' + (count ? signClass(t.profit) : '');
    $('#' + prefix + '-wr').textContent = t.n ? fmtPct(t.winrate) : '—';
    $('#' + prefix + '-wr-sub').innerHTML = t.n
      ? 'IC 95% ' + fmtPct(t.ci_low) + '–' + fmtPct(t.ci_high) + (t.n < MIN_SAMPLE ? '<span class="warn-chip">amostra pequena</span>' : '')
      : 'sem entradas avaliadas';
    $('#' + prefix + '-n').textContent = intFmt.format(count);
    $('#' + prefix + '-n-sub').textContent = intFmt.format(t.wins) + ' wins · ' + intFmt.format(t.losses) + ' losses · ' + intFmt.format(t.draws) + ' empates';
    renderWl($('#' + prefix + '-wl'), t);
    $('#' + prefix + '-be').textContent = fmtPct(st.breakeven);
  }
  function renderWl(el, t) {
    var total = t.wins + t.losses + t.draws;
    if (!total) { el.innerHTML = ''; return; }
    el.innerHTML = [['w', t.wins], ['l', t.losses], ['e', t.draws]].filter(function (p) { return p[1] > 0; })
      .map(function (p) { return '<span class="' + p[0] + '" style="flex:' + p[1] + '"></span>'; }).join('');
  }

  // ------------------------------------------------------------------ PAINEL
  function refreshPainel() { refreshChart(); refreshToday(); refreshOrders(); }

  function refreshToday() {
    renderScope();
    api('/api/stats?period=hoje&origin=ao_vivo' + scopeQuery()).then(function (st) {
      renderKpis('p', st);
      $('#p-profit-sub').textContent = !st.total.n && !st.total.draws
        ? 'nenhuma entrada hoje (só entra quando o gatilho dispara)'
        : 'em entradas · ganho = +payout, perda = −1';
    }).catch(function () {});
    // O placar mostra cada estratégia ligada, inclusive as que só observam.
    api('/api/stats?period=hoje&origin=ao_vivo').then(function (st) { renderBoard(st.by_strategy); }).catch(function () {});
    api('/api/signals?period=hoje&origin=ao_vivo&limit=200' + scopeQuery()).then(renderFeed).catch(function () {});
  }

  function renderScope() {
    if (!state.config) return;
    var main = mainStrategies();
    if (!main.length) {
      $('#p-scope').innerHTML = '<span>Nenhuma estratégia ligada. Escolha em Configuração.</span>';
      return;
    }
    var observing = strategiesIn(['observe']).filter(function (n) { return main.indexOf(n) < 0; });
    $('#p-scope').innerHTML = '<span>Números e entradas de hoje: ' + main.map(function (n) { return stratHtml(n); }).join(' ') + '</span>' +
      (observing.length ? '<span class="muted small">Só observando: ' + esc(observing.map(label).join(', ')) + '</span>' : '');
  }
  // As que estão rodando agora (ligar ou desligar vale no próximo início); com o bot parado, as ligadas.
  function shownStrategies() {
    var s = state.status;
    return isBusy(s) && s.active_strategies ? s.active_strategies : strategiesIn(['operate', 'observe']);
  }

  function renderBoard(groups) {
    var byKey = {};
    groups.forEach(function (g) { byKey[g.key] = g; });
    $('#p-board').innerHTML = shownStrategies().map(function (name) {
      var g = byKey[name] || { n: 0, draws: 0, wins: 0, losses: 0, winrate: null, profit: 0 };
      return '<tr><td>' + stratHtml(name) + '<span class="tag">' + (strategyState(name) === 'operate' ? 'opera' : 'observa') + '</span>' +
        '</td><td class="num">' + intFmt.format(g.n + g.draws) + '</td><td class="num">' +
        g.wins + ' · ' + g.losses + '</td><td class="num">' + fmtPct(g.winrate) + '</td><td class="num ' + signClass(g.profit) + '">' +
        ((g.n + g.draws) ? fmtUnits(g.profit) : '—') + '</td></tr>';
    }).join('');
  }

  function renderFeed(rows) {
    $('#feed-count').textContent = rows.length ? intFmt.format(rows.length) + ' hoje' : '';
    var el = $('#feed');
    if (!rows.length) { el.innerHTML = '<li class="empty">Nenhuma entrada ao vivo hoje ainda. Com o bot rodando, cada sinal aparece aqui na hora.</li>'; return; }
    el.innerHTML = rows.map(function (r) {
      var profit = r.result === 'pendente' || r.result === 'cancelado' ? '' :
        '<div class="' + signClass(r.profit) + '">' + fmtUnits(r.profit) + '</div>';
      return '<li><span class="when">' + fmtTime(r.candle_ts) + '</span>' +
        '<div class="what"><div class="line1">' + dotHtml(r.strategy) + dirHtml(r.direction) + ' <span class="muted small">' + esc(r.asset) + '</span></div>' +
        '<div class="line2">' + esc(label(r.strategy)) + ' · ' + esc(r.setup) + '</div></div>' +
        '<div class="right">' + resHtml(r.result) + profit + '</div></li>';
    }).join('');
  }

  function chartLimit() {
    var since = state.showBacktest && state.retroData && state.retroData.since_ts;
    if (!since) return CHART_BARS;
    var tf = (state.chartData && state.chartData.timeframe) || 60;
    return Math.max(CHART_BARS, Math.min(CHART_BARS_MAX, Math.ceil((serverNow() - since) / tf) + 5));
  }
  function refreshChart() {
    return api('/api/chart?limit=' + chartLimit()).then(renderChart).then(refreshReading).then(refreshRetro).catch(function () {});
  }

  // ------------------------------------------------------------------ retroativo do dia
  // Conta o que as setas do backtest mostram: só as estratégias ligadas nos botões do gráfico.
  function refreshRetro() {
    if (!state.showBacktest) { renderRetro(); return null; }
    var seq = ++state.retroSeq;
    return api('/api/backtest/today').then(function (data) {
      if (seq !== state.retroSeq) return;
      state.retroData = data;
      renderRetro();
    }).catch(function () {});
  }
  function retroScopes(asset) {
    var s = state.status;
    var pairs = isBusy(s) && s.assets && s.assets.length ? s.assets.map(function (a) { return a.asset; }) : (state.config ? state.config.assets : []);
    // OTC e mercado normal não se somam: têm estatística separada.
    var same = pairs.filter(function (p) { return isOtc(p) === isOtc(asset); });
    var scopes = asset ? [{ title: asset, assets: [asset] }] : [];
    if (same.length > 1) scopes.push({ title: same.length + (isOtc(asset) ? ' pares OTC' : ' pares normais'), assets: same });
    return scopes;
  }
  function retroCells(rows) {
    var t = { wins: 0, losses: 0, draws: 0, profit: 0 };
    rows.forEach(function (g) { t.wins += g.wins; t.losses += g.losses; t.draws += g.draws; t.profit += g.profit; });
    var n = t.wins + t.losses;
    if (!n && !t.draws) return '<td class="num muted">0</td><td class="num muted">—</td><td class="num muted">—</td>';
    return '<td class="num">' + t.wins + ' W · ' + t.losses + ' L' + (t.draws ? ' · ' + t.draws + ' empate' + (t.draws > 1 ? 's' : '') : '') + '</td>' +
      '<td class="num">' + (n ? fmtPct(t.wins / n) : '—') + '</td><td class="num ' + signClass(t.profit) + '">' + fmtUnits(t.profit) + '</td>';
  }
  function renderRetro() {
    var el = $('#bt-count');
    if (!state.showBacktest || !state.retroData) { el.hidden = true; return; }
    el.hidden = false;
    var names = shownStrategies().filter(function (n) { return state.visible[n]; });
    var scopes = retroScopes(state.chartData && state.chartData.asset);
    var inScopes = {};
    scopes.forEach(function (sc) { sc.assets.forEach(function (a) { inScopes[a] = true; }); });
    var groups = state.retroData.groups.filter(function (g) { return inScopes[g.asset] && names.indexOf(g.strategy) >= 0; });
    if (!groups.length) {
      el.innerHTML = '<div class="bt-head"><strong>Retroativo de hoje</strong><span class="muted">Nenhuma entrada. O cálculo roda quando o bot inicia.</span></div>';
      return;
    }
    var first = Math.min.apply(null, groups.map(function (g) { return g.first_ts; }));
    var last = Math.max.apply(null, groups.map(function (g) { return g.last_ts; }));
    el.innerHTML = '<div class="bt-head"><strong>Retroativo de hoje</strong><span class="muted">primeira às ' + fmtTime(first) + ' · última às ' + fmtTime(last) +
        ' · calculado ao iniciar o bot; depois disso, as entradas contam como ao vivo</span></div>' +
      '<div class="table-wrap"><table class="data"><thead><tr><th rowspan="2">Estratégia</th>' +
      scopes.map(function (sc) { return '<th class="bt-scope" colspan="3">' + esc(sc.title) + '</th>'; }).join('') + '</tr><tr>' +
      scopes.map(function () { return '<th class="num">W · L</th><th class="num">Acerto</th><th class="num">Resultado</th>'; }).join('') + '</tr></thead><tbody>' +
      names.map(function (name) {
        return '<tr><td>' + stratHtml(name) + '</td>' + scopes.map(function (sc) {
          return retroCells(groups.filter(function (g) { return g.strategy === name && sc.assets.indexOf(g.asset) >= 0; }));
        }).join('') + '</tr>';
      }).join('') + '</tbody></table></div>';
  }

  // ------------------------------------------------------------------ gráfico expandido
  function setChartExpanded(on) {
    if (state.chartExpanded === on) return;
    state.chartExpanded = on;
    $('#chart-card').classList.toggle('expanded', on);
    document.documentElement.classList.toggle('chart-open', on);
    var btn = $('#chart-expand');
    btn.setAttribute('aria-pressed', on ? 'true' : 'false');
    btn.title = on ? 'Voltar ao painel (Esc)' : 'Só o gráfico, em tela cheia';
    $('#chart-expand-text').textContent = on ? 'Sair' : 'Expandir';
    if (on) {
      // Tela cheia do documento (não só do cartão), para o pedido de aprovação continuar aparecendo por cima.
      if (!document.fullscreenElement) {
        document.documentElement.requestFullscreen().then(function () { state.chartOwnsFullscreen = true; }).catch(function () { /* ocupa a janela inteira mesmo assim */ });
      }
    } else if (state.chartOwnsFullscreen) {
      state.chartOwnsFullscreen = false;
      if (document.fullscreenElement) document.exitFullscreen().catch(function () {});
    }
  }

  // ------------------------------------------------------------------ leitura do estudo no gráfico
  // Caixa = lote · faixa = região (com o lado da leitura) · rótulo = padrão na vela. Só desenho: nenhuma estratégia usa isto ainda.
  var STUDY_STRATEGIES = ['retracao_lote', 'reversao_forca', 'reversao_indecisao'];
  var READING_LABELS = ['NA', 'NB', 'NP', 'DP', 'TP', 'FA', 'FB', 'NL', 'TR', 'DS', 'TD1', 'TD2', 'TD3', 'TDI', 'TD', 'VD', 'DF'];
  var READING_BARS = 45;
  var SCENARIO_INFO = {
    topos_fundos: { text: 'Topos e fundos', note: 'o melhor cenário para a lógica do preço', cls: 'good' },
    tendencia: { text: 'Tendência', note: 'melhor para operar fluxo', cls: '' },
    consolidacao: { text: 'Consolidado', note: 'o estudo não recomenda operar', cls: 'warn' }
  };
  var LOT_CAUSE = { reversao: 'reversão', comando: 'comando', fim_de_taxa: 'fim de taxa', rompimento: 'rompimento' };
  var readingPrimitive = {
    data: null, chart: null, series: null, request: null,
    attached: function (p) { this.chart = p.chart; this.series = p.series; this.request = p.requestUpdate; },
    detached: function () { this.chart = this.series = this.request = null; },
    updateAllViews: function () {},
    setData: function (data) { this.data = data; if (this.request) this.request(); },
    paneViews: function () { return [{ zOrder: function () { return 'bottom'; }, renderer: function () { return { draw: drawReading }; } }]; }
  };
  function drawReading(target) {
    var p = readingPrimitive, d = p.data;
    if (!d || !p.chart) return;
    var ts = p.chart.timeScale(), half = ts.options().barSpacing / 2;
    var buy = cssVar('--line-buy'), sell = cssVar('--line-sell'), neutral = cssVar('--text-muted');
    target.useMediaCoordinateSpace(function (scope) {
      var ctx = scope.context;
      function box(from, to, low, high, color, fill, extendTo) {
        var x1 = ts.timeToCoordinate(from), x2 = extendTo != null ? extendTo : ts.timeToCoordinate(to);
        var y1 = p.series.priceToCoordinate(high), y2 = p.series.priceToCoordinate(low);
        if (x1 == null || x2 == null || y1 == null || y2 == null) return null;
        ctx.globalAlpha = fill;
        ctx.fillStyle = color;
        ctx.fillRect(x1 - half, y1, x2 - x1 + half * 2, Math.max(1, y2 - y1));
        return { x1: x1 - half, x2: x2 + half, y1: y1, y2: y2 };
      }
      d.lots.forEach(function (lot) {
        var color = lot.direction > 0 ? buy : sell;
        var b = box(lot.from, lot.to, lot.low, lot.high, color, 0.07);
        if (!b) return;
        ctx.globalAlpha = 0.55;
        ctx.strokeStyle = color;
        ctx.lineWidth = 1;
        ctx.strokeRect(b.x1, b.y1, b.x2 - b.x1, Math.max(1, b.y2 - b.y1));
      });
      var right = scope.mediaSize.width;
      ctx.font = '10px system-ui, sans-serif';
      d.regions.forEach(function (r) {
        var color = r.side > 0 ? buy : r.side < 0 ? sell : neutral;
        var b = box(r.from, r.to, r.low, r.high, color, r.active ? 0.22 : 0.06, r.active ? right : null);
        if (!b) return;
        ctx.globalAlpha = r.active ? 0.9 : 0.3;
        ctx.fillRect(b.x1, b.y1, b.x2 - b.x1, 1);
        if (b.y2 - b.y1 > 1) ctx.fillRect(b.x1, b.y2 - 1, b.x2 - b.x1, 1);
        if (r.active) {
          ctx.globalAlpha = 1;
          ctx.fillText(r.code, Math.max(b.x1 + 2, 2), b.y1 - 2);
        }
      });
      ctx.globalAlpha = 1;
    });
  }
  function refreshReading() {
    var legend = $('#reading-legend');
    if (!state.showReading || !state.chartData || !state.chartData.asset) {
      state.readingData = null;
      state.readingByTime = {};
      legend.hidden = true;
      readingPrimitive.setData(null);
      return null;
    }
    return api('/api/reading?limit=240&asset=' + encodeURIComponent(state.chartData.asset)).then(function (data) {
      state.readingData = data;
      state.readingByTime = {};
      data.tags.forEach(function (t) { (state.readingByTime[t.time] = state.readingByTime[t.time] || []).push(t); });
      readingPrimitive.setData(data);
      applyMarkers();
      var sc = SCENARIO_INFO[data.scenario];
      legend.innerHTML = (sc ? '<span class="scenario ' + sc.cls + '">Agora: <strong>' + sc.text + '</strong> · ' + sc.note + ' (pág. 223)</span>' : '') +
        '<span class="key">Caixa = lote · faixa = região (verde, buscou é CALL; vermelha, buscou é PUT; cinza, indecisão)</span>' +
        '<span class="key">NA nova alta · NB nova baixa · NP nova posição · DP dupla · TP tripla · FA/FB futuro · NL nano-lote · TD taxa dividida · TR transferência · DS desinstalação · DF defesa · VD vela de força na defesa</span>' +
        '<span class="key">Só desenho: nenhuma estratégia usa esta leitura ainda. Passe o mouse na vela para ver cada padrão com a página.</span>';
      legend.hidden = false;
    });
  }
  function readingMarkers() {
    var d = state.readingData;
    if (!state.showReading || !d) return [];
    return d.tags.filter(function (t) { return READING_LABELS.indexOf(t.code) >= 0; }).map(function (t) {
      return { time: t.time, position: t.direction > 0 ? 'belowBar' : 'aboveBar', shape: 'circle', size: 0.4, text: t.code,
        color: cssVar(t.direction > 0 ? '--line-buy' : t.direction < 0 ? '--line-sell' : '--text-secondary') };
    });
  }
  function readingReadout(time) {
    if (!state.showReading || !state.readingData) return '';
    var html = (state.readingByTime[time] || []).map(function (t) {
      return esc(t.label) + (t.detail ? ' (' + esc(t.detail) + ')' : '') + ' <span class="muted">pág. ' + t.page + '</span>';
    }).join(' · ');
    var lot = state.readingData.lots.filter(function (l) { return l.from <= time && time <= l.to; }).pop();
    if (lot) {
      html += (html ? ' · ' : '') + 'Lote de ' + (lot.direction > 0 ? 'compra' : 'venda') + ', aberto por ' + (LOT_CAUSE[lot.open_cause] || lot.open_cause) +
        (lot.close_cause ? ', fechado por ' + (LOT_CAUSE[lot.close_cause] || lot.close_cause) : '');
    }
    return html ? ' &nbsp;|&nbsp; ' + html : '';
  }

  function renderChart(data) {
    state.chartData = data;
    if (!mainChart) return;
    $('#chart-title').textContent = data.asset ? data.asset + ' · M' + ((data.timeframe || 60) / 60) : 'Gráfico';
    if (!data.candles || !data.candles.length) {
      candleSeries.setData([]); buySeries.setData([]); sellSeries.setData([]); applyMarkers();
      $('#p-price').textContent = '—';
      var w = state.status && state.status.watch;
      $('#p-price-sub').textContent = w && w.asset === data.asset && w.state !== 'sem_conexao' ? 'carregando as velas…' : 'sem velas deste par ainda';
      renderReading(null);
      return;
    }
    var last = data.candles[data.candles.length - 1];
    var prec = precision(last.close);
    candleSeries.applyOptions({ priceFormat: { type: 'price', precision: prec, minMove: Math.pow(10, -prec) } });
    var bars = data.candles.slice();
    if (data.forming && data.forming.time > last.time) bars.push(data.forming);
    candleSeries.setData(bars);
    var showLines = scriptOn('ldp_lines') && !state.showReading;  // na leitura do estudo, os scripts saem para não embolar
    buySeries.applyOptions({ visible: showLines });
    sellSeries.applyOptions({ visible: showLines });
    buySeries.setData(data.buy_line);
    sellSeries.setData(data.sell_line);
    applyMarkers();

    state.priceLines.forEach(function (pl) { candleSeries.removePriceLine(pl); });
    var sup = data.levels.filter(function (l) { return l.role === 'suporte'; })[0];
    var res = data.levels.filter(function (l) { return l.role === 'resistencia'; })[0];
    state.priceLines = [sup, res].filter(Boolean).map(function (lv) {
      return candleSeries.createPriceLine({
        price: lv.price, color: cssVar('--level'), lineWidth: 1, lineStyle: LWC.LineStyle.Dotted,
        axisLabelVisible: true, title: (lv.role === 'suporte' ? 'Suporte' : 'Resistência') + ' F' + lv.strength
      });
    });

    var key = data.asset + ':' + data.timeframe;
    if (state.chartKey !== key) {
      mainChart.timeScale().setVisibleLogicalRange({ from: bars.length - 90, to: bars.length + FOCUS_MARGIN_BARS });
      state.chartKey = key;
    }
    var current = bars[bars.length - 1];
    $('#p-price').textContent = fmtPrice(current.close);
    $('#p-price-sub').textContent = data.forming ? 'vela atual · ' + fmtTime(data.forming.time) : 'última vela · ' + fmtTime(last.time);
    renderReading(data.reading);
  }

  function applyMarkers() {
    var d = state.chartData;
    if (!d || !candleSeries) return;
    state.markersByTime = {};
    state.scriptMarksByTime = {};
    state.entriesByTime = {};
    var markers = [];
    var sent = {};  // entrada que virou ordem: a marca de ENTRADA fala por ela
    (d.entries || []).forEach(function (o) {
      if (o.signal_id != null) sent[o.signal_id] = true;
      (state.entriesByTime[o.time] = state.entriesByTime[o.time] || []).push(o);
      markers.push(entryMarker(o));
    });
    (d.markers || []).forEach(function (m) {
      if (!state.visible[m.strategy]) return;
      if (m.origin === 'backtest' && !state.showBacktest) return;
      (state.markersByTime[m.time] = state.markersByTime[m.time] || []).push(m);
      if (sent[m.id]) return;
      markers.push({  // só anotada: seta pequena, na cor da estratégia
        time: m.time, position: m.direction === 'call' ? 'belowBar' : 'aboveBar', size: 0.7,
        color: strategyColor(m.strategy), shape: m.direction === 'call' ? 'arrowUp' : 'arrowDown',
        text: (RESULT_INFO[m.result] || { icon: '' }).icon
      });
    });
    if (!state.showReading) {
      if (scriptOn('ldp_arrows')) {
        (d.script_marks || []).forEach(function (m) {
          (state.scriptMarksByTime[m.time] = state.scriptMarksByTime[m.time] || []).push({ name: label('ldp_v13'), mark: m });
          markers.push(scriptMarker(m));
        });
      }
      (d.wiki_marks || []).forEach(function (m) {
        (state.scriptMarksByTime[m.time] = state.scriptMarksByTime[m.time] || []).push({ name: label('wiki_pro_v21'), mark: m });
        markers.push(Object.assign(scriptMarker(m), { color: strategyColor('wiki_pro_v21'), size: 0.8,
          text: 'WIKI ' + (m.direction === 'call' ? 'CALL' : 'PUT') }));
      });
    }
    markers = markers.concat(readingMarkers());
    candleSeries.setMarkers(markers.sort(byTime));
    renderEntryLines(d.entries || []);
  }

  // Ordem aberta: uma linha no preço de entrada, para ver se está ganhando até o vencimento.
  function renderEntryLines(entries) {
    state.entryLines.forEach(function (pl) { candleSeries.removePriceLine(pl); });
    state.entryLines = entries.filter(function (o) {
      return (o.status === 'enviando' || o.status === 'aberta') && o.price != null;
    }).map(function (o) {
      return candleSeries.createPriceLine({
        price: o.price, color: cssVar('--text-primary'), lineWidth: 2, lineStyle: LWC.LineStyle.Solid,
        axisLabelVisible: true, title: 'Entrada ' + (o.direction === 'call' ? 'CALL' : 'PUT')
      });
    });
  }

  function onCrosshair(param) {
    var out = $('#readout');
    if (!param || param.time == null || !param.seriesData) {
      out.textContent = 'Passe o mouse sobre uma vela para ver os detalhes.';
      out.classList.add('idle');
      return;
    }
    var bar = param.seriesData.get(candleSeries);
    if (!bar) return;
    var html = '<strong>' + fmtDateTime(param.time) + '</strong> · A ' + fmtPrice(bar.open) + ' · M ' + fmtPrice(bar.high) +
      ' · m ' + fmtPrice(bar.low) + ' · F ' + fmtPrice(bar.close);
    (state.entriesByTime[param.time] || []).forEach(function (o) {
      var outcome = RESULT_INFO[o.status] ? resHtml(o.status) + (o.profit != null ? ' ' + fmtMoney(o.profit, true) : '')
        : esc((ORDER_INFO[o.status] || { text: o.status }).text);
      var manual = o.strategy === MANUAL;
      html += ' &nbsp;|&nbsp; <strong>' + (manual ? 'MANUAL' : 'ENTRADA') + '</strong> ' + dirHtml(o.direction) + ' ' + fmtPrice(o.price) +
        ' · ' + fmtMoney(o.amount) + (manual ? '' : ' · ' + stratHtml(o.strategy)) + ' ' + outcome;
    });
    (state.markersByTime[param.time] || []).forEach(function (s) {
      html += ' &nbsp;|&nbsp; ' + stratHtml(s.strategy) + ' ' + dirHtml(s.direction) + ' ' + esc(s.setup) + ' ' + resHtml(s.result);
    });
    (state.scriptMarksByTime[param.time] || []).forEach(function (s) {
      html += ' &nbsp;|&nbsp; <span class="muted">script ' + esc(s.name) + ':</span> ' + dirHtml(s.mark.direction) + ' ' + esc(s.mark.setup);
    });
    html += readingReadout(param.time);
    out.innerHTML = html;
    out.classList.remove('idle');
  }

  function onTick(asset, candle) {
    state.forming[asset] = candle;
    var sel = state.approvalSelObj;
    if (sel && sel.asset === asset && state.abSeries && candle.time === sel.target_ts) {
      // pedido aberto desse par: a vela da entrada se mexe ao vivo no gráfico grande
      try { state.abSeries.update(candle); } catch (e) { /* vela fora de ordem: ignora */ }
      var now = $('#ab-now');
      if (now) now.innerHTML = approvalNowText(sel);
    }
    if (!candleSeries || !state.chartData || state.chartData.asset !== asset) return;
    try { candleSeries.update(candle); } catch (e) { return; }
    $('#p-price').textContent = fmtPrice(candle.close);
    $('#p-price-sub').textContent = 'vela atual · ' + fmtTime(candle.time);
  }

  function renderToggles() {
    $('#script-toggles').innerHTML = shownStrategies().map(function (n) {
      return '<button class="toggle" data-s="' + n + '" aria-pressed="' + (state.visible[n] ? 'true' : 'false') + '">' + dotHtml(n) + esc(label(n)) + '</button>';
    }).join('');
  }
  function renderLineLegend() {
    $('#line-legend').innerHTML =
      '<span class="key"><strong>ENTRADA CALL / PUT</strong> · ordem enviada pelo bot, com o preço e o resultado (✓ ✗ …)</span>' +
      '<span class="key"><strong>MANUAL CALL / PUT</strong> · entrada que você fez na mão</span>' +
      '<span class="key">▲▼ pequena · entrada só anotada pela estratégia, sem ordem</span>' +
      (scriptOn('ldp_arrows') && !state.showReading ? '<span class="key">▲ CALL ▼ PUT · script LDP v1.3 (só desenho, não decide entrada)</span>' : '') +
      (scriptOn('wiki_pro') && !state.showReading ? '<span class="key">WIKI CALL / PUT · script WIKI PRO (só desenho, não decide entrada)</span>' : '') +
      (scriptOn('ldp_lines') && !state.showReading
        ? '<span class="key"><span class="line-key" style="background:' + cssVar('--line-buy') + '"></span>Linha verde · 50% do último comando de alta</span>' +
          '<span class="key"><span class="line-key" style="background:' + cssVar('--line-sell') + '"></span>Linha vermelha · 50% do último comando de baixa</span>'
        : '') +
      '<span class="key"><span class="dotted-key"></span>Suporte / resistência mais próximos (apostila · F = força 1–3)</span>';
  }

  function renderReading(r) {
    var el = $('#reading');
    if (!r) { el.innerHTML = '<p class="muted">Inicie o bot para ver a leitura.</p>'; return; }
    var structs = r.estruturas.length
      ? '<div class="chips">' + r.estruturas.map(function (s) {
          return '<span class="chip">' + esc(STRUCT_LABELS[s.name] || s.name) + ' <span class="muted">p.' + s.page + '</span></span>';
        }).join('') + '</div>'
      : '<span class="muted">nenhuma</span>';
    function lvl(l) {
      if (!l) return '<span class="muted">nenhum por perto</span>';
      return fmtPrice(l.price) + ' <span class="muted">· a ' + unitsFmt.format(l.distance / pip(r.close)) + ' pip · força ' + l.strength + '</span>' +
        '<div class="muted small">' + l.sources.map(sourceLabel).map(esc).join(' · ') + '</div>';
    }
    var html = '<dl>' +
      '<dt>Vela</dt><dd>' + fmtDateTime(r.ts) + ' · fechou ' + fmtPrice(r.close) + '</dd>' +
      '<dt>Classe</dt><dd>' + esc(CLASS_LABELS[r.classe] || r.classe) + '</dd>' +
      '<dt>Estruturas</dt><dd>' + structs + '</dd>' +
      '<dt>Suporte</dt><dd>' + lvl(r.support) + '</dd>' +
      '<dt>Resistência</dt><dd>' + lvl(r.resistance) + '</dd></dl>';
    if (r.support && r.resistance && r.atr && (r.resistance.price - r.support.price) < r.atr) {
      html += '<p class="note"><span class="warn-icon" aria-hidden="true">▲</span> Suporte e resistência mais próximos que o tamanho médio de uma vela: preço espremido, zona de conflito (págs. 106 e 223).</p>';
    }
    el.innerHTML = html;
  }

  // ------------------------------------------------------------------ ENTRADAS
  function refreshEntradas() {
    var q = ['limit=2000', 'period=' + state.ePeriod];
    ['strategy', 'result', 'origin'].forEach(function (k) {
      var v = $('#e-' + k).value;
      if (v) q.push(k + '=' + encodeURIComponent(v));
    });
    api('/api/signals?' + q.join('&')).then(function (rows) {
      var w = 0, l = 0, e = 0, p = 0, profit = 0;
      rows.forEach(function (r) {
        if (r.result === 'win') w++; else if (r.result === 'loss') l++; else if (r.result === 'empate') e++; else if (r.result === 'pendente') p++;
        profit += r.profit || 0;
      });
      function pl(n, one, many) { return '<span><strong>' + intFmt.format(n) + '</strong> ' + (n === 1 ? one : many) + '</span>'; }
      $('#e-summary').innerHTML = rows.length
        ? pl(rows.length, 'sinal', 'sinais') + pl(w, 'win', 'wins') + pl(l, 'loss', 'losses') + pl(e, 'empate', 'empates') + pl(p, 'pendente', 'pendentes') +
          '<span>Acerto <strong>' + (w + l ? fmtPct(w / (w + l)) : '—') + '</strong></span><span>Resultado <strong class="' + signClass(profit) + '">' + fmtUnits(profit) + '</strong> entradas</span>'
        : '';
      var body = $('#e-body');
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="10" class="muted">Nenhuma entrada com esses filtros' +
          (state.ePeriod === 'hoje' ? ' hoje. Com o bot rodando, as entradas ao vivo aparecem aqui.' : '.') + '</td></tr>';
        return;
      }
      body.innerHTML = rows.map(function (r) {
        return '<tr><td class="num">' + fmtDateTime(r.candle_ts) + '</td><td>' + esc(r.asset) + '</td><td>' + stratHtml(r.strategy) +
          '</td><td>' + dirHtml(r.direction) + '</td><td>' + esc(r.setup) + '</td><td class="num">' + fmtPrice(r.entry_price) +
          '</td><td class="num">' + fmtPrice(r.exit_price) + '</td><td>' + resHtml(r.result) + '</td><td class="num ' + signClass(r.profit) + '">' +
          (r.result === 'pendente' || r.result === 'cancelado' ? '—' : fmtUnits(r.profit)) + '</td><td>' + originText(r.origin) + '</td></tr>';
      }).join('');
    }).catch(function (err) { $('#e-body').innerHTML = '<tr><td colspan="10">Erro: ' + esc(err.message) + '</td></tr>'; });
  }

  // ------------------------------------------------------------------ DESEMPENHO
  function refreshDesempenho() {
    var strategy = $('#d-strategy').value, asset = $('#d-asset').value, origin = $('#d-origin').value;
    var q = ['period=' + state.dPeriod, 'origin=' + encodeURIComponent(origin)];
    if (strategy) q.push('strategy=' + encodeURIComponent(strategy));
    if (asset) q.push('asset=' + encodeURIComponent(asset));
    api('/api/stats?' + q.join('&')).then(function (st) {
      $('#d-profit-label').textContent = 'Resultado ' + PERIOD_TEXT[state.dPeriod];
      renderKpis('d', st);
      $('#d-cols-title').textContent = GRAN_TITLE[st.granularity] || 'Resultado';
      renderCols(st.timeline);
      renderEquity(st.cumulative, strategy ? strategyColor(strategy) : cssVar('--text-secondary'));
      renderBars(st.by_strategy, st.breakeven);
      var be = st.breakeven;
      $('#d-setups').innerHTML = st.by_setup.length ? st.by_setup.map(function (g) {
        var parts = g.key.split('|');
        return groupRow('<td>' + stratHtml(parts[0]) + '</td><td>' + esc(parts[1]) + '</td>', g, be);
      }).join('') : '<tr><td colspan="6" class="muted">—</td></tr>';
      $('#d-hours').innerHTML = st.by_hour.length ? st.by_hour.map(function (g) {
        return groupRow('<td>' + esc(g.key) + 'h</td>', g, be);
      }).join('') : '<tr><td colspan="5" class="muted">—</td></tr>';
      $('#d-markets').innerHTML = st.by_market.length ? st.by_market.map(function (g) {
        return groupRow('<td>' + esc(g.key) + '</td>', g, be);
      }).join('') : '<tr><td colspan="5" class="muted">—</td></tr>';
      var sel = $('#d-asset'), current = sel.value;
      sel.innerHTML = '<option value="">Todos</option>' + st.assets.map(function (a) {
        return '<option value="' + esc(a) + '"' + (a === current ? ' selected' : '') + '>' + esc(a) + '</option>';
      }).join('');
    }).catch(function () {});
  }

  function groupRow(cells, g, be) {
    var good = g.n >= MIN_SAMPLE && g.ci_low != null && be != null && g.ci_low > be;
    return '<tr' + (good ? ' class="good-row" title="Intervalo de confiança inteiro acima do mínimo para empatar"' : '') + '>' + cells +
      '<td class="num">' + intFmt.format(g.n) + '</td><td class="num">' + fmtPct(g.winrate) + '</td><td class="num">' +
      (g.n ? fmtPct(g.ci_low) + '–' + fmtPct(g.ci_high) : '—') + '</td><td class="num ' + signClass(g.profit) + '">' + fmtUnits(g.profit) + '</td></tr>';
  }

  function renderCols(tl) {
    var el = $('#d-cols');
    var any = tl.some(function (b) { return b.n + b.draws > 0; });
    if (!tl.length || !any) { el.innerHTML = '<div class="empty-state">Nenhuma entrada no período.</div>'; return; }
    var maxPos = 0, maxNeg = 0, iMax = -1, iMin = -1;
    tl.forEach(function (b, i) {
      if (b.profit > maxPos) { maxPos = b.profit; iMax = i; }
      if (-b.profit > maxNeg) { maxNeg = -b.profit; iMin = i; }
    });
    var H = 220, span = (maxPos + maxNeg) || 1;
    var posH = Math.round(H * maxPos / span), negH = H - posH;
    var step = Math.max(1, Math.ceil(tl.length / 12));
    var html = '<div class="cols-plot">' + tl.map(function (b, i) {
      var ph = b.profit > 0 ? Math.max(2, b.profit / maxPos * (posH - 18)) : 0;
      var nh = b.profit < 0 ? Math.max(2, -b.profit / maxNeg * (negH - 18)) : 0;
      var val = function (h) { return '<span class="col-val" style="--h:' + h.toFixed(1) + 'px">' + fmtUnits(b.profit) + '</span>'; };
      return '<div class="col" tabindex="0" data-i="' + i + '">' +
        '<div class="col-pos" style="height:' + posH + 'px">' + (ph ? '<div class="col-bar pos" style="height:' + ph.toFixed(1) + 'px"></div>' : '') + (i === iMax ? val(ph) : '') + '</div>' +
        '<div class="col-neg" style="height:' + negH + 'px">' + (nh ? '<div class="col-bar neg" style="height:' + nh.toFixed(1) + 'px"></div>' : '') + (i === iMin ? val(nh) : '') + '</div>' +
        '</div>';
    }).join('') + '</div>';
    html += '<div class="cols-axis">' + tl.map(function (b, i) { return '<span>' + (i % step === 0 ? esc(b.label) : '') + '</span>'; }).join('') + '</div>';
    el.innerHTML = html;
    Array.prototype.forEach.call(el.querySelectorAll('.col'), function (c) {
      var b = tl[parseInt(c.dataset.i, 10)];
      tipData.set(c, '<div class="t-title">' + esc(b.label) + '</div>Resultado <strong>' + fmtUnits(b.profit) + '</strong> entradas<br>' +
        b.wins + ' wins · ' + b.losses + ' losses · ' + b.draws + ' empates<br>Acerto ' + fmtPct(b.winrate));
    });
  }

  function renderEquity(points, color) {
    var empty = !points.length;
    $('#d-equity-empty').hidden = !empty;
    $('#d-equity').style.visibility = empty ? 'hidden' : 'visible';
    if (!eqSeries) return;
    eqSeries.applyOptions({ lineColor: color, topColor: hexA(color, 0.16), bottomColor: hexA(color, 0.02) });
    eqSeries.setData(points);
    if (!empty) eqChart.timeScale().fitContent();
  }

  function renderBars(groups, be) {
    var el = $('#d-bars');
    if (!groups.length) { el.innerHTML = '<div class="empty-state">Nenhuma entrada no período.</div>'; return; }
    var html = groups.map(function (g, i) {
      var wr = (g.winrate || 0) * 100, lo = (g.ci_low || 0) * 100, hi = (g.ci_high || 0) * 100, b = (be || 0) * 100;
      return '<div class="bar-row" tabindex="0" data-i="' + i + '">' +
        '<div class="bar-label">' + stratHtml(g.key) + '</div>' +
        '<div class="bar-track">' +
          '<div class="bar-fill" style="width:' + wr.toFixed(2) + '%;background:' + strategyColor(g.key) + '"></div>' +
          '<div class="bar-ci" style="left:' + lo.toFixed(2) + '%;width:' + Math.max(0, hi - lo).toFixed(2) + '%"></div>' +
          '<div class="bar-be" style="left:calc(' + b.toFixed(2) + '% - 1px)" aria-hidden="true"></div>' +
        '</div>' +
        '<div class="bar-value">' + fmtPct(g.winrate) + ' <span class="muted">n=' + intFmt.format(g.n) + '</span>' +
          (g.n < MIN_SAMPLE ? '<span class="warn-chip">pouca amostra</span>' : '') + '</div>' +
      '</div>';
    }).join('');
    html += '<div class="bar-axis"><span></span><div class="bar-axis-track">' +
      [0, 25, 50, 75, 100].map(function (v) { return '<span style="left:' + v + '%">' + v + '%</span>'; }).join('') +
      '</div><span>traço = empate ' + fmtPct(be) + '</span></div>';
    el.innerHTML = html;
    Array.prototype.forEach.call(el.querySelectorAll('.bar-row'), function (row) {
      var g = groups[parseInt(row.dataset.i, 10)];
      tipData.set(row, '<div class="t-title">' + stratHtml(g.key) + '</div>' +
        'Acerto ' + fmtPct(g.winrate) + ' (IC 95% ' + fmtPct(g.ci_low) + '–' + fmtPct(g.ci_high) + ')<br>' +
        intFmt.format(g.wins) + ' wins · ' + intFmt.format(g.losses) + ' losses · ' + intFmt.format(g.draws) + ' empates<br>' +
        'Mínimo para empatar ' + fmtPct(g.breakeven) + '<br>Resultado ' + fmtUnits(g.profit) + ' entradas');
    });
  }

  // ------------------------------------------------------------------ CONFIGURAÇÃO
  function loadConfig(fillForm) {
    return api('/api/config').then(function (cfg) {
      configChanged(cfg);
      if (fillForm) fillConfigForm(cfg);
      return cfg;
    }).catch(function (e) { if (fillForm) setResult('#cfg-save-result', false, 'Erro ao carregar: ' + e.message); });
  }
  function configChanged(cfg) {
    state.config = cfg;
    renderToolbarAssets();
    renderPairTabs();
    renderManual();
    syncVisible();
    renderToggles();
    renderLineLegend();
    refreshChart();
    if (state.page === 'painel') refreshToday();
  }

  var STRATEGY_NOTES = {
    score_ldp: 'principal · entra com 3 de 4 padrões sobre a retração no comando · regra congelada em 06/11, em validação',
    retracao_comando: '~54% sozinha · é a base do score',
    ldp_apostila: '48% na pesquisa · não recomendado',
    retracao_lote: 'nova · em pesquisa · pág. 162',
    reversao_forca: 'nova · em pesquisa · vela de força trava na defesa e reverte',
    reversao_indecisao: 'nova · em pesquisa · força rompe dupla/tripla e volta'
  };
  var STATE_LABELS = { off: 'Desligada', observe: 'Observar', operate: 'Operar' };
  function renderStrategyChoices(cfg) {
    $('#cfg-strats').innerHTML = (cfg.strategy_names || []).map(function (name) {
      var current = (cfg.strategies && cfg.strategies[name]) || 'off';
      var note = STRATEGY_NOTES[name];
      return '<tr><th scope="row">' + dotHtml(name) + esc(label(name)) + (note ? '<div class="muted small">' + esc(note) + '</div>' : '') + '</th>' +
        Object.keys(STATE_LABELS).map(function (st) {
          return '<td><input type="radio" name="cfg-strat-' + esc(name) + '" value="' + st + '"' + (st === current ? ' checked' : '') +
            ' aria-label="' + esc(label(name)) + ': ' + STATE_LABELS[st] + '"></td>';
        }).join('') + '</tr>';
    }).join('');
  }
  function chosenStrategies() {
    var out = {};
    ((state.config && state.config.strategy_names) || []).forEach(function (name) {
      var r = document.querySelector('input[name="cfg-strat-' + name + '"]:checked');
      out[name] = r ? r.value : 'off';
    });
    return out;
  }
  function chosenScripts() {
    var out = {};
    Array.prototype.forEach.call(document.querySelectorAll('input[name="cfg-script"]'), function (c) { out[c.value] = c.checked; });
    return out;
  }

  function setResult(sel, ok, text) {
    var el = $(sel);
    el.className = 'small ' + (ok === true ? 'result-ok' : ok === false ? 'result-bad' : 'muted');
    el.textContent = text;
  }

  function fillConfigForm(cfg) {
    $('#cfg-email').value = cfg.iq_email || '';
    var pw = $('#cfg-password');
    pw.value = '';
    pw.placeholder = cfg.has_password ? '•••••••• (salva)' : 'senha da IQ Option';
    $('#cfg-cred-note').textContent = cfg.credentials_source === 'tela' ? 'Usando o login salvo nesta tela.'
      : cfg.credentials_source === 'arquivo .env' ? 'Usando o login do arquivo backend/.env. Preencha aqui para trocar.'
      : 'Nenhum login salvo ainda.';
    Array.prototype.forEach.call(document.querySelectorAll('input[name="cfg-mode"]'), function (r) { r.checked = r.value === cfg.mode; });
    renderStrategyChoices(cfg);
    Array.prototype.forEach.call(document.querySelectorAll('input[name="cfg-script"]'), function (c) {
      c.checked = !!(cfg.chart_scripts && cfg.chart_scripts[c.value]);
    });
    state.cfgPairs = cfg.assets.slice();
    renderPairChips();
    $('#cfg-timeframe').value = String(cfg.timeframe);
    $('#cfg-stake').value = cfg.stake;
    $('#cfg-stop-win').value = cfg.stop_win == null ? '' : cfg.stop_win;
    $('#cfg-stop-loss').value = cfg.stop_loss == null ? '' : cfg.stop_loss;
    $('#cfg-max-trades').value = cfg.max_trades == null ? '' : cfg.max_trades;
    $('#cfg-max-losses').value = cfg.max_consecutive_losses == null ? '' : cfg.max_consecutive_losses;
    $('#cfg-min-payout').value = cfg.min_payout == null ? '' : Math.round(cfg.min_payout * 100);
    $('#cfg-hours-start').value = cfg.hours_start || '';
    $('#cfg-hours-end').value = cfg.hours_end || '';
    $('#cfg-martingale').checked = !!cfg.martingale;
    $('#cfg-gale-levels').value = String(cfg.gale_levels || 1);
    renderGaleExample();
    setResult('#cfg-test-result', null, '');
  }

  function galeStake(base, cycleLoss, payout) { return Math.ceil((cycleLoss + base * payout) / payout * 100) / 100; }
  function renderGaleExample() {
    var on = $('#cfg-martingale').checked;
    $('#cfg-gale-levels').disabled = !on;
    var el = $('#cfg-gale-example');
    var stake = numField('#cfg-stake') || 2, levels = parseInt($('#cfg-gale-levels').value, 10) || 1, payout = 0.84;
    var stakes = [stake], loss = stake;
    for (var i = 0; i < levels; i++) { var s = galeStake(stake, loss, payout); stakes.push(s); loss += s; }
    var gain = stake * payout, wipe = Math.floor(loss / gain);
    el.innerHTML = (on ? '' : 'Desligado. Se ligar: ') + 'com entrada de ' + fmtMoney(stake) + ' e payout de 84%, o ciclo é ' +
      stakes.map(function (v) { return fmtMoney(v); }).join(' → ') + '. Ganhar o ciclo rende cerca de <strong>' + fmtMoney(gain) +
      '</strong>; perder o ciclo inteiro custa <strong>' + fmtMoney(loss) + '</strong>, o que apaga umas ' + wipe +
      ' vitórias. O martingale não melhora o acerto da estratégia: só concentra a perda em menos vezes.';
  }

  function renderPairChips() {
    function group(title, fixed, otc) {
      var all = fixed.slice();
      state.cfgPairs.forEach(function (p) { if (isOtc(p) === otc && all.indexOf(p) < 0) all.push(p); });
      return '<div><span class="pair-group-title">' + title + '</span><div class="pair-chips">' + all.map(function (p) {
        return '<button type="button" class="toggle" data-pair="' + esc(p) + '" aria-pressed="' + (state.cfgPairs.indexOf(p) >= 0 ? 'true' : 'false') + '">' + esc(p) + '</button>';
      }).join('') + '</div></div>';
    }
    $('#cfg-assets').innerHTML = group('Mercado normal', DEFAULT_PAIRS, false) + group('OTC', OTC_PAIRS, true);
  }
  function togglePair(p) {
    var i = state.cfgPairs.indexOf(p);
    if (i >= 0) state.cfgPairs.splice(i, 1);
    else if (state.cfgPairs.length >= 8) { setResult('#cfg-save-result', false, 'No máximo 8 pares ao mesmo tempo.'); return; }
    else state.cfgPairs.push(p);
    renderPairChips();
  }
  function addPair() {
    var input = $('#cfg-asset-new');
    var p = normalizeAsset(input.value);
    if (!/^[A-Za-z0-9-]{3,20}$/.test(p)) { setResult('#cfg-save-result', false, 'Par inválido: use letras, números e hífen (ex.: EURUSD-op).'); return; }
    if (state.cfgPairs.indexOf(p) < 0) togglePair(p);
    input.value = '';
  }

  function numField(id) { var v = $(id).value.trim(); return v === '' ? null : Number(v); }
  function configPatch() {
    var mode = document.querySelector('input[name="cfg-mode"]:checked');
    var patch = {
      mode: mode ? mode.value : 'sinais',
      strategies: chosenStrategies(),
      chart_scripts: chosenScripts(),
      assets: state.cfgPairs.slice(),
      timeframe: parseInt($('#cfg-timeframe').value, 10),
      stop_win: numField('#cfg-stop-win'),
      stop_loss: numField('#cfg-stop-loss'),
      max_trades: numField('#cfg-max-trades'),
      max_consecutive_losses: numField('#cfg-max-losses'),
      min_payout: numField('#cfg-min-payout') == null ? null : numField('#cfg-min-payout') / 100,
      hours_start: $('#cfg-hours-start').value || null,
      hours_end: $('#cfg-hours-end').value || null,
      martingale: $('#cfg-martingale').checked,
      gale_levels: parseInt($('#cfg-gale-levels').value, 10) || 1
    };
    var stake = numField('#cfg-stake');
    if (stake != null) patch.stake = stake;
    var email = $('#cfg-email').value.trim();
    if (email) patch.iq_email = email;
    var pw = $('#cfg-password').value;
    if (pw) patch.iq_password = pw;
    return patch;
  }
  function putConfig(patch) {
    return api('/api/config', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(patch) });
  }

  function saveConfig(e) {
    e.preventDefault();
    var btn = $('#cfg-save');
    btn.disabled = true;
    setResult('#cfg-save-result', null, 'Salvando…');
    var before = state.config;
    putConfig(configPatch()).then(function (cfg) {
      configChanged(cfg);
      fillConfigForm(cfg);
      var changedRun = before && (before.assets.join() !== cfg.assets.join() || before.timeframe !== cfg.timeframe);
      var isOn = function (st) { return st === 'observe' || st === 'operate'; };
      var changedOnOff = before && cfg.strategy_names.some(function (n) {
        return isOn(before.strategies[n]) !== isOn(cfg.strategies[n]);
      });
      var nextStart = [];
      if (changedRun) nextStart.push('os pares e a vela');
      if (changedOnOff) nextStart.push('ligar ou desligar estratégia');
      setResult('#cfg-save-result', true, 'Configuração salva.' + (cfg.applies_next_start && nextStart.length
        ? ' Valem no próximo início do bot (pare e inicie de novo): ' + nextStart.join(' e ') + '.' : ''));
    }).catch(function (err) {
      setResult('#cfg-save-result', false, err.message);
    }).then(function () { btn.disabled = false; });
  }

  function testConnection() {
    var btn = $('#cfg-test');
    btn.disabled = true;
    setResult('#cfg-test-result', null, 'Entrando na IQ Option…');
    var email = $('#cfg-email').value.trim(), pw = $('#cfg-password').value;
    var saved = (state.config && state.config.iq_email) || '';
    var creds = {};
    // E-mail novo vai junto mesmo sem senha: o servidor recusa e pede a senha, em vez de testar a conta antiga.
    if (email && (pw || email.toLowerCase() !== saved.toLowerCase())) creds.iq_email = email;
    if (pw) creds.iq_password = pw;
    var changed = creds.iq_email || creds.iq_password;
    var first = changed ? putConfig(creds).then(function (cfg) { state.config = cfg; fillConfigForm(cfg); }) : Promise.resolve();
    first.then(function () { return api('/api/config/test', { method: 'POST' }); }).then(function (r) {
      setResult('#cfg-test-result', true, 'Conectado · ' + (r.account === 'PRACTICE' ? 'conta demo' : 'conta ' + r.account) + ' · saldo ' + fmtMoney(r.balance));
    }).catch(function (err) {
      setResult('#cfg-test-result', false, err.message);
    }).then(function () { btn.disabled = false; });
  }

  function resetHistory() {
    var s = state.status;
    if (isBusy(s)) {
      setResult('#cfg-reset-result', false, 'Pare o bot antes de zerar o histórico.');
      return;
    }
    if (!window.confirm('Zerar o histórico do bot? Entradas, ordens, sessões e velas guardadas serão apagadas (fica uma cópia em data/backups). A configuração continua.')) return;
    var btn = $('#cfg-reset');
    btn.disabled = true;
    setResult('#cfg-reset-result', null, 'Zerando…');
    api('/api/data/reset', { method: 'POST' }).then(function (r) {
      var a = r.apagado;
      setResult('#cfg-reset-result', true, 'Histórico zerado: ' + intFmt.format(a.signals) + ' entradas, ' + intFmt.format(a.orders) +
        ' ordens e ' + intFmt.format(a.candles) + ' velas apagadas. Cópia: ' + r.copia.split('/').slice(-2).join('/'));
      state.chartData = null; state.chartKey = null; state.seenOpen = {}; state.doneAt = {};
    }).catch(function (err) {
      setResult('#cfg-reset-result', false, err.message);
    }).then(function () { btn.disabled = false; });
  }

  // ------------------------------------------------------------------ tooltip
  function setupTooltip() {
    var tip = $('#tooltip');
    function show(target, x, y) {
      var html = tipData.get(target);
      if (!html) { tip.hidden = true; return; }
      tip.innerHTML = html;
      tip.hidden = false;
      var r = tip.getBoundingClientRect();
      tip.style.left = Math.min(x + 14, window.innerWidth - r.width - 8) + 'px';
      tip.style.top = Math.min(y + 14, window.innerHeight - r.height - 8) + 'px';
    }
    document.addEventListener('mousemove', function (e) {
      var t = e.target.closest ? e.target.closest('.bar-row, .col') : null;
      if (t) show(t, e.clientX, e.clientY); else tip.hidden = true;
    });
    document.addEventListener('focusin', function (e) {
      var t = e.target;
      if (t.classList && (t.classList.contains('bar-row') || t.classList.contains('col'))) {
        var b = t.getBoundingClientRect();
        show(t, b.left + b.width / 2, b.bottom);
      }
    });
    document.addEventListener('focusout', function () { tip.hidden = true; });
  }

  // ------------------------------------------------------------------ navegação
  function setPage(name) {
    if (name !== 'painel') setChartExpanded(false);
    state.page = name;
    Array.prototype.forEach.call(document.querySelectorAll('.nav-item'), function (b) {
      if (b.dataset.page === name) b.setAttribute('aria-current', 'page'); else b.removeAttribute('aria-current');
    });
    PAGES.forEach(function (p) { $('#page-' + p).hidden = p !== name; });
    $('#page-title').textContent = PAGE_TITLES[name];
    if (location.hash !== '#' + name) history.replaceState(null, '', '#' + name);
    if (name === 'config') loadConfig(true);
    else refreshCurrent();
  }
  function refreshCurrent() {
    if (state.page === 'painel') refreshPainel();
    else if (state.page === 'entradas') refreshEntradas();
    else if (state.page === 'desempenho') refreshDesempenho();
  }
  var refreshSoon = debounce(refreshCurrent, 300);
  var refreshTodaySoon = debounce(refreshToday, 300);

  function bindSegmented(id, key, onChange) {
    var group = $(id);
    group.addEventListener('click', function (e) {
      var btn = e.target.closest('button');
      if (!btn) return;
      state[key] = btn.dataset.v;
      Array.prototype.forEach.call(group.querySelectorAll('button'), function (b) {
        b.setAttribute('aria-pressed', b === btn ? 'true' : 'false');
      });
      onChange();
    });
  }

  // ------------------------------------------------------------------ conexão ao vivo
  function setConnected(ok) {
    state.connected = ok;
    $('#conn-dot').className = 'conn-dot ' + (ok ? 'ok' : 'bad');
    $('#conn-dot-mini').className = 'conn-dot ' + (ok ? 'ok' : 'bad');
    $('#conn-text').textContent = ok ? 'Servidor conectado' : 'Sem conexão com o servidor';
    if (!ok && !state.shuttingDown) showBanner('Sem conexão com o servidor do BotBene. Tentando reconectar…');
    else if (ok && !(state.status && state.status.status === 'erro')) hideBanner();
  }
  function connectWs() {
    if (state.shuttingDown) return;
    var proto = location.protocol === 'https:' ? 'wss' : 'ws';
    var ws = new WebSocket(proto + '://' + location.host + '/ws/live');
    ws.onopen = function () {
      var reconnect = state.wsWasDown;
      state.wsWasDown = false;
      setConnected(true);
      if (reconnect) {  // servidor reiniciou: painel novo? e o par da tela volta a ficar ao vivo
        api('/api/status').then(function (s) { checkVersion(s); renderStatus(s); ensureWatching(); refreshPairs(); }).catch(function () {});
      }
    };
    ws.onmessage = function (ev) {
      var e = JSON.parse(ev.data);
      if (e.type === 'status') { renderStatus(e); refreshSoon(); }
      else if (e.type === 'tick') onTick(e.asset, e.candle);
      else if (e.type === 'closed') {
        if (e.status) renderStatus(e.status);
        if (!state.chartData || e.asset === state.chartData.asset) refreshSoon(); else if (state.page === 'painel') refreshTodaySoon();
      }
      else if (e.type === 'armed' || e.type === 'approval') { if (e.status) renderStatus(e.status); }
      else if (e.type === 'order') {
        if (e.order) state.ordersById[e.order.id] = e.order;
        renderRisk(e.risk);
        if (state.status) { renderApprovals(state.status); renderArmed(state.status); }  // cartão de resultado na hora
        if (state.page === 'painel') refreshOrders();
        if (e.order && state.chartData && e.order.asset === state.chartData.asset) refreshChart();  // marca de ENTRADA na hora
        renderManual();
        if (['win', 'loss', 'empate'].indexOf(e.order && e.order.status) >= 0) refreshAccount();  // saldo mudou
      }
      else if (e.type === 'signal' || e.type === 'result') { if (state.page === 'painel') refreshTodaySoon(); }
      else if (e.type === 'reload') refreshSoon();
    };
    ws.onclose = function () {
      if (state.shuttingDown) return;
      state.wsWasDown = true;
      setConnected(false);
      setTimeout(connectWs, 2000);
    };
  }

  // Barra lateral encolhida (só ícones) ou aberta; a escolha fica guardada neste computador.
  function setCollapsed(on) {
    root().classList.toggle('collapsed', on);
    var btn = $('#btn-collapse');
    var text = on ? 'Expandir o menu' : 'Encolher o menu';
    btn.title = text;
    btn.setAttribute('aria-label', text);
    btn.setAttribute('aria-expanded', on ? 'false' : 'true');
    try { localStorage.setItem('botbene-menu', on ? 'encolhido' : 'aberto'); } catch (e) { /* sem armazenamento */ }
  }

  // O painel recarrega sozinho quando o servidor tem arquivos novos (nunca no meio de um pedido de aprovação).
  function checkVersion(s) {
    if (!s || !s.ui_version) return;
    if (!state.uiVersion) { state.uiVersion = s.ui_version; return; }
    if (s.ui_version === state.uiVersion) return;
    var open = ((state.status && state.status.approvals) || []).some(isOpenApproval);
    if (!open) location.reload();
  }

  function shutdown() {
    if (!window.confirm('Desligar o BotBene? O bot para e o servidor é encerrado.')) return;
    state.shuttingDown = true;
    api('/api/shutdown', { method: 'POST' }).catch(function () {}).then(function () {
      $('#overlay').hidden = false;
      setTimeout(function () { window.close(); }, 1500);
    });
  }

  // ------------------------------------------------------------------ início
  function init() {
    var saved = null;
    try { saved = localStorage.getItem('botbene-theme'); } catch (e) { saved = null; }
    root().dataset.theme = saved === 'light' ? 'light' : 'dark';
    $('#btn-theme-text').textContent = root().dataset.theme === 'dark' ? 'Tema claro' : 'Tema escuro';
    var menu = null;
    try { menu = localStorage.getItem('botbene-menu'); } catch (e) { menu = null; }
    setCollapsed(menu === 'encolhido');

    initCharts();
    renderToggles();
    renderLineLegend();
    setupTooltip();

    Array.prototype.forEach.call(document.querySelectorAll('.nav-item'), function (b) {
      b.addEventListener('click', function () { setPage(b.dataset.page); });
    });
    $('#btn-toggle').addEventListener('click', toggleBot);
    $('#acct-switch').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-acct]');
      if (b) chooseAccount(b.dataset.acct);
    });
    $('#assets-text').addEventListener('click', function () { setPage('config'); });
    $('#pair-tabs').addEventListener('click', function (e) {
      var x = e.target.closest('[data-unpin]');
      if (x) { unpinPair(x.dataset.unpin); return; }
      if (e.target.closest('#pt-all')) { openPicker(); return; }
      var b = e.target.closest('[data-pair]');
      if (b) choosePair(b.dataset.pair);
    });
    $('#chart-title').addEventListener('click', openPicker);
    $('#pp-close').addEventListener('click', closePicker);
    $('#pair-picker').addEventListener('click', function (e) {
      if (e.target === e.currentTarget) { closePicker(); return; }
      var b = e.target.closest('[data-pair]');
      if (b) choosePair(b.dataset.pair);
    });
    $('#pp-search').addEventListener('input', renderPicker);
    $('#pp-search').addEventListener('keydown', function (e) {
      if (e.key !== 'Enter') return;
      var first = document.querySelector('#pp-list [data-pair]');
      if (first) choosePair(first.dataset.pair);
    });
    $('#pp-open').addEventListener('change', renderPicker);
    $('#pp-cats').addEventListener('click', function (e) {
      var b = e.target.closest('[data-cat]');
      if (!b) return;
      state.pickerCat = b.dataset.cat;
      renderPickerCats();
      renderPicker();
    });
    $('#m-exp').addEventListener('click', function (e) {
      var b = e.target.closest('[data-min]');
      if (!b) return;
      state.manualMinutes = Number(b.dataset.min);
      saveStored('botbene-manual-min', state.manualMinutes);
      renderManual();
    });
    $('#m-minus').addEventListener('click', function () { stepAmount(-1); });
    $('#m-plus').addEventListener('click', function () { stepAmount(1); });
    $('#m-amount').addEventListener('input', function () { state.manualError = null; renderManual(); });
    $('#m-amount').addEventListener('change', function () {
      var v = manualAmount();
      if (isFinite(v) && v > 0) {
        $('#m-amount').value = fmtAmount(v);
        state.manualAmount = v;
        saveStored('botbene-manual-valor', v);
      }
      renderManual();
    });
    $('#m-amount').addEventListener('keydown', function (e) {
      if (e.key === 'ArrowUp') { e.preventDefault(); stepAmount(1); } else if (e.key === 'ArrowDown') { e.preventDefault(); stepAmount(-1); }
    });
    $('#m-call').addEventListener('click', function () { sendManual('call'); });
    $('#m-put').addEventListener('click', function () { sendManual('put'); });
    $('#approvals').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-act]');
      if (btn) { decideApproval(btn.dataset.id, btn.dataset.act, btn); return; }
      var chip = e.target.closest('[data-sel]');
      if (chip) { state.approvalSel = chip.dataset.sel; state.abKey = null; renderApprovals(state.status); }
    });
    $('#cfg-form').addEventListener('submit', saveConfig);
    $('#cfg-test').addEventListener('click', testConnection);
    $('#cfg-reset').addEventListener('click', resetHistory);
    $('#cfg-assets').addEventListener('click', function (e) {
      var b = e.target.closest('[data-pair]');
      if (b) togglePair(b.dataset.pair);
    });
    $('#cfg-asset-add').addEventListener('click', addPair);
    $('#cfg-asset-new').addEventListener('keydown', function (e) { if (e.key === 'Enter') { e.preventDefault(); addPair(); } });
    ['#cfg-martingale', '#cfg-gale-levels', '#cfg-stake'].forEach(function (id) {
      $(id).addEventListener('input', renderGaleExample);
      $(id).addEventListener('change', renderGaleExample);
    });
    document.addEventListener('click', unlockAudio, { once: true });
    $('#btn-theme').addEventListener('click', function () { applyTheme(root().dataset.theme === 'dark' ? 'light' : 'dark'); });
    $('#btn-collapse').addEventListener('click', function () { setCollapsed(!root().classList.contains('collapsed')); });
    $('#btn-fullscreen').addEventListener('click', function () {
      if (document.fullscreenElement) { document.exitFullscreen().catch(function () {}); return; }
      document.documentElement.requestFullscreen().catch(function (err) { showBanner('Não deu para entrar em tela cheia: ' + err.message + ' (tente F11).'); });
    });
    document.addEventListener('fullscreenchange', function () {
      $('#btn-fullscreen-text').textContent = document.fullscreenElement ? 'Sair da tela cheia' : 'Tela cheia';
      if (!document.fullscreenElement) setChartExpanded(false);  // o Esc do navegador sai da tela cheia: o gráfico volta junto
    });
    $('#chart-expand').addEventListener('click', function () { setChartExpanded(!state.chartExpanded); });
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      if (!closePicker()) setChartExpanded(false);  // a lista de pares fecha primeiro
    });
    $('#btn-shutdown').addEventListener('click', shutdown);
    $('#script-toggles').addEventListener('click', function (e) {
      var btn = e.target.closest('.toggle');
      if (!btn) return;
      var n = btn.dataset.s;
      state.visible[n] = !state.visible[n];
      btn.setAttribute('aria-pressed', state.visible[n] ? 'true' : 'false');
      applyMarkers();
      renderRetro();
    });
    $('#show-backtest').addEventListener('change', function (e) {
      state.showBacktest = e.target.checked;
      applyMarkers();
      if (state.showBacktest) { refreshRetro().then(refreshChart); return; }  // precisa do início do dia para saber quantas velas pedir
      renderRetro();
      refreshChart();
    });
    $('#show-reading').checked = state.showReading;
    $('#show-reading').addEventListener('change', function (e) {
      state.showReading = e.target.checked;
      try { localStorage.setItem('botbene-leitura', state.showReading ? '1' : '0'); } catch (err) { /* sem armazenamento */ }
      if (state.chartData) renderChart(state.chartData);
      renderLineLegend();
      refreshReading();
      var bars = candleSeries ? candleSeries.data().length : 0;  // a leitura tem um rótulo por padrão: de longe eles se atropelam
      if (bars) mainChart.timeScale().setVisibleLogicalRange({ from: bars - (state.showReading ? READING_BARS : 90), to: bars + FOCUS_MARGIN_BARS });
    });
    bindSegmented('#e-period', 'ePeriod', refreshEntradas);
    bindSegmented('#d-period', 'dPeriod', refreshDesempenho);
    ['strategy', 'result', 'origin'].forEach(function (k) { $('#e-' + k).addEventListener('change', refreshEntradas); });
    ['strategy', 'asset', 'origin'].forEach(function (k) { $('#d-' + k).addEventListener('change', refreshDesempenho); });

    api('/api/strategies').then(function (list) {
      list.forEach(function (s) { LABELS[s.name] = s.label; });
      var opts = '<option value="">Todas</option>' + list.map(function (s) {
        return '<option value="' + esc(s.name) + '">' + esc(s.label) + '</option>';
      }).join('');
      $('#e-strategy').innerHTML = opts;
      $('#d-strategy').innerHTML = opts;
      renderToggles();
    }).catch(function () {});

    var fromHash = location.hash.replace('#', '');
    var configLoaded = loadConfig(fromHash === 'config');
    refreshAccount();
    refreshOrders();  // o cartão de resultado precisa saber das ordens mesmo fora do Painel
    refreshPairs();
    setInterval(refreshAccount, 60000);
    setInterval(refreshPairs, 60000);  // payout e pares abertos
    api('/api/status').then(function (s) {
      checkVersion(s);
      renderStatus(s);
      configLoaded.then(ensureWatching);  // sem o bot, o par da tela fica ao vivo do mesmo jeito
      if (PAGE_TITLES[fromHash]) setPage(fromHash); else refreshCurrent();
      // Endereço terminado em #exemplo abre um pedido de exemplo (só na tela, não envia nada): usado para conferir o visual.
      if (fromHash === 'exemplo') setTimeout(showDemoApproval, 2500);
    }).catch(function () { setConnected(false); });
    connectWs();
    setInterval(function () {
      updateStatusSub();
      api('/api/status').then(function (s) { checkVersion(s); renderStatus(s); }).catch(function () {});
    }, 30000);
    setInterval(function () { updateCountdowns(); updateApprovalClocks(); updateManualClock(); }, 1000);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
