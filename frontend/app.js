/* BotBene · painel (JavaScript simples, sem build). Fala com o backend em /api e /ws/live. */
(function () {
  'use strict';

  // Ordem fixa: a cor segue o script, nunca a posição na lista.
  var STRATEGY_ORDER = ['ldp_v13', 'ldp_v13_linhas', 'wiki_pro_v21', 'ldp_apostila', 'retracao_comando',
    'retracao_lote', 'reversao_forca', 'reversao_indecisao', 'score_ldp', 'retracao_comando_v2', 'esticao', 'deeplob_iq', 'bb_rci', 'bb_rci_v2'];
  var SCORE = 'score_ldp';  // o combo: várias estratégias e padrões juntos decidem a entrada
  var RETRACAO_V2 = 'retracao_comando_v2';
  var ESTICAO = 'esticao';  // da pesquisa (08/11): arma os dois lados e entra contra o disparo dos 10 s iniciais
  var DEEPLOB = 'deeplob_iq';  // rede DeepLOB nas velas de 5 s (08/11): só arma quando a probabilidade passa do limiar
  var BB_RCI = 'bb_rci';  // Bollinger + RCI (09/11): banda tocada com o RCI no extremo, entra contra na vela seguinte
  var BB_RCI_V2 = 'bb_rci_v2';  // v1 + Gator, MACD e Weis Wave (09/11): só observar até passar na régua combinada
  var OBSERVE_ONLY = [ESTICAO, DEEPLOB, BB_RCI_V2];  // ainda em validação: a configuração não deixa operar
  // As duas versões da retração no comando: gatilho medido a partir da abertura da vela.
  function isRetracao(name) { return name === 'retracao_comando' || name === RETRACAO_V2; }
  var LABELS = {
    ldp_v13: 'LDP v1.3', ldp_v13_linhas: 'LDP v1.3 + regra das linhas', wiki_pro_v21: 'WIKI PRO V2.1',
    ldp_apostila: 'Apostila · marcações', retracao_comando: 'Apostila · retração no comando',
    retracao_lote: 'Estudo · retração no lote', reversao_forca: 'Estudo · reversão A (força trava)',
    reversao_indecisao: 'Estudo · reversão B (força rompe indecisão)', score_ldp: 'Score LDP v1 (combo)',
    retracao_comando_v2: 'Apostila · retração no comando v2',
    esticao: 'Pesquisa · esticão rápido',
    deeplob_iq: 'Pesquisa · DeepLOB (IA)',
    bb_rci: 'Pesquisa · Bollinger + RCI',
    bb_rci_v2: 'Pesquisa · Bollinger + RCI v2',
    manual: 'Entrada manual'
  };
  var MANUAL = 'manual';  // ordem que você fez na mão: não é estratégia e não entra nas estatísticas delas
  var TRIGGER_LABELS = { retracao: 'Retração', reversao: 'Reversão', throwback: 'Throwback', comando: 'Retração no comando', score: 'Score', esticao: 'Esticão', deeplob: 'DeepLOB', bb_rci: 'Bollinger + RCI', bb_rci_v2: 'Bollinger + RCI v2' };
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
  var DEFAULT_PAIRS = ['EURUSD-op', 'GBPUSD-op', 'USDJPY-op', 'AUDUSD-op', 'EURJPY-op', 'EURGBP-op', 'AUDJPY-op', 'NZDUSD-op',
    'USDCHF-op', 'USDCAD-op', 'GBPJPY-op', 'EURAUD-op', 'EURCHF-op', 'AUDCAD-op', 'GBPAUD-op', 'EURNZD-op'];
  var OTC_PAIRS = ['EURUSD-OTC', 'GBPUSD-OTC', 'USDJPY-OTC', 'AUDUSD-OTC', 'EURJPY-OTC', 'EURGBP-OTC', 'AUDCAD-OTC', 'NZDUSD-OTC',
    'USDCHF-OTC', 'USDCAD-OTC', 'GBPJPY-OTC', 'EURAUD-OTC', 'EURCHF-OTC', 'AUDJPY-OTC', 'GBPAUD-OTC', 'EURNZD-OTC'];
  var CHART_BARS = 240, CHART_BARS_MAX = 1500;  // com o retroativo à vista, o gráfico vai até a meia-noite
  var WAIT_GALE = 'esperando resultado';  // entrada do gale esperando o resultado da ordem anterior (dentro da janela)
  var OPEN_APPROVAL = ['aguardando', 'aprovado', 'disparou', WAIT_GALE];
  var APPROVAL_STATE = {
    aguardando: { cls: 'warn', icon: '●', text: 'Aguardando sua decisão' },
    aprovado: { cls: 'ok', icon: '✓', text: 'Aprovado: a ordem sai quando o gatilho disparar' },
    disparou: { cls: 'warn', icon: '▲', text: 'O gatilho disparou! Aprovar agora entra no preço do momento' },
    'esperando resultado': { cls: 'warn', icon: '…', text: 'Entrada do gale: esperando o resultado da ordem anterior para sair com o valor certo. Sai assim que ele chegar, se a janela ainda estiver aberta' },
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
  var weekdayTimeFmt = new Intl.DateTimeFormat('pt-BR', { timeZone: tz, weekday: 'short', hour: '2-digit', minute: '2-digit' });
  var pctFmt = new Intl.NumberFormat('pt-BR', { style: 'percent', minimumFractionDigits: 1, maximumFractionDigits: 1 });
  var unitsFmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  var intFmt = new Intl.NumberFormat('pt-BR');
  var moneyFmts = {};

  // ------------------------------------------------------------------ utilitários
  function $(sel) { return document.querySelector(sel); }
  function root() { return document.querySelector('.viz-root'); }
  function cssVar(name) { return getComputedStyle(root()).getPropertyValue(name).trim(); }
  function strategyColor(name) {
    // O score usa a cor da "LDP v1.3 + regra das linhas", que só existe na ferramenta de pesquisa; a v2 da retração tem a 9ª
    // o esticão, a 10ª, o DeepLOB, a 11ª, a Bollinger + RCI, a 12ª, e a v2 dela, a 13ª.
    var i = name === SCORE ? 1 : name === RETRACAO_V2 ? 8 : name === ESTICAO ? 9 : name === DEEPLOB ? 10 : name === BB_RCI ? 11
      : name === BB_RCI_V2 ? 12 : STRATEGY_ORDER.indexOf(name);
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
  // A ordem fechou diferente do que as velas do bot diziam (entrou noutro preço): vale o resultado da corretora.
  function brokerNote(r) {
    var c = r.details && r.details.corretora;
    if (!c || !c.velas || c.velas === r.result) return '';
    var v = RESULT_INFO[c.velas];
    return ' <span class="muted small" title="Pelas velas do bot seria ' + esc(v ? v.text : c.velas) +
      '. Vale o resultado da ordem: a corretora abriu num preço diferente do toque.">pela corretora</span>';
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
    uiVersion: null, ordersById: {}, resolvedAt: {}, apInit: false, entrySeen: {}, entryFocus: null, soundKind: {}, entryLines: [], entriesByTime: {}, scriptMarksByTime: {},
    showReading: false, readingData: null, readingByTime: {}, retroData: null, retroSeq: 0, chartExpanded: false, chartOwnsFullscreen: false,
    pairs: null, pairList: [], pairsError: null, pickerCat: 'Todos', pickerMarket: 'todos', pickerType: 'todos',
    manualSending: false, manualError: null, manualLastId: null
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
    candleSeries.attachPrimitive(drawPrimitive);
    mainChart.subscribeCrosshairMove(onCrosshair);
    mainChart.subscribeClick(onChartClick);
    // Dois cliques rápidos no gráfico viram "clique duplo" para a biblioteca: o segundo também conta como clique de desenho.
    if (mainChart.subscribeDblClick) mainChart.subscribeDblClick(onChartClick);
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
    renderDrawings();
    buySeries.applyOptions({ color: cssVar('--line-buy') });
    sellSeries.applyOptions({ color: cssVar('--line-sell') });
    eqChart.applyOptions(themeOptions());
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
    if (s.payout) $('#p-be-sub').textContent = beSubText(s);
    renderPairTabs();
    renderManual();
    renderArmed(s);
    renderApprovals(s);
    renderRisk(s.risk);
    renderGaleChip(s);
    var start = sessionStart();
    if (start !== state.painelStart) {  // o bot iniciou ou parou: a sessão do Painel mudou
      state.painelStart = start;
      if (state.page === 'painel') {
        if (state.sessionOnly) { refreshToday(); refreshOrders(); } else renderScope();
      }
    }
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
  var PAIR_MARKETS = [['todos', 'Normal e OTC'], ['normal', 'Mercado normal'], ['otc', 'OTC']];
  var PAIR_TYPES = [['todos', 'Todos os tipos'], ['binaria', 'Binária'], ['digital', 'Digital']];
  function loadStored(key, fallback) {
    try { var v = localStorage.getItem(key); return v == null ? fallback : JSON.parse(v); } catch (e) { return fallback; }
  }
  function saveStored(key, value) {
    try { localStorage.setItem(key, JSON.stringify(value)); } catch (e) { /* sem armazenamento */ }
  }
  state.recentPairs = loadStored('botbene-recent-pairs', []);
  state.sessionOnly = loadStored('botbene-painel-sessao', false);  // Painel: só a sessão, em vez do dia
  state.byCycle = loadStored('botbene-painel-ciclo', false);  // Painel: acerto por ciclo de gale, em vez de por ordem
  state.manualMinutes = loadStored('botbene-manual-min', 1);
  state.manualAmount = loadStored('botbene-manual-valor', null);
  state.manualKind = loadStored('botbene-manual-tipo', null);
  state.marketClockOpen = loadStored('botbene-mercado-detalhes', false);

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
  // Tipos de opção: a binária e a digital do mesmo par usam o mesmo preço; muda só o produto comprado.
  var KIND_TEXT = { binary: 'binária', digital: 'digital' };
  var OPTION_TYPE_TEXT = { binary: 'binária', digital: 'digital', best: 'binária ou digital (maior payout)' };
  function optionType() {
    var s = state.status;
    return (s && s.option_type) || (state.config && state.config.option_type) || 'binary';
  }
  function pairOpenAny(p) { return !!(p && (p.open || p.digital_open)); }  // dá para comprar algum tipo agora?
  function pairBestPayout(p) {  // o maior payout entre os tipos abertos agora
    if (!p) return null;
    var list = [];
    if (p.open && p.payout != null) list.push(p.payout);
    if (p.digital_open && p.digital_payout != null) list.push(p.digital_payout);
    return list.length ? Math.max.apply(null, list) : null;
  }
  function pairNextOpen(p) {
    var opens = [p.next_open, p.digital_next_open].filter(function (x) { return x != null; });
    return opens.length ? Math.min.apply(null, opens) : null;
  }
  function kindTag(kind) { return kind === 'digital' ? ' <span class="kind-tag">DIGITAL</span>' : ''; }

  function refreshPairs() {
    return api('/api/pairs').then(function (d) {
      state.pairs = {};
      (d.pairs || []).forEach(function (p) { state.pairs[p.asset] = p; });
      state.pairList = d.pairs || [];
      state.pairsError = d.error;
      fillPairSuggestions();
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
    if (p && !pairOpenAny(p)) text += ' · fechado agora';
    else if (p && !p.open && p.digital_open) text += ' · só digital aberta agora';
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
    var armed = {}, runs = {};
    ((state.status && state.status.assets) || []).forEach(function (a) {
      if (a.armed) armed[a.asset] = true;
      if (isBusy(state.status) && a.kind) runs[a.asset] = a;  // servidor novo: payout e tipo da próxima ordem do bot
    });
    function tab(asset, removable) {
      var p = pairInfo(asset), run = runs[asset], on = asset === current;
      // Par do bot: o payout do tipo em que vai a próxima ordem. Outros: o maior entre os tipos abertos.
      var openNow = run ? run.tradable !== false : pairOpenAny(p);
      var payout = run ? run.payout : pairBestPayout(p);
      var known = !!(p || run);
      var pay = known ? (openNow ? (payout != null ? payoutPct(payout) : '') : 'fechado') : (state.pairList.length ? 'fora da lista' : '');
      var next = p && !openNow ? pairNextOpen(p) : null;
      var title = (p ? p.label : asset) + (known && !openNow ? ' · fechado agora' + (next ? ', abre ' + whenText(next) : '') : '') +
        (run && openNow ? ' · próxima ordem na ' + KIND_TEXT[run.kind] : '');
      return '<span class="pair-tab' + (on ? ' on' : '') + ((known ? !openNow : state.pairList.length) ? ' closed' : '') + '">' +
        '<button type="button" data-pair="' + esc(asset) + '" aria-pressed="' + on + '" title="' + esc(title) + '">' +
        (armed[asset] ? '<span class="armed-dot" title="entrada armada"></span>' : '') + esc(asset) +
        (pay ? '<span class="pt-pay">' + pay + '</span>' : '') +
        (run && openNow && run.kind === 'digital' ? '<span class="pt-kind">D</span>' : '') + '</button>' +
        (removable && !on ? '<button type="button" class="pt-x" data-unpin="' + esc(asset) + '" aria-label="Tirar ' + esc(asset) + ' das abas">×</button>' : '') +
        '</span>';
    }
    var html = (bot.length ? '<span class="pt-cap">Bot (' + bot.length + ')</span>' + bot.map(function (a) { return tab(a, false); }).join('') : '') +
      (recent.length ? '<span class="pt-cap">Olhando</span>' + recent.map(function (a) { return tab(a, true); }).join('') : '');
    // Uma linha só, que rola para o lado (com muitos pares, as abas não empurram o gráfico para baixo).
    var scroller = $('#pt-scroll');
    if (!scroller) {
      el.innerHTML = '<button type="button" class="pt-arrow" data-scroll="-1" aria-label="Ver os pares à esquerda" hidden>‹</button>' +
        '<div class="pt-scroll" id="pt-scroll"></div>' +
        '<button type="button" class="pt-arrow" data-scroll="1" aria-label="Ver os pares à direita" hidden>›</button>' +
        '<button type="button" class="pt-all" id="pt-all">+ Todos os pares</button>';
      scroller = $('#pt-scroll');
      scroller.addEventListener('scroll', updatePairArrows);
      scroller.addEventListener('wheel', function (e) {  // roda do mouse rola as abas para o lado
        if (scroller.scrollWidth <= scroller.clientWidth + 1 || Math.abs(e.deltaX) >= Math.abs(e.deltaY)) return;
        scroller.scrollLeft += e.deltaY;
        e.preventDefault();
      }, { passive: false });
    }
    if (scroller.dataset.html !== html) { scroller.innerHTML = html; scroller.dataset.html = html; }
    if (state.ptShown !== current) { state.ptShown = current; showActiveTab(scroller); }  // trocou de par: a aba dele fica à vista
    updatePairArrows();
    renderMarketClock();
  }
  function showActiveTab(scroller) {
    var t = scroller.querySelector('.pair-tab.on');
    if (!t) return;
    if (t.offsetLeft < scroller.scrollLeft) scroller.scrollLeft = t.offsetLeft - 8;
    else if (t.offsetLeft + t.offsetWidth > scroller.scrollLeft + scroller.clientWidth) scroller.scrollLeft = t.offsetLeft + t.offsetWidth - scroller.clientWidth + 8;
  }
  function updatePairArrows() {
    var scroller = $('#pt-scroll');
    if (!scroller) return;
    var over = scroller.scrollWidth > scroller.clientWidth + 1;
    Array.prototype.forEach.call(document.querySelectorAll('#pair-tabs .pt-arrow'), function (b) {
      b.hidden = !over;
      b.disabled = b.dataset.scroll === '-1' ? scroller.scrollLeft <= 0 : scroller.scrollLeft + scroller.clientWidth >= scroller.scrollWidth - 1;
    });
  }

  // ------------------------------------------------------------------ mercado normal: quando abre e quando o bot troca
  // Para cada par do bot no OTC: quando o -op abre (pelo tipo de opção escolhido) e se o OTC fecha antes disso (o par
  // fica parado no intervalo). Para os que já estão no -op: quando o normal fecha e o bot volta para o OTC.
  function sideView(p, kind) {
    return kind === 'digital'
      ? { open: p.digital_open === true, payout: p.digital_payout, next_open: p.digital_next_open, next_close: p.digital_next_close }
      : { open: !!p.open, payout: p.payout, next_open: p.next_open, next_close: p.next_close };
  }
  function marketView(p, type) {  // a mesma regra de service/product.py (market_view), que a troca automática usa
    if (type === 'binary' || type === 'digital') return sideView(p, type);
    var sides = [sideView(p, 'binary'), sideView(p, 'digital')];
    var opened = sides.filter(function (x) { return x.open; });
    if (opened.length) {
      var closes = opened.map(function (x) { return x.next_close; });
      var pays = opened.map(function (x) { return x.payout; }).filter(function (x) { return x != null; });
      return { open: true, payout: pays.length ? Math.max.apply(null, pays) : null, next_open: null,
               next_close: closes.some(function (c) { return c == null; }) ? null : Math.max.apply(null, closes) };
    }
    var opens = sides.map(function (x) { return x.next_open; }).filter(function (x) { return x != null; });
    return { open: false, payout: null, next_open: opens.length ? Math.min.apply(null, opens) : null, next_close: null };
  }
  function durText(sec) {
    var m = Math.max(1, Math.round(sec / 60)), h = Math.floor(m / 60), d = Math.floor(h / 24);
    if (d >= 1) return d + ' d' + (h % 24 ? ' ' + (h % 24) + ' h' : '');
    return h ? h + ' h' + (m % 60 ? ' ' + (m % 60) + ' min' : '') : m + ' min';
  }
  function byTime(groups) {  // {horário: [pares]} -> [[horário, [pares]], ...] do mais cedo para o mais tarde
    return Object.keys(groups).map(Number).sort(function (a, b) { return a - b; }).map(function (t) { return [t, groups[t]]; });
  }
  function renderMarketClock() {
    var el = $('#market-clock');
    if (!el) return;
    var s = state.status, cfg = state.config, type = optionType(), now = serverNow();
    var auto = s && s.auto_market != null ? s.auto_market : !!(cfg && cfg.auto_market);
    var opens = {}, closes = {}, gaps = [];
    botAssets().forEach(function (asset) {
      var base = asset.replace(/-(OTC|op)$/i, '');
      if (isOtc(asset)) {
        var twin = pairInfo(base + '-op');
        if (!twin) return;  // par sem mercado normal na IQ
        var v = marketView(twin, type);
        if (v.open || v.next_open == null || v.next_open <= now) return;  // já abriu: a troca aparece nos avisos do bot
        (opens[v.next_open] = opens[v.next_open] || []).push(base);
        var otc = pairInfo(asset), ov = otc ? marketView(otc, type) : null;
        if (ov && ov.open && ov.next_close != null && ov.next_close < v.next_open) gaps.push({ asset: asset, from: ov.next_close, to: v.next_open });
      } else if (/-op$/.test(asset)) {
        var p = pairInfo(asset), pv = p ? marketView(p, type) : null;
        if (pv && pv.open && pv.next_close != null && pv.next_close > now) (closes[pv.next_close] = closes[pv.next_close] || []).push(base);
      }
    });
    var html = '', o = byTime(opens), c = byTime(closes);
    if (!state.marketClockOpen && (o.length || c.length)) {  // resumida: uma linha só
      var first = o.length ? o[0] : c[0], names = first[1];
      html = '<div class="mc-line one"><span class="mc-icon" aria-hidden="true">◷</span><span><strong>Mercado normal ' + (o.length ? 'abre ' : 'fecha ') +
        esc(whenText(first[0])) + '</strong> <span class="mc-left">em ' + durText(first[0] - now) + '</span>: ' +
        esc(names.slice(0, 3).join(', ')) + (names.length > 3 ? ' +' + (names.length - 3) : '') +
        (gaps.length ? ' · <span class="mc-warn">▲ ' + gaps.length + ' com pausa' + '</span>' : '') +
        '</span><button type="button" class="mc-toggle" data-mc="1">detalhes ▾</button></div>';
      el.hidden = false;
      if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
      return;
    }
    if (o.length) {
      html += '<div class="mc-line"><span class="mc-icon" aria-hidden="true">◷</span><span><strong>Mercado normal abre ' + esc(whenText(o[0][0])) +
        '</strong> <span class="mc-left">em ' + durText(o[0][0] - now) + '</span>: ' + esc(o[0][1].join(', ')) +
        o.slice(1).map(function (g) { return ' · ' + esc(whenText(g[0])) + ': ' + esc(g[1].join(', ')); }).join('') + '</span></div>';
      html += '<div class="mc-sub">' + (auto ? 'Quando abrir, o bot passa cada par do OTC para o -op sozinho (sem entrada armada no par e com o payout acima do mínimo).'
        : 'Troca automática desligada (Configuração): o bot fica no OTC.') + ' Horários de Brasília, pela grade da IQ' +
        (type === 'binary' ? ' para a binária' : type === 'digital' ? ' para a digital' : ' (o primeiro entre binária e digital)') + '.</div>';
    }
    gaps.sort(function (a, b) { return a.from - b.from; }).forEach(function (g) {
      html += '<div class="mc-sub warn">' + esc(g.asset) + ' fecha ' + esc(whenText(g.from)) + ' e o -op só abre ' + esc(whenText(g.to)) +
        ': o par fica ' + durText(g.to - g.from) + ' sem operar.</div>';
    });
    if (c.length) {
      html += '<div class="mc-line"><span class="mc-icon" aria-hidden="true">◷</span><span><strong>Mercado normal fecha ' + esc(whenText(c[0][0])) +
        '</strong> <span class="mc-left">em ' + durText(c[0][0] - now) + '</span>: ' + esc(c[0][1].join(', ')) +
        c.slice(1).map(function (g) { return ' · ' + esc(whenText(g[0])) + ': ' + esc(g[1].join(', ')); }).join('') +
        (auto ? '. Aí o bot volta para o OTC.' : '') + '</span></div>';
    }
    if (html) html += '<button type="button" class="mc-toggle mc-close" data-mc="0">ocultar detalhes ▴</button>';
    el.hidden = !html;
    if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
  }

  function choosePair(asset) {
    asset = normalizeAsset(asset);
    closePicker();
    if (!asset) return;
    state.lastChartTouch = Date.now();  // escolheu o par na mão: está analisando
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
    function seg(list, attr, current) {
      return list.map(function (o) {
        return '<button type="button" ' + attr + '="' + o[0] + '" aria-pressed="' + (o[0] === current) + '">' + esc(o[1]) + '</button>';
      }).join('');
    }
    $('#pp-market').innerHTML = seg(PAIR_MARKETS, 'data-market', state.pickerMarket);
    $('#pp-type').innerHTML = seg(PAIR_TYPES, 'data-type', state.pickerType);
  }
  // Horário de abertura: só a hora se for nas próximas 20 h; senão, com o dia da semana.
  function whenText(ts) {
    return ts - serverNow() < 20 * 3600 ? 'às ' + fmtTime(ts) : weekdayTimeFmt.format(new Date(ts * 1000)).replace(',', ' às');
  }
  function pairMarket(p) { return p.market || (isOtc(p.asset) ? 'otc' : 'normal'); }
  // Fechado para o tipo escolhido? (sem a informação, não esconde)
  function pairClosedFor(p, type) {
    if (type === 'digital') return p.digital_open === false;
    if (type === 'binaria') return p.open === false;
    return p.open === false && p.digital_open !== true;
  }
  // Etiquetas do tipo, com o payout de cada um. Verde = aberta agora.
  function pairTypeTags(p) {
    if (p.binary == null && p.digital == null) return '';  // sem a lista da IQ
    function tag(text, open, payout) {
      var pay = open && payout != null ? ' ' + payoutPct(payout) : '';
      return '<span class="pp-type' + (open ? ' on' : '') + '" title="' + text + (open ? ' aberta agora' : ' fechada agora') + '">' + text + pay + '</span>';
    }
    return (p.binary !== false ? tag('binária', p.open, p.payout) : '') + (p.digital ? tag('digital', p.digital_open, p.digital_payout) : '');
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
    var market = state.pickerMarket, type = state.pickerType;
    var bot = botAssets(), current = focusAsset();
    var items = all.filter(function (p) {
      if (state.pickerCat !== 'Todos' && p.category !== state.pickerCat) return false;
      if (market !== 'todos' && pairMarket(p) !== market) return false;
      if (type === 'binaria' && p.binary === false) return false;
      if (type === 'digital' && !p.digital) return false;
      if (onlyOpen && pairClosedFor(p, type)) return false;
      return !q || squash(p.asset + ' ' + p.label).indexOf(q) >= 0;
    }).sort(function (a, b) {
      var ab = bot.indexOf(a.asset) >= 0, bb = bot.indexOf(b.asset) >= 0;
      if (ab !== bb) return ab ? -1 : 1;
      if (pairOpenAny(a) !== pairOpenAny(b)) return pairOpenAny(a) ? -1 : 1;
      return (pairBestPayout(b) || 0) - (pairBestPayout(a) || 0) || a.asset.localeCompare(b.asset);
    });
    var open = all.filter(function (p) { return p.open; }).length;
    var digitalOpen = all.filter(function (p) { return p.digital_open; }).length;
    var known = all.some(function (p) { return p.digital != null; });
    $('#pp-note').textContent = state.pairsError
      ? 'Sem conexão com a IQ agora: mostrando os pares de sempre, sem payout.'
      : (state.pairList.length ? intFmt.format(open) + ' pares abertos para binária agora' +
          (known ? ' e ' + intFmt.format(digitalOpen) + ' para digital' : '') + ', de ' + intFmt.format(all.length) + '.' : 'Carregando a lista da IQ…');
    $('#pp-list').innerHTML = items.length ? items.map(function (p) {
      var best = pairBestPayout(p), next = pairNextOpen(p);
      var right = p.open === false && !p.digital_open ? '<span class="pp-closed">' + (next ? 'abre ' + esc(whenText(next)) : 'fechado') + '</span>'
        : (best != null ? '<span class="pp-pay">' + payoutPct(best) + '</span>' : '');
      var attrs = ' data-pair="' + esc(p.asset) + '"' + (p.asset === current ? ' aria-current="true"' : '');
      return '<li><button type="button"' + attrs + '>' +
        '<span class="pp-name">' + esc(p.asset) + (bot.indexOf(p.asset) >= 0 ? ' <span class="pp-tag">bot</span>' : '') + '</span>' +
        '<span class="pp-types">' + pairTypeTags(p) + '</span>' +
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
  // Digital: o próximo horário múltiplo do prazo (1 min: virada do minuto; 5 min: :00, :05…) a mais de 30 s.
  function digitalExpiryFor(now, minutes) {
    var step = 60 * minutes, end = (Math.floor(now / step) + 1) * step;
    if (end - now <= 30) end += step;
    return end;
  }
  function manualKinds(p) {  // tipos que o par tem (servidor antigo: só binária)
    var out = [];
    if (!p || p.binary !== false) out.push('binary');
    if (p && p.digital) out.push('digital');
    return out;
  }
  function manualKind(p) {
    var kinds = manualKinds(p);
    var want = state.manualKind || (optionType() === 'digital' ? 'digital' : 'binary');
    if (kinds.indexOf(want) >= 0) return want;
    return kinds[0] || 'binary';
  }
  function kindSide(p, kind) {  // o que vale para a entrada no tipo escolhido
    if (!p) return null;
    if (kind === 'digital') return { open: !!p.digital_open, payout: p.digital_payout, reason: p.digital_reason, expiries: p.digital_expiries || [] };
    return { open: !!p.open, payout: p.payout, reason: p.reason, expiries: p.expiries || [] };
  }
  function renderKindToggle(p, kind) {
    var el = $('#m-kind'), kinds = manualKinds(p);
    var show = !!p && p.digital != null && (kinds.length > 1 || kinds[0] === 'digital');
    el.hidden = !show;
    if (!show) return;
    var html = ['binary', 'digital'].map(function (k) {
      var has = kinds.indexOf(k) >= 0, side = kindSide(p, k);
      var pay = !has ? '' : side.open ? (side.payout != null ? '<span class="mk-pay">' + payoutPct(side.payout) + '</span>' : '')
        : '<span class="mk-pay off">fechada</span>';
      return '<button type="button" data-kind="' + k + '" aria-pressed="' + (k === kind) + '"' +
        (has ? '' : ' disabled title="' + esc(p.asset) + ' não tem ' + KIND_TEXT[k] + '"') + '>' + capitalize(KIND_TEXT[k]) + pay + '</button>';
    }).join('');
    if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
  }
  function manualBlock(asset, p, amount, kind) {
    var s = state.status;
    if (!asset) return 'Escolha um par acima do gráfico.';
    if (s && s.status === 'reconectando') return 'O bot está reconectando à IQ: espere alguns segundos.';
    if (!p) return state.pairsError ? 'Sem conexão com a IQ agora.' : (state.pairs ? asset + ' não está na lista de pares da IQ.' : 'Carregando a lista de pares…');
    var side = kindSide(p, kind || 'binary');
    if (!side.open) return side.reason || asset + ' está fechado para ' + KIND_TEXT[kind || 'binary'] + ' agora.';
    if (!isFinite(amount) || amount <= 0) return 'Digite o valor da entrada.';
    if (kind === 'digital') return '';  // a IQ não informa os limites da digital: ela mesma recusa o que não aceitar
    if (p.min != null && amount < p.min) return 'Valor mínimo neste par: ' + fmtMoney(p.min) + '.';
    if (p.max != null && amount > p.max) return 'Valor máximo neste par: ' + fmtMoney(p.max) + '.';
    return '';
  }
  function manualOrderText(o) {
    var st = orderState(o);
    var money = o.profit != null && st.kind === 'sent' && o.status !== 'aberta' ? ' ' + fmtMoney(o.profit, true) : '';
    return '<div class="m-last ' + (st.kind === 'fail' ? 'bad' : (st.cls || '')) + '">' + dirHtml(o.direction) + ' ' + esc(o.asset) + kindTag(o.option_type) + ' ' + fmtMoney(o.amount) +
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
    var kind = manualKind(p), side = kindSide(p, kind);
    renderKindToggle(p, kind);
    $('#m-payout').textContent = side && side.payout != null ? payoutPct(side.payout) : '—';
    var exps = side && side.expiries.length ? side.expiries : [1, 2, 3, 4, 5];
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
    $('#m-win').textContent = side && side.payout != null && isFinite(amount) && amount > 0 ? 'se ganhar: ' + fmtMoney(amount * side.payout, true) : '';
    var why = manualBlock(asset, p, amount, kind);
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
    var now = serverNow(), minutes = manualMinutesNow();
    var end = manualKind(pairInfo(focusAsset())) === 'digital' ? digitalExpiryFor(now, minutes) : expiryFor(now, minutes);
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
    if (p && manualKind(p) === 'digital') p = null;  // os limites da lista são os da binária
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
    var asset = focusAsset(), p = pairInfo(asset), amount = manualAmount(), minutes = manualMinutesNow(), kind = manualKind(p);
    if (state.manualSending || manualBlock(asset, p, amount, kind)) return;
    state.manualSending = true;
    state.manualError = null;
    state.manualAmount = amount;
    saveStored('botbene-manual-valor', amount);
    saveStored('botbene-manual-min', minutes);
    renderManual();
    api('/api/orders/manual', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ asset: asset, direction: direction, amount: amount, minutes: minutes, kind: kind }) })
      .then(function (row) { state.ordersById[row.id] = row; state.manualLastId = row.id; })
      .catch(function (e) { state.manualLastId = null; state.manualError = e.message; })
      .then(function () { state.manualSending = false; renderManual(); });
  }

  // ------------------------------------------------------------------ próxima entrada (apostila)
  function capitalize(text) { return text.charAt(0).toUpperCase() + text.slice(1); }

  // Troca entre OTC e mercado normal: o que acabou de trocar, o que está esperando e quando o normal abre.
  var SWITCH_NOTE_SECONDS = 15 * 60;
  function marketNote(s) {
    var out = '', now = serverNow();
    var groups = {}, order = [];
    (s.market_swaps || []).filter(function (w) { return now - w.at < SWITCH_NOTE_SECONDS; }).forEach(function (w) {
      if (!groups[w.reason]) { groups[w.reason] = []; order.push(w.reason); }
      groups[w.reason].push(w);
    });
    order.forEach(function (reason) {
      var list = groups[reason].slice().reverse();  // na ordem em que trocou
      out += '<div class="pairs-note">' + esc(capitalize(reason)) + ' às ' + fmtTime(list[list.length - 1].at) + ': o bot trocou ' +
        list.map(function (w) { return esc(w.from) + ' → <strong>' + esc(w.to) + '</strong>'; }).join(', ') + '</div>';
    });
    var waiting = (s.assets || []).filter(function (a) { return a.switch_to && a.switch_wait; });
    if (waiting.length) {
      out += '<div class="pairs-note">Troca pendente: ' + waiting.map(function (a) {
        return esc(a.asset) + ' → <strong>' + esc(a.switch_to) + '</strong> (' + esc(a.switch_wait) + ')';
      }).join(' · ') + '</div>';
    }
    // Quando o mercado normal abre (e fecha) fica na faixa "Mercado normal" acima do gráfico (renderMarketClock).
    return out;
  }

  // Par fechado para o tipo de opção escolhido não manda ordem: melhor avisar logo do que deixar parecer que o bot parou.
  function openPairsNote(s) {
    return marketNote(s) + closedPairsNote(s);
  }
  function closedPairsNote(s) {
    var assets = s.assets || [];
    var closed = assets.filter(function (a) { return !a.tradable; });
    if (!closed.length) return '';
    var forWhat = { binary: ' para binária', digital: ' para digital', best: ' (nem binária nem digital)' }[s.option_type || 'binary'] || '';
    if (closed.length === assets.length) {
      return '<div class="pairs-note warn">' + (assets.length > 1 ? 'Nenhum par aberto' : 'Par fechado') + forWhat + ' agora: as entradas ficam só anotadas.</div>';
    }
    return '<div class="pairs-note"><strong>' + (assets.length - closed.length) + ' de ' + assets.length + '</strong> pares abertos' +
      (s.option_type === 'best' ? '' : forWhat) + ' · fechados: ' + esc(closed.map(function (a) { return a.asset; }).join(', ')) + '</div>';
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
        if (a.strategy === DEEPLOB) {
          return head +
            '<div class="armed-level">Entrada no início da vela das <strong>' + fmtTime(a.target_ts) + '</strong> <span class="muted">· ' +
              esc(a.level_sources[0] || '') + '</span></div>' +
            '<div class="muted small">A rede DeepLOB leu as últimas 100 velas de 5 s e passou do limiar. Anota ' +
              (a.direction === 'call' ? 'CALL' : 'PUT') + ' no 1º preço da vela, com vencimento no fim dela. Só observa: não manda ordem.</div>' +
          '</div>';
        }
        if (a.strategy === ESTICAO) {
          return head +
            '<div class="armed-level">Gatilho <strong>' + fmtPrice(a.level_price) + '</strong> <span class="muted">· ' +
              esc(a.level_sources[0] || '') + ' a partir da abertura</span></div>' +
            '<div class="muted small">A vela anterior foi grande. Anota ' + (a.direction === 'call' ? 'CALL' : 'PUT') +
              ' se a vela das ' + fmtTime(a.target_ts) + ' disparar até o gatilho nos primeiros ' + a.window_seconds +
              ' s (vale o lado que tocar primeiro). Só observa: não manda ordem.</div>' +
          '</div>';
        }
        if (isRetracao(a.strategy)) {
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

  // Pedidos de entrada: uma linha compacta por pedido, acima do Painel. A análise é no gráfico principal: ele vai
  // sozinho para o par do pedido mais urgente, ou, se você está analisando outro par, a linha pergunta antes de trocar.
  // Ordem enviada ou recusada pela corretora vira um aviso pequeno no canto, que some sozinho (o resto fica em Ordens).
  var ANALYZE_MS = 90000;  // trocou de par ou mexeu no gráfico há menos que isso = está analisando
  function analyzingOther(asset) {
    return focusAsset() !== asset && Date.now() - (state.lastChartTouch || 0) < ANALYZE_MS;
  }
  function goToChart(asset) {
    if (!asset || asset === focusAsset()) return;
    saveStored('botbene-focus', asset);
    focusOn(asset).catch(function () {});
  }

  function renderApprovals(s) {
    var tray = $('#approvals');
    var all = ((s && s.approvals) || []).concat(state.demoApproval ? [state.demoApproval] : []);
    var now = Date.now() / 1000;
    state.focusAsk = state.focusAsk || {};
    if (!state.apInit) {  // ao abrir o painel, pedidos que já tinham terminado não reaparecem (nem mudam o gráfico)
      all.forEach(function (a) { if (!isOpenApproval(a)) { state.doneAt[a.id] = -1; state.entrySeen[a.id] = true; } });
      state.apInit = true;
    }
    // Ordem enviada: o gráfico vai para o par dela quando não houver pedido aberto, se você não estiver analisando outro.
    all.forEach(function (a) {
      if (a.demo || a.status !== 'ordem enviada' || state.entrySeen[a.id]) return;
      state.entrySeen[a.id] = true;
      state.entryFocus = a.asset;  // várias de uma vez: vale a última
    });
    // No modo automático puro o bot entra sozinho: a linha não aparece antes; só o aviso, se a ordem saiu.
    var pureAuto = function (a) { return a.auto && !a.veto; };
    all.forEach(function (a) {
      if (isOpenApproval(a)) {
        if (pureAuto(a)) return;
        if (!state.seenOpen[a.id]) { state.seenOpen[a.id] = true; alertApproval(a, 'novo'); }
        if (a.status === 'disparou' && !state.beeped[a.id]) { state.beeped[a.id] = true; alertApproval(a, 'disparou'); }
      } else if (state.doneAt[a.id] == null && (state.seenOpen[a.id] || (pureAuto(a) && approvalOutcome(a).kind !== 'none'))) {
        state.doneAt[a.id] = now;
        outcomeSound(a);
      } else if (state.soundKind[a.id] === 'sent' && approvalOutcome(a).kind === 'fail') {
        state.soundKind[a.id] = 'fail';  // a corretora recusou depois de o pedido sair
        playSound('sem_ordem');
      }
    });
    var open = all.filter(function (a) { return isOpenApproval(a) && !pureAuto(a); });
    if (!open.length && state.entryFocus) {
      var entryAsset = state.entryFocus;
      state.entryFocus = null;
      if (!analyzingOther(entryAsset)) goToChart(entryAsset);
    }
    var isSel = function (a) { return String(a.id) === String(state.approvalSel); };
    if (!open.some(isSel)) {
      var urgent = open.slice().sort(function (x, y) { return x.deadline - y.deadline; })[0];
      state.approvalSel = urgent ? String(urgent.id) : null;
    }
    var sel = open.filter(isSel)[0] || null;
    state.approvalSelObj = sel;
    // O pedido mais urgente decide o gráfico, uma vez: vai sozinho, ou pergunta se você está analisando outro par.
    if (sel && !sel.demo && !state.focusAsk[sel.id]) {
      if (sel.asset === focusAsset()) state.focusAsk[sel.id] = 'aqui';
      else if (analyzingOther(sel.asset)) state.focusAsk[sel.id] = 'perguntar';
      else { state.focusAsk[sel.id] = 'foi'; goToChart(sel.asset); }
    }
    renderToasts(all, now);
    if (!open.length) { tray.hidden = true; tray.innerHTML = ''; state.approvalSelObj = null; resetTitle(); return; }
    tray.hidden = false;
    tray.innerHTML = open.map(approvalRowHtml).join('');
    var waiting = open.filter(function (a) { return a.status === 'aguardando' || a.status === 'disparou'; }).length;
    if (waiting) document.title = '● Aprovar entrada · BotBene'; else resetTitle();
    updateApprovalClocks();
  }
  function resetTitle() { if (document.title !== 'BotBene') document.title = 'BotBene'; }

  // Aviso no canto: só ordem enviada (com o resultado) e ordem recusada pela corretora. Pedido sem ordem (o preço não
  // veio, a gestão de risco barrou, você cancelou) não vira aviso: fica na lista de Ordens e em "Últimos setups".
  function toastBox() {
    var box = $('#ap-toasts');
    if (box) return box;
    box = document.createElement('div');
    box.id = 'ap-toasts';
    box.className = 'ap-toasts';
    box.setAttribute('aria-live', 'polite');
    (document.querySelector('.app') || document.body).appendChild(box);
    box.addEventListener('click', function (e) {
      var x = e.target.closest('[data-dismiss]');
      if (!x) return;
      state.toastGone[x.dataset.dismiss] = true;
      var el = x.closest('.ap-toast');
      if (el) el.remove();
    });
    return box;
  }
  function renderToasts(all, now) {
    state.toastGone = state.toastGone || {};
    var items = all.filter(function (a) {
      if (isOpenApproval(a) || !(state.doneAt[a.id] > 0) || state.toastGone[a.id]) return false;
      var oc = approvalOutcome(a);
      var refused = oc.kind === 'fail' && a.status !== 'bloqueada';  // a corretora recusou (não a gestão de risco)
      return (oc.kind === 'sent' || refused) && now < outcomeUntil(a, oc);
    }).slice(-4);
    var box = $('#ap-toasts');
    if (!items.length && !box) return;
    toastBox().innerHTML = items.map(toastHtml).join('');
  }
  function toastHtml(a) {
    var oc = approvalOutcome(a);
    var res = oc.result ? '<span class="ap-toast-res ' + oc.result.cls + '">' + esc(shortResult(oc.result.text)) + '</span>' : '';
    return '<div class="ap-toast ' + oc.kind + '" data-until="' + outcomeUntil(a, oc) + '" role="status">' +
      '<span class="ap-toast-icon" aria-hidden="true">' + oc.icon + '</span>' +
      '<div class="ap-toast-text"><strong>' + (oc.kind === 'sent' ? (a.demo ? 'Exemplo' : 'Ordem enviada') : 'Ordem recusada') + '</strong> · ' +
        esc(oc.reason) + '</div>' + res +
      '<button type="button" class="ap-x" data-dismiss="' + esc(a.id) + '" aria-label="Fechar aviso">×</button></div>';
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

  // Gale por estratégia: só as marcadas recebem o valor do gale (servidor antigo, sem a lista: todas).
  function usesGale(c, strategy) {
    return !!c.martingale && (c.gale_strategies == null || c.gale_strategies.indexOf(strategy) >= 0);
  }
  // Ciclo de gale de uma estratégia: cada uma tem o seu (servidor antigo: um ciclo só, nos campos de cima do risco).
  function cycleOf(risk, strategy) {
    if (!risk.cycles) return risk;
    for (var i = 0; i < risk.cycles.length; i++) if (risk.cycles[i].strategy === strategy) return risk.cycles[i];
    var stake = (risk.config || {}).stake;
    return { gale_level: 0, next_stake: stake != null ? stake : risk.next_stake };
  }
  function stakeFor(risk, strategy) {
    var c = risk.config || {};
    if (!usesGale(c, strategy)) return fmtMoney(c.stake != null ? c.stake : risk.next_stake);
    var cy = cycleOf(risk, strategy);
    return fmtMoney(cy.next_stake) + (cy.gale_level ? ' <span class="tag gale-tag">gale ' + cy.gale_level + ' de ' + c.gale_levels + '</span>' : '');
  }
  // Ciclos de gale abertos (houve perda e o próximo gale ainda não saiu nem fechou o ciclo), um por estratégia.
  function openCycles(risk) {
    var c = risk && risk.config;
    if (!c || !c.martingale) return [];
    return (risk.cycles || [risk]).filter(function (x) { return x.gale_level > 0; });
  }
  function galeCycle(risk) { return openCycles(risk).length ? risk.config : null; }
  // Aviso no topo, visível em qualquer página, enquanto o bot roda com um ciclo aberto.
  function renderGaleChip(s) {
    var el = $('#gale-chip');
    if (!el) return;
    var risk = s && s.risk, c = galeCycle(risk);
    if (!c || !isBusy(s)) { el.hidden = true; return; }
    el.hidden = false;
    var open = openCycles(risk);
    el.innerHTML = '<span class="gale-icon" aria-hidden="true">↻</span><span><strong>' +
      (open.length > 1 ? open.length + ' ciclos de gale' : 'Ciclo de gale') + '</strong> · ' + open.map(function (cy) {
        var next = cy.gale_open ? 'aguardando o resultado' : 'próxima ' + fmtMoney(cy.next_stake);
        return (cy.strategy ? esc(label(cy.strategy)) + ' ' : '') + 'gale ' + cy.gale_level + ' de ' + c.gale_levels +
          ' <span class="muted small">· ' + esc(next) + '</span>';
      }).join(' · ') + '</span>';
    el.title = 'Houve perda: a próxima entrada ' + (open.length > 1 ? 'de cada uma dessas estratégias' : open[0].strategy ? 'dela' : 'aprovada') +
      ' vale mais, para recuperar o ciclo. Cada estratégia tem o seu ciclo.';
  }
  // Etapas do ciclo de uma estratégia: o que já perdeu, a entrada da vez e os gales que ainda podem vir.
  function galeCycleHtml(risk, c) {
    var busy = !!(state.status && isBusy(state.status));
    var lost = risk.cycle_stakes;  // servidor antigo: não manda os valores
    var steps = [];
    for (var i = 0; i <= c.gale_levels; i++) {
      var name = i === 0 ? 'Entrada' : 'Gale ' + i;
      if (i < risk.gale_level) {
        steps.push('<li class="lost">' + name + (lost && lost[i] != null ? ' ' + fmtMoney(lost[i]) : '') + ' ✗</li>');
      } else if (i === risk.gale_level) {
        var when = !busy ? 'não saiu' : risk.gale_open ? 'aberta' : 'próxima';
        steps.push('<li class="now">' + name + ' ' + fmtMoney(risk.next_stake) + ' · ' + when + '</li>');
      } else {
        steps.push('<li class="later">' + name + '</li>');
      }
    }
    var p = (state.status && state.status.payout) || 0.85;
    var info = [];
    if (risk.cycle_loss != null) info.push('perdido no ciclo: <strong>' + fmtMoney(risk.cycle_loss) + '</strong>');
    if (busy) {
      info.push((risk.gale_open ? 'se a ordem aberta ganhar' : 'se a próxima ganhar') + ', o ciclo fecha em cerca de <strong>' +
        fmtMoney(c.stake * p, true) + '</strong>');
      if (risk.cycle_worst) info.push('se perder até o último gale: <strong>' + fmtMoney(-risk.cycle_worst, true) + '</strong>');
    } else {
      info.push('o bot parou no meio do ciclo; ao iniciar de novo, a próxima entrada volta ao valor normal');
    }
    return '<div class="gale-cycle' + (busy ? '' : ' stopped') + '" role="status">' +
      '<div class="gc-head"><strong>' + (busy ? 'Ciclo de gale em andamento' : 'Ciclo de gale interrompido') + '</strong>' +
      (risk.strategy ? ' <span class="muted small">· ' + esc(label(risk.strategy)) + '</span>'
        : c.gale_strategies ? ' <span class="muted small">· ' + esc(galeNames(c)) + '</span>' : '') + '</div>' +
      '<ol class="gc-steps">' + steps.join('') + '</ol><div class="gc-info">' + info.join(' · ') + '</div></div>';
  }
  function galeNames(c) {
    return c.gale_strategies ? c.gale_strategies.map(label).join(', ') : '';
  }

  function approvalRowHtml(a) {
    var st = apState(a.status);
    var risk = state.status && state.status.risk;
    var stake = a.demo ? fmtMoney(2) : risk ? stakeFor(risk, a.strategy) : '—';
    var call = a.direction === 'call';
    var buttons;
    if (a.status === 'aprovado' || a.status === WAIT_GALE) {
      buttons = '<button type="button" class="reject" data-act="rejeitar" data-id="' + esc(a.id) + '">' + (a.auto ? 'Cancelar entrada' : 'Cancelar aprovação') + '</button>';
    } else {
      buttons = '<button type="button" class="approve" data-act="aprovar" data-id="' + esc(a.id) + '">✓ Aprovar ' + (call ? 'CALL' : 'PUT') +
        (a.status === 'disparou' ? ' agora' : '') + '</button>' +
        '<button type="button" class="reject" data-act="rejeitar" data-id="' + esc(a.id) + '">Rejeitar</button>';
    }
    var here = a.asset === focusAsset();
    var chart = '';
    if (!here && state.focusAsk[a.id] === 'perguntar') {
      chart = '<div class="ap-ask"><span>Você está analisando <strong>' + esc(focusAsset() || 'outro par') + '</strong>. Ir para o gráfico desta entrada?</span>' +
        '<button type="button" class="ap-go" data-goto="' + esc(a.asset) + '">Ir para ' + esc(a.asset) + '</button>' +
        '<button type="button" class="ap-stay" data-stay="' + esc(a.id) + '">Ficar aqui</button></div>';
    } else if (!here) {
      chart = '<button type="button" class="ap-stay" data-goto="' + esc(a.asset) + '">Ver no gráfico</button>';
    }
    var stateText = a.auto && a.status === 'aprovado' ? 'Automático: a ordem sai sozinha se o gatilho disparar' : st.text;
    return '<div class="ap-row' + (String(a.id) === String(state.approvalSel) ? ' sel' : '') + '" style="border-left-color:' + strategyColor(a.strategy) + '">' +
      '<div class="ap-main">' +
        '<div class="ap-title"><span class="dir">' + (call ? '▲ CALL' : '▼ PUT') + '</span><strong>' + esc(a.asset) + '</strong>' + kindTag(a.kind) +
          '<span class="muted small">' + esc(label(a.strategy)) + (a.demo ? ' · exemplo, não envia nada' : '') + '</span></div>' +
        '<div class="ap-facts small">gatilho <strong>' + fmtPrice(a.level_price) + '</strong>' +
          (here ? ' · <span id="ab-now">' + approvalNowText(a) + '</span>' : '') +
          ' · valor ' + stake + ' · vela das ' + fmtTime(a.target_ts) + ', vence ' + fmtTime(a.target_ts + (a.timeframe || 60)) + '</div>' +
        '<div class="ap-state small ' + st.cls + '"><span aria-hidden="true">' + st.icon + '</span> ' + esc(stateText) +
          (a.note ? ' · ' + esc(a.note) : '') + '</div>' +
      '</div>' +
      '<div class="ap-clock"><span class="clock" data-deadline="' + a.deadline + '">—</span><span class="muted small">janela</span></div>' +
      chart +
      '<div class="ap-buttons">' + buttons + '</div>' +
    '</div>';
  }

  function updateApprovalClocks() {
    var now = Date.now() / 1000, iq = serverNow();
    Array.prototype.forEach.call(document.querySelectorAll('#approvals .clock'), function (c) {
      var left = Math.ceil(parseFloat(c.dataset.deadline) - iq);
      c.textContent = left > 0 ? left + ' s' : '0 s';
    });
    Array.prototype.forEach.call(document.querySelectorAll('#ap-toasts .ap-toast'), function (el) {
      if (now >= parseFloat(el.dataset.until)) el.remove();
    });
  }

  function unlockAudio() {
    try {
      if (!state.audio) state.audio = new (window.AudioContext || window.webkitAudioContext)();
      if (state.audio.state === 'suspended') state.audio.resume();
    } catch (e) { state.audio = null; }
  }
  // Sons dos pedidos. Cada nota: [frequência em Hz, início em s, duração em s]. As notas não se sobrepõem,
  // então o volume máximo (0,8) não estoura. O bipe do pedido novo é o de sempre, agora mais alto (era 0,25).
  var SOUNDS = {
    card: { wave: 'sine', octave: 0.25, notes: [[880, 0, 0.18], [880, 0.24, 0.18]] },
    disparou: { wave: 'sine', octave: 0.25, notes: [[880, 0, 0.16], [880, 0.21, 0.16], [880, 0.42, 0.16]] },
    entrada: { wave: 'triangle', notes: [[660, 0, 0.12], [880, 0.13, 0.12], [1320, 0.26, 0.45]] },   // sobe: entrou
    sem_ordem: { wave: 'triangle', notes: [[440, 0, 0.22], [294, 0.25, 0.4]] }                      // desce: sem ordem
  };
  var SOUND_PEAK = 0.8;
  // Terminou assim porque você mesmo decidiu: não precisa de aviso.
  var SILENT_END = ['rejeitado', 'cancelado por você', 'cancelado: modo só sinais', 'cancelado: bot parado'];
  state.soundVolume = Math.min(1, Math.max(0, Number(loadStored('botbene-volume', 1)) || 0));
  function playSound(name) {
    var ctx = state.audio, sound = SOUNDS[name], peak = SOUND_PEAK * state.soundVolume;
    if (!ctx || !sound || peak <= 0) return;
    if (ctx.state === 'suspended') ctx.resume();
    var t0 = ctx.currentTime + 0.02;
    sound.notes.forEach(function (n) {
      var t = t0 + n[1], end = t + n[2];
      [[n[0], 1 - (sound.octave || 0)], [n[0] * 2, sound.octave || 0]].forEach(function (voice) {
        if (!voice[1]) return;  // oitava acima: dá presença no alto-falante do notebook
        var o = ctx.createOscillator(), g = ctx.createGain(), top = peak * voice[1];
        o.type = sound.wave; o.frequency.value = voice[0];
        g.gain.setValueAtTime(0.0001, t);
        g.gain.exponentialRampToValueAtTime(top, t + 0.015);
        g.gain.setValueAtTime(top, t + n[2] * 0.6);
        g.gain.exponentialRampToValueAtTime(0.0001, end);
        o.connect(g); g.connect(ctx.destination); o.start(t); o.stop(end + 0.02);
      });
    });
  }
  function alertApproval(a, kind) {
    if (a.status === 'aprovado' && kind === 'novo' && !a.veto) return;
    playSound(kind === 'disparou' ? 'disparou' : 'card');
  }
  // Pedido terminou: som de entrada se a ordem saiu, som de "sem ordem" se não saiu.
  function outcomeSound(a) {
    var kind = approvalOutcome(a).kind;
    state.soundKind[a.id] = kind;
    if (kind === 'sent') playSound('entrada');
    else if (SILENT_END.indexOf(a.status) < 0) playSound('sem_ordem');
  }
  function renderVolume() {
    var pct = Math.round(state.soundVolume * 100);
    $('#snd-volume').value = pct;
    $('#snd-volume-text').textContent = pct ? pct + '%' : 'sem som';
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
    $('#side-mini').title = (real ? 'Conta REAL' : 'Conta demo') +
      (info && info.balance != null ? ' · saldo ' + fmtMoney(info.balance + (info.bonus || 0)) : '') +
      (state.connected ? ' · servidor conectado' : ' · sem conexão');
    $('#orders-title').textContent = real ? 'Ordens na conta REAL' : 'Ordens na conta demo';
    renderManual();
    var el = $('#acct-balance');
    if (!info) { el.textContent = 'Saldo —'; return; }
    if (info.error) { el.textContent = 'Sem conexão com a IQ'; el.title = info.error; return; }
    el.title = '';
    if (info.balance == null) { el.textContent = 'Saldo —'; return; }
    var bonus = info.bonus || 0;
    var cur = info.currency || 'USD', fmt;
    try { fmt = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: cur }); }
    catch (e) { fmt = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 2 }); }
    var sameAccount = info.account === chosen;
    // Como no site da IQ: saldo e bônus somados. A separação fica só na dica do mouse (o bônus costuma ter regras para saque).
    el.innerHTML = 'Saldo ' + (real ? '<span class="acct-real">real</span>' : 'demo') + ': <strong>' + fmt.format(info.balance + bonus) + '</strong>' +
      (sameAccount ? '' : ' <span class="muted">(conectando na conta escolhida…)</span>');
    if (bonus) el.title = fmt.format(info.balance) + ' de saldo + ' + fmt.format(bonus) + ' de bônus.';
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
      (c.martingale ? ' · martingale até ' + c.gale_levels + ' gale' + (c.gale_levels > 1 ? 's' : '') +
        (c.gale_strategies ? ' só em ' + esc(galeNames(c)) : '') +
        (c.max_lost_cycles ? ' · stop de ciclo: ' + (risk.lost_cycles || 0) + ' de ' + c.max_lost_cycles + ' perdidos'
          : risk.lost_cycles ? ' · ' + risk.lost_cycles + ' ciclo' + (risk.lost_cycles > 1 ? 's' : '') + ' perdido' + (risk.lost_cycles > 1 ? 's' : '') : '')
        : '') + filtersText() + '</div>';
    openCycles(risk).forEach(function (cy) { html += galeCycleHtml(cy, c); });
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
    if (cfg.option_type && cfg.option_type !== 'binary') out += ' · ' + OPTION_TYPE_TEXT[cfg.option_type];
    if (cfg.min_payout != null) out += ' · payout mín. ' + Math.round(cfg.min_payout * 100) + '%';
    if (cfg.hours_start && cfg.hours_end) out += ' · opera das ' + cfg.hours_start + ' às ' + cfg.hours_end;
    return out;
  }

  function refreshOrders() {
    var since = painelSince();
    api('/api/orders?period=' + (since ? '7d' : 'hoje') + '&limit=2000').then(function (all) {
      all.forEach(function (o) { state.ordersById[o.id] = o; });
      var rows = since ? all.filter(function (o) { return o.requested_at >= since; }) : all;
      state.painelOrders = rows;
      state.ordersSince = since;
      renderOrderList(rows);
      renderOrderStats();
      renderFeed();
      if (state.status) { renderApprovals(state.status); renderArmed(state.status); }
      renderManual();
    }).catch(function () {});
  }

  function renderOrderList(rows) {
    $('#orders-cap').textContent = state.ordersSince ? 'Nesta sessão' : 'Hoje';
    var el = $('#orders');
    if (!rows.length) {
      el.innerHTML = '<li class="empty">Nenhuma ordem ' + (state.ordersSince ? 'nesta sessão' : 'hoje') + '.</li>';
      return;
    }
    el.innerHTML = rows.slice(0, 100).map(function (o) {
      var st = orderState(o);
      var money = o.profit != null && st.kind !== 'fail' ? ' ' + fmtMoney(o.profit, true) : '';
      var profit = st.detail ? '<div class="oc-res ' + (st.cls || '') + '">' + esc(st.detail + money) + '</div>' : '';
      return '<li title="' + esc(o.error || '') + '"><span class="when">' + fmtTime(o.requested_at) + '</span>' +
        '<div class="what"><div class="line1">' + dirHtml(o.direction) + ' <span class="muted small">' + esc(o.asset) + '</span>' +
          (o.strategy === MANUAL ? ' <span class="manual-tag">MANUAL</span>' : '') + '</div>' +
        '<div class="line2">' + (o.option_type === 'digital' ? 'digital · ' : '') + fmtMoney(o.amount) +
          (o.account === 'REAL' ? ' · <span class="acct-real">REAL</span>' : ' · demo') +
          (o.gale ? ' · gale ' + o.gale : '') + (o.status === 'aberta' && o.expires_at ? ' · vence ' + fmtTime(o.expires_at) : '') +
          (st.kind === 'fail' && o.error ? ' · ' + esc(o.error) : '') + '</div></div>' +
        '<div class="right"><span class="oc-pill ' + st.kind + '">' + esc(st.label) + '</span>' + profit + '</div></li>';
    }).join('');
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
  function renderKpis(prefix, st, money) {
    var t = st.total;
    var count = t.n + t.draws;
    var profit = $('#' + prefix + '-profit');
    profit.textContent = count ? (money ? fmtMoney(t.profit, true) : fmtUnits(t.profit)) : '—';
    profit.className = 'hero-value ' + (count ? signClass(t.profit) : '');
    $('#' + prefix + '-wr').textContent = t.n ? fmtPct(t.winrate) : '—';
    $('#' + prefix + '-wr-sub').innerHTML = t.n
      ? 'IC 95% ' + fmtPct(t.ci_low) + '–' + fmtPct(t.ci_high) + (t.n < MIN_SAMPLE ? '<span class="warn-chip">amostra pequena</span>' : '')
      : (money ? 'sem ordens com resultado' : 'sem entradas avaliadas');
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
  // O Painel conta ORDENS: o que entrou na corretora, em dinheiro, de hoje ou só da sessão. A lista mostra os sinais,
  // cada um com o que aconteceu com a ordem dele. O acerto das estratégias nos sinais fica em Entradas.
  var FEED_LIMIT = 500;
  var STATE_TAG = { operate: 'opera', observe: 'observa', off: 'desligada' };
  function refreshPainel() { refreshChart(); refreshToday(); refreshOrders(); }

  // Início da sessão (clique em Iniciar bot); null com o bot parado.
  function sessionStart() {
    var s = state.status;
    return isBusy(s) && s.started_at ? s.started_at : null;
  }
  // Desde quando o Painel conta: o início da sessão (caixa marcada e bot rodando) ou null = hoje.
  function painelSince() { return state.sessionOnly ? sessionStart() : null; }
  function painelWhen(since) { return since ? 'da sessão' : 'de hoje'; }

  function refreshToday() {
    renderScope();
    if (state.painelOrders) renderOrderStats();  // quem opera pode ter mudado na Configuração
    var since = painelSince();
    api('/api/signals?period=' + (since ? '7d' : 'hoje') + '&origin=ao_vivo&limit=' + FEED_LIMIT + scopeQuery()).then(function (rows) {
      state.feedFull = rows.length >= FEED_LIMIT;
      state.feedRows = since ? rows.filter(function (r) { return r.entry_ts >= since; }) : rows;
      state.feedSince = since;
      renderFeed();
    }).catch(function () {});
  }

  function renderScope() {
    if (!state.config) return;
    var main = mainStrategies();
    var start = sessionStart();
    var box = '<label class="check" title="' + (start ? 'Só o que aconteceu desde que você clicou em Iniciar bot'
      : 'A sessão começa quando você clica em Iniciar bot') + '"><input type="checkbox" id="p-session"' +
      (state.sessionOnly ? ' checked' : '') + (start ? '' : ' disabled') + '> só esta sessão' +
      (start ? ' <span class="muted">(desde ' + fmtTime(start) + ')</span>' : '') + '</label>';
    if (state.config.martingale) {
      box += '<label class="check" title="Com martingale, cada ciclo (entrada + gales) conta uma vez: vitória se terminou ganho, ' +
        'derrota só se perdeu até o último gale (ou ficou no meio quando o bot parou). O resultado em dinheiro não muda.">' +
        '<input type="checkbox" id="p-cycle"' + (state.byCycle ? ' checked' : '') + '> contar por ciclo de gale</label>';
    }
    if (!main.length) {
      $('#p-scope').innerHTML = '<span>Nenhuma estratégia ligada. Escolha em Configuração.</span>' + box;
      return;
    }
    var observing = strategiesIn(['observe']).filter(function (n) { return main.indexOf(n) < 0; });
    $('#p-scope').innerHTML = '<span>Ordens ' + painelWhen(painelSince()) + ' na ' + accountLabel() + ' · sinais de ' +
      main.map(function (n) { return stratHtml(n); }).join(' ') + '</span>' + box +
      (observing.length ? '<span class="muted small">Só observando (sem ordem): ' + esc(observing.map(label).join(', ')) + '</span>' : '');
  }
  // As que estão rodando agora (ligar ou desligar vale no próximo início); com o bot parado, as ligadas.
  function shownStrategies() {
    var s = state.status;
    return isBusy(s) && s.active_strategies ? s.active_strategies : strategiesIn(['operate', 'observe']);
  }

  function wilson(wins, n) {
    if (!n) return [null, null];
    var z = 1.96, p = wins / n, d = 1 + z * z / n;
    var c = (p + z * z / (2 * n)) / d, h = z * Math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d;
    return [Math.max(0, c - h), Math.min(1, c + h)];
  }
  // Como na tela Desempenho: dinheiro e acerto só com as ordens que entraram e têm resultado.
  function orderTotals(rows) {
    var t = { wins: 0, losses: 0, draws: 0, profit: 0, notSent: 0, open: 0, noResult: 0, paidSum: 0 };
    rows.forEach(function (o) {
      if (o.status === 'win' || o.status === 'loss' || o.status === 'empate') {
        if (o.status === 'win') { t.wins++; if (o.amount) t.paidSum += (o.profit || 0) / o.amount; }
        else if (o.status === 'loss') t.losses++;
        else t.draws++;
        t.profit += o.profit || 0;
      } else if (o.status === 'bloqueada' || o.status === 'erro') t.notSent++;
      else if (o.status === 'sem_resultado') t.noResult++;
      else t.open++;  // enviando ou aberta
    });
    t.n = t.wins + t.losses;
    t.profit = Math.round(t.profit * 100) / 100;
    t.winrate = t.n ? t.wins / t.n : null;
    var ci = wilson(t.wins, t.n);
    t.ci_low = ci[0];
    t.ci_high = ci[1];
    t.paid = t.wins ? t.paidSum / t.wins : null;  // payout pago de fato (média das vitórias)
    return t;
  }

  // "Contar por ciclo de gale" marcado e martingale ligado na Configuração.
  function cycleMode() { return !!(state.byCycle && state.config && state.config.martingale); }
  function beSubText(s) {
    var base = s && s.payout ? 'payout de ' + fmtPct(s.payout) + (s.asset ? ' no ' + s.asset : '') : 'depende do payout';
    if (!cycleMode()) return base;
    var n = state.config.gale_levels || 1;
    return 'por ciclo, com ' + n + ' gale' + (n > 1 ? 's' : '') + ' · ' + base;
  }
  // Acerto mínimo na contagem por ciclo: o ciclo ganho rende ~uma entrada e conta 1 vitória; o perdido custa a entrada
  // e todos os gales e conta 1 derrota por ordem perdida (3 no G2). Empata quando vitórias × ganho = ciclos perdidos × perda.
  function cycleBreakeven(c, payout) {
    var stake = c.stake || 2, levels = c.martingale ? (c.gale_levels || 1) : 0, loss = 0, s = stake;
    for (var i = 0; i <= levels; i++) { loss += s; s = galeStake(stake, loss, payout); }
    return loss / (loss + (levels + 1) * stake * payout);
  }
  // Ciclos de gale a partir das ordens. Entrada (gale 0) de quem usa o gale abre um ciclo; gale 1, 2… continua o ciclo
  // aberto. Termina na vitória (ganho) ou numa perda sem continuação: chegou ao último gale, a entrada seguinte já abriu
  // outro ciclo, ou o bot parou no meio (perdido, porque o dinheiro foi perdido). Quem não usa o gale: cada ordem é um
  // ciclo. Bloqueadas e recusadas passam como estão. Cada ciclo vira uma linha no formato das ordens (para orderTotals):
  // o ganho conta 1 vitória (as perdas dentro dele não contam); o perdido conta cada ordem perdida (3 no G2), para o
  // acerto não esconder o tamanho da perda. As derrotas a mais vão em linhas extras, sem dinheiro (o total não muda).
  function galeCycles(rows) {
    var risk = state.status && state.status.risk;
    // a configuração salva: o placar de risco do bot só recebe a configuração quando o bot inicia
    var c = state.config || (risk && risk.config) || {};
    var levels = c.gale_levels || 1;
    var list = c.gale_strategies != null ? c.gale_strategies : null;
    var inGale = function (o) { return (o.gale || 0) > 0 || (!!c.martingale && (list == null || list.indexOf(o.strategy) >= 0)); };
    var sorted = rows.slice().sort(function (a, b) { return a.requested_at - b.requested_at || a.id - b.id; });
    // Um ciclo aberto por estratégia: cada uma tem o seu desde 09/11/2026 (antes, um ciclo só para todas).
    var out = [], open = {};
    var finish = function (cur) {
      cur.status = cur.loss ? (cur.last === 'sem_resultado' ? 'sem_resultado' : 'loss') : 'empate';
      var extra = cur.status === 'loss' ? cur.losses - 1 : cur.status === 'sem_resultado' ? cur.losses : 0;
      for (var i = 0; i < extra; i++) out.push({ status: 'loss', profit: 0, strategy: cur.strategy, account: cur.account, cycleExtra: true });
      delete open[cur.key];
    };
    sorted.forEach(function (o) {
      var st = o.status;
      if (st === 'bloqueada' || st === 'erro' || !inGale(o)) { out.push(o); return; }
      var key = o.strategy || '', cur = open[key];
      if (!cur && o.gale > 0) {  // ordens de antes dos ciclos separados: o gale continuava o ciclo de outra estratégia
        var keys = Object.keys(open);
        if (keys.length === 1) cur = open[keys[0]];
      }
      if (!cur || !(o.gale > 0)) {
        if (cur) finish(cur);  // a entrada seguinte do gale abriu outro ciclo
        cur = { id: o.id, requested_at: o.requested_at, strategy: o.strategy, account: o.account, amount: o.amount,
                profit: 0, status: 'aberta', loss: false, losses: 0, last: null, cycle: true, key: key };
        open[key] = cur;
        out.push(cur);
      }
      cur.profit += o.profit || 0;
      cur.last = st;
      if (st === 'loss' || st === 'sem_resultado') cur.loss = true;
      if (st === 'loss') cur.losses++;
      if (st === 'win') { cur.status = 'win'; delete open[cur.key]; }
      else if (cur.loss && (o.gale || 0) >= levels && (st === 'loss' || st === 'sem_resultado')) finish(cur);
    });
    Object.keys(open).forEach(function (k) {  // ciclos que ficaram no meio
      var cur = open[k];
      var running = isBusy(state.status) && !!risk && cycleOf(risk, cur.strategy).gale_level > 0;
      if (cur.last === 'aberta' || cur.last === 'enviando' || running) cur.status = 'aberta';
      else finish(cur);
    });
    return out;
  }

  // Números do topo e placar: só as ordens da conta em uso (demo e real não se somam).
  function renderOrderStats() {
    var since = state.ordersSince;
    var acct = state.chosenAccount || 'PRACTICE';
    var mine = (state.painelOrders || []).filter(function (o) { return (o.account || 'PRACTICE') === acct; });
    var byCycle = cycleMode();
    if (byCycle) mine = galeCycles(mine);
    var t = orderTotals(mine);
    var when = painelWhen(since);
    var payout = t.paid || (state.status && state.status.payout) || 0.85;
    $('#p-profit-label').textContent = 'Resultado ' + when;
    $('#p-wr-label').textContent = (byCycle ? 'Acerto por ciclo ' : 'Acerto ') + (since ? 'na sessão' : 'hoje');
    $('#p-n-label').textContent = (byCycle ? 'Contagem por ciclo ' : 'Ordens com resultado ') + (since ? 'na sessão' : 'hoje');
    $('#p-board-n').textContent = byCycle ? 'Contagem' : 'Ordens';
    $('#p-be-sub').textContent = beSubText(state.status);
    renderKpis('p', { total: t, breakeven: byCycle ? cycleBreakeven(state.config, payout) : 1 / (1 + payout) }, true);
    if (byCycle) {
      var lostCycles = mine.filter(function (r) { return r.cycle && r.status === 'loss'; }).length;
      $('#p-n-sub').textContent = intFmt.format(t.wins) + ' ciclos ganhos · ' + intFmt.format(t.losses) + ' derrotas' +
        (lostCycles ? ' (' + lostCycles + ' ciclo' + (lostCycles > 1 ? 's' : '') + ' perdido' + (lostCycles > 1 ? 's' : '') + ')' : '') +
        ' · ' + intFmt.format(t.draws) + ' empates';
    }
    var notes = [];
    if (t.open) notes.push(t.open + (t.open > 1 ? ' abertas' : ' aberta'));
    if (t.notSent) notes.push(t.notSent + ' não saíram');
    if (t.noResult) notes.push(t.noResult + ' sem resultado da IQ');
    var mode = state.status && state.status.mode;
    var head = t.n + t.draws ? 'em dinheiro, só ordens que entraram'
      : mode === 'sinais' ? 'modo "só sinais": nenhuma ordem sai' : 'nenhuma ordem com resultado ' + when;
    $('#p-profit-sub').textContent = head + (notes.length ? ' · ' + notes.join(' · ') : '');
    renderBoard(mine, since);
  }

  function renderBoard(rows, since) {
    $('#p-board-title').textContent = 'Placar ' + painelWhen(since) + ' por estratégia';
    var by = {};
    rows.forEach(function (o) { (by[o.strategy] = by[o.strategy] || []).push(o); });
    var names = strategiesIn(['operate']);
    Object.keys(by).forEach(function (n) { if (names.indexOf(n) < 0) names.push(n); });
    var rank = function (n) { var i = STRATEGY_ORDER.indexOf(n); return i < 0 ? 999 : i; };
    names.sort(function (a, b) { return rank(a) - rank(b); });
    $('#p-board').innerHTML = names.length ? names.map(function (name) {
      var t = orderTotals(by[name] || []);
      var count = t.n + t.draws;
      var who = name === MANUAL ? '<span class="key">Entrada manual</span>'
        : stratHtml(name) + '<span class="tag">' + (STATE_TAG[strategyState(name)] || '') + '</span>';
      var extra = [];
      if (t.open) extra.push(t.open + (t.open > 1 ? ' abertas' : ' aberta'));
      if (t.notSent) extra.push(t.notSent + ' não saíram (bloqueadas ou recusadas)');
      return '<tr><td>' + who + (extra.length ? '<div class="muted small">' + extra.join(' · ') + '</div>' : '') +
        '</td><td class="num">' + intFmt.format(count) + '</td><td class="num">' + t.wins + ' · ' + t.losses +
        '</td><td class="num">' + fmtPct(t.winrate) + '</td><td class="num ' + signClass(t.profit) + '">' +
        (count ? fmtMoney(t.profit, true) : '—') + '</td></tr>';
    }).join('') : '<tr><td colspan="5" class="muted">Nenhuma estratégia operando: só as marcadas "opera" mandam ordem.</td></tr>';
    var observing = strategiesIn(['observe']).filter(function (n) { return names.indexOf(n) < 0; }).length;
    var notes = [];
    if (cycleMode()) {
      var c = state.config, galeWho = c.gale_strategies ? c.gale_strategies.map(label).join(', ') : 'todas';
      var p = (state.status && state.status.payout) || 0.85;
      notes.push('Contando por ciclo de gale: ciclo ganho conta 1 vitória (as perdas dentro dele não contam); ciclo perdido conta ' +
        'cada ordem perdida (' + ((c.gale_levels || 1) + 1) + ' derrotas com ' + (c.gale_levels || 1) + ' gale' + ((c.gale_levels || 1) > 1 ? 's' : '') +
        '). Nessa conta, quem usa gale (' + galeWho + ') precisa de ' + fmtPct(cycleBreakeven(c, p)) +
        ' para empatar; quem não usa continua precisando de ' + fmtPct(1 / (1 + p)) + '.');
    }
    if (observing) {
      notes.push((observing > 1 ? observing + ' estratégias só observam e não mandam ordem' : '1 estratégia só observa e não manda ordem') +
        ': o acerto delas nos sinais está em Entradas.');
    }
    $('#p-board-note').textContent = notes.join(' ');
  }

  // O que aconteceu com a ordem de um sinal.
  function signalOrderPill(r, o) {
    if (!o) {
      return strategyState(r.strategy) === 'operate'
        ? '<span class="oc-pill none" title="Nenhuma ordem foi pedida: par fechado na IQ naquela hora, outra estratégia ficou com a vela, payout abaixo do mínimo, fora do horário, vetada ou modo só sinais">sem ordem</span>'
        : '<span class="oc-pill none">só observa</span>';
    }
    switch (o.status) {
      case 'win': return '<span class="oc-pill good">ordem ' + esc(fmtMoney(o.profit, true)) + '</span>';
      case 'loss': return '<span class="oc-pill bad">ordem ' + esc(fmtMoney(o.profit, true)) + '</span>';
      case 'empate': return '<span class="oc-pill note">ordem: empate</span>';
      case 'bloqueada': return '<span class="oc-pill fail" title="' + esc(o.error || '') + '">bloqueada</span>';
      case 'erro': return '<span class="oc-pill fail" title="' + esc(o.error || '') + '">não enviada</span>';
      case 'sem_resultado': return '<span class="oc-pill note">ordem sem resultado</span>';
      default: return '<span class="oc-pill note">ordem aberta</span>';
    }
  }

  function renderFeed() {
    var rows = state.feedRows;
    if (!rows) return;
    var since = state.feedSince;
    var bySignal = {};  // as ordens vêm da mais nova para a mais antiga: fica a última de cada sinal
    (state.painelOrders || []).forEach(function (o) { if (o.signal_id != null && !bySignal[o.signal_id]) bySignal[o.signal_id] = o; });
    var sent = rows.filter(function (r) { var o = bySignal[r.id]; return o && o.status !== 'bloqueada' && o.status !== 'erro'; }).length;
    $('#feed-title').textContent = 'Sinais ' + painelWhen(since);
    $('#feed-count').textContent = rows.length
      ? (state.feedFull ? 'últimos ' : '') + intFmt.format(rows.length) + ' sinais · ' + intFmt.format(sent) + ' viraram ordem' : '';
    var el = $('#feed');
    if (!rows.length) {
      el.innerHTML = '<li class="empty">Nenhum sinal ao vivo ' + (since ? 'nesta sessão' : 'hoje') +
        ' ainda. Com o bot rodando, cada sinal aparece aqui na hora, com o que aconteceu com a ordem.</li>';
      return;
    }
    el.innerHTML = rows.map(function (r) {
      var o = bySignal[r.id];
      var why = o && (o.status === 'bloqueada' || o.status === 'erro') && o.error ? '<span class="down">' + esc(o.error) + '</span> · ' : '';
      return '<li><span class="when">' + fmtTime(r.candle_ts) + '</span>' +
        '<div class="what"><div class="line1">' + dotHtml(r.strategy) + dirHtml(r.direction) + ' <span class="muted small">' + esc(r.asset) + '</span></div>' +
        '<div class="line2">' + why + esc(label(r.strategy)) + ' · ' + esc(r.setup) + '</div></div>' +
        '<div class="right"><span title="Resultado do sinal (com ordem, o da corretora)">' + resHtml(r.result) + '</span>' + brokerNote(r) +
        '<div>' + signalOrderPill(r, o) + '</div></div></li>';
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
    if (!on) setDrawTool(null);
  }

  // ------------------------------------------------------------------ linhas desenhadas por você
  // Horizontal num preço (linha de preço da biblioteca, com o valor no eixo) e vertical num horário (desenhada por
  // cima das velas, com a hora no topo). Ferramentas só no gráfico expandido; as linhas ficam salvas neste navegador,
  // por par, e aparecem também no painel normal. Só desenho: o bot não usa estas linhas para nada.
  var DRAW_KEY = 'botbene-desenhos', DRAW_HIT_PX = 7;
  var DRAW_HINTS = {
    h: 'Clique no preço onde quer a linha horizontal · Esc cancela',
    v: 'Clique na vela onde quer a linha vertical · Esc cancela',
    erase: 'Clique numa linha sua para apagar · Esc cancela'
  };
  state.drawings = loadStored(DRAW_KEY, {});
  state.drawTool = null;
  state.drawLines = [];
  function chartAsset() { return state.chartData && state.chartData.asset; }
  function drawingsOf(asset) { return (asset && state.drawings[asset]) || []; }
  function chartTf() { return (state.chartData && state.chartData.timeframe) || 60; }
  // Coordenada x de um horário, mesmo fora das velas carregadas (linha no futuro ou num buraco do histórico).
  function timeToX(t) {
    var ts = mainChart.timeScale(), x = ts.timeToCoordinate(t);
    if (x != null) return x;
    var bars = candleSeries.data();
    if (!bars.length) return null;
    var lo = 0, hi = bars.length - 1;
    if (t < bars[0].time) hi = 0;
    else while (lo < hi) { var mid = (lo + hi + 1) >> 1; if (bars[mid].time <= t) lo = mid; else hi = mid - 1; }
    var ref = bars[t < bars[0].time ? 0 : lo].time, rx = ts.timeToCoordinate(ref);
    return rx == null ? null : rx + (t - ref) / chartTf() * ts.options().barSpacing;
  }
  // Horário da vela sob um x do gráfico, inclusive no espaço vazio à direita (velas que ainda vão abrir).
  function xToTime(x) {
    var logical = mainChart.timeScale().coordinateToLogical(x), bars = candleSeries.data();
    if (logical == null || !bars.length) return null;
    var i = Math.round(logical), last = bars.length - 1;
    if (i >= 0 && i <= last) return bars[i].time;
    return i > last ? bars[last].time + (i - last) * chartTf() : bars[0].time + i * chartTf();
  }
  var drawPrimitive = {
    chart: null, series: null, request: null,
    attached: function (p) { this.chart = p.chart; this.series = p.series; this.request = p.requestUpdate; },
    detached: function () { this.chart = this.series = this.request = null; },
    updateAllViews: function () {},
    refresh: function () { if (this.request) this.request(); },
    paneViews: function () { return [{ zOrder: function () { return 'top'; }, renderer: function () { return { draw: drawVerticals }; } }]; }
  };
  function drawVerticals(target) {
    var lines = drawingsOf(chartAsset()).filter(function (d) { return d.kind === 'v'; });
    if (!lines.length || !drawPrimitive.chart) return;
    var color = cssVar('--series-1');
    target.useMediaCoordinateSpace(function (scope) {
      var ctx = scope.context, w = scope.mediaSize.width, h = scope.mediaSize.height;
      ctx.lineWidth = 2;
      ctx.font = '11px system-ui, -apple-system, "Segoe UI", sans-serif';
      lines.forEach(function (d) {
        var x = timeToX(d.time);
        if (x == null || x < 0 || x > w) return;
        x = Math.round(x);
        ctx.strokeStyle = color;
        ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x, h); ctx.stroke();
        var label = fmtTime(d.time), tw = ctx.measureText(label).width;
        var lx = Math.max(0, Math.min(w - tw - 8, x - tw / 2 - 4));
        ctx.fillStyle = color;
        ctx.fillRect(lx, 2, tw + 8, 16);
        ctx.fillStyle = '#fff';
        ctx.fillText(label, lx + 4, 14);
      });
    });
  }
  function renderDrawings() {
    if (!candleSeries) return;
    state.drawLines.forEach(function (pl) { candleSeries.removePriceLine(pl); });
    var color = cssVar('--series-1');
    state.drawLines = drawingsOf(chartAsset()).filter(function (d) { return d.kind === 'h'; }).map(function (d) {
      return candleSeries.createPriceLine({ price: d.price, color: color, lineWidth: 2, lineStyle: LWC.LineStyle.Solid,
        axisLabelVisible: true, title: '' });
    });
    drawPrimitive.refresh();
  }
  function setDrawTool(tool) {
    state.drawTool = tool || null;
    document.querySelectorAll('#draw-tools [data-tool]').forEach(function (b) {
      if (b.dataset.tool !== 'clear') b.setAttribute('aria-pressed', b.dataset.tool === state.drawTool ? 'true' : 'false');
    });
    $('#chart-box').classList.toggle('drawing', !!state.drawTool);
    var hint = $('#draw-hint');
    hint.hidden = !state.drawTool;
    hint.textContent = state.drawTool ? DRAW_HINTS[state.drawTool] : '';
  }
  function nearestDrawing(list, point) {
    var best = -1, bestDist = DRAW_HIT_PX + 1;
    list.forEach(function (d, i) {
      var c = d.kind === 'h' ? candleSeries.priceToCoordinate(d.price) : timeToX(d.time);
      if (c == null) return;
      var dist = Math.abs(c - (d.kind === 'h' ? point.y : point.x));
      if (dist < bestDist) { best = i; bestDist = dist; }
    });
    return best;
  }
  function onChartClick(param) {
    var tool = state.drawTool, asset = chartAsset();
    if (!tool || !param.point || !asset) return;
    var list = state.drawings[asset] || [];
    if (tool === 'h') {
      var price = candleSeries.coordinateToPrice(param.point.y);
      if (price == null) return;
      list.push({ kind: 'h', price: Number(price.toFixed(precision(price))) });
    } else if (tool === 'v') {
      var t = param.time != null ? param.time : xToTime(param.point.x);
      if (t == null) return;
      list.push({ kind: 'v', time: t });
    } else {
      var hit = nearestDrawing(list, param.point);
      if (hit < 0) return;  // errou a linha: a borracha continua na mão
      list.splice(hit, 1);
    }
    if (list.length) state.drawings[asset] = list; else delete state.drawings[asset];
    saveStored(DRAW_KEY, state.drawings);
    renderDrawings();
    setDrawTool(null);
  }
  function clearDrawings() {
    var asset = chartAsset();
    setDrawTool(null);
    if (!drawingsOf(asset).length) return;
    if (!window.confirm('Apagar todas as suas linhas de ' + asset + '?')) return;
    delete state.drawings[asset];
    saveStored(DRAW_KEY, state.drawings);
    renderDrawings();
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
    renderDrawings();  // as linhas são por par: troca junto com o gráfico
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
    if (sel && sel.asset === asset && candle.time === sel.target_ts) {  // pedido aberto deste par: preço até o gatilho ao vivo
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
    updateChartMenu();
  }
  // Resumo no botão do menu "Marcações no gráfico": quantas estratégias aparecem e as opções ligadas.
  function updateChartMenu() {
    var el = $('#cm-count');
    if (!el) return;
    var names = shownStrategies(), on = names.filter(function (n) { return state.visible[n]; }).length;
    el.textContent = on + ' de ' + names.length + (state.showBacktest ? ' · backtest' : '') + (state.showReading ? ' · leitura' : '');
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
    // As ordens do mesmo período, para a coluna "Ordem": o que aconteceu com a ordem de cada sinal.
    var signalsReq = api('/api/signals?' + q.join('&'));
    var ordersReq = api('/api/orders?period=' + state.ePeriod + '&limit=2000').catch(function () { return null; });
    Promise.all([signalsReq, ordersReq]).then(function (got) {
      var rows = got[0], orders = got[1];
      var bySignal = {};
      (orders || []).forEach(function (o) { if (o.signal_id != null && !bySignal[o.signal_id]) bySignal[o.signal_id] = o; });
      // Com 2000 ordens a lista pode ter cortado as mais antigas: antes da mais antiga que veio, não dá para saber.
      var known = orders ? (orders.length >= 2000 ? orders[orders.length - 1].requested_at : 0) : Infinity;
      // Filtro "Ordem": virou ordem, foi bloqueada ou recusada, ou não teve ordem. Nos sinais do backtest (e nos antigos
      // demais para a lista de ordens) não dá para saber: ficam de fora quando o filtro está ligado.
      var want = $('#e-order').value;
      if (want) {
        rows = rows.filter(function (r) {
          if (r.origin !== 'ao_vivo' || r.entry_ts < known) return false;
          var o = bySignal[r.id];
          var kind = !o ? 'none' : o.status === 'bloqueada' || o.status === 'erro' ? 'blocked' : 'sent';
          return kind === want;
        });
      }
      var sent = 0;
      var w = 0, l = 0, e = 0, p = 0, profit = 0;
      rows.forEach(function (r) {
        if (r.result === 'win') w++; else if (r.result === 'loss') l++; else if (r.result === 'empate') e++; else if (r.result === 'pendente') p++;
        profit += r.profit || 0;
        var o = bySignal[r.id];
        if (o && o.status !== 'bloqueada' && o.status !== 'erro') sent++;
      });
      function pl(n, one, many) { return '<span><strong>' + intFmt.format(n) + '</strong> ' + (n === 1 ? one : many) + '</span>'; }
      $('#e-summary').innerHTML = rows.length
        ? pl(rows.length, 'sinal', 'sinais') + pl(w, 'win', 'wins') + pl(l, 'loss', 'losses') + pl(e, 'empate', 'empates') + pl(p, 'pendente', 'pendentes') +
          '<span>Acerto <strong>' + (w + l ? fmtPct(w / (w + l)) : '—') + '</strong></span><span>Resultado <strong class="' + signClass(profit) + '">' + fmtUnits(profit) + '</strong> entradas</span>' +
          (orders ? pl(sent, 'virou ordem', 'viraram ordem') : '')
        : '';
      var body = $('#e-body');
      if (!rows.length) {
        body.innerHTML = '<tr><td colspan="11" class="muted">Nenhuma entrada com esses filtros' +
          (state.ePeriod === 'hoje' ? ' hoje. Com o bot rodando, as entradas ao vivo aparecem aqui.' : '.') + '</td></tr>';
        return;
      }
      body.innerHTML = rows.map(function (r) {
        return '<tr><td class="num">' + fmtDateTime(r.candle_ts) + '</td><td>' + esc(r.asset) + '</td><td>' + stratHtml(r.strategy) +
          '</td><td>' + dirHtml(r.direction) + '</td><td>' + esc(r.setup) + '</td><td class="num">' + fmtPrice(r.entry_price) +
          '</td><td class="num">' + fmtPrice(r.exit_price) + '</td><td>' + resHtml(r.result) + brokerNote(r) + '</td><td class="num ' + signClass(r.profit) + '">' +
          (r.result === 'pendente' || r.result === 'cancelado' ? '—' : fmtUnits(r.profit)) + '</td><td>' +
          (r.origin !== 'ao_vivo' || r.entry_ts < known ? '<span class="muted">—</span>' : signalOrderPill(r, bySignal[r.id])) +
          '</td><td>' + originText(r.origin) + '</td></tr>';
      }).join('');
    }).catch(function (err) { $('#e-body').innerHTML = '<tr><td colspan="11">Erro: ' + esc(err.message) + '</td></tr>'; });
  }

  // ------------------------------------------------------------------ DESEMPENHO
  // Só ordens enviadas à corretora, em dinheiro. Demo e real não se somam: a conta começa na escolhida na barra lateral.
  function refreshDesempenho() {
    if (!state.dAccountTouched && state.chosenAccount) $('#d-account').value = state.chosenAccount;
    var strategy = $('#d-strategy').value, asset = $('#d-asset').value, account = $('#d-account').value;
    var q = ['period=' + state.dPeriod, 'account=' + encodeURIComponent(account)];
    if (strategy) q.push('strategy=' + encodeURIComponent(strategy));
    if (asset) q.push('asset=' + encodeURIComponent(asset));
    api('/api/stats/orders?' + q.join('&')).then(function (st) {
      $('#d-note').hidden = true;
      $('#d-profit-label').textContent = 'Resultado ' + PERIOD_TEXT[state.dPeriod];
      renderKpis('d', st, true);
      $('#d-profit-sub').textContent = 'em dinheiro · só ordens com resultado' + (st.staked ? ' · apostado ' + fmtMoney(st.staked) : '');
      var extra = [[st.open, 'aberta', 'abertas'], [st.not_sent, 'não enviada', 'não enviadas'], [st.no_result, 'sem resultado', 'sem resultado']]
        .filter(function (x) { return x[0]; }).map(function (x) { return intFmt.format(x[0]) + ' ' + (x[0] === 1 ? x[1] : x[2]); });
      $('#d-n-extra').textContent = extra.length ? 'fora da conta: ' + extra.join(' · ') : '';
      var stratSel = $('#d-strategy'), stratNow = stratSel.value;  // só as que têm ordem nesta conta
      stratSel.innerHTML = '<option value="">Todas</option>' + st.strategies.map(function (x) {
        return '<option value="' + esc(x.name) + '"' + (x.name === stratNow ? ' selected' : '') + '>' + esc(x.label) + '</option>';
      }).join('');
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
      var types = st.by_type || [];  // só aparece quando já houve ordem na digital
      $('#d-types-wrap').hidden = !types.some(function (g) { return g.key === 'Digital'; });
      $('#d-types').innerHTML = types.map(function (g) { return groupRow('<td>' + esc(g.key) + '</td>', g, be); }).join('');
      var sel = $('#d-asset'), current = sel.value;
      sel.innerHTML = '<option value="">Todos</option>' + st.assets.map(function (a) {
        return '<option value="' + esc(a) + '"' + (a === current ? ' selected' : '') + '>' + esc(a) + '</option>';
      }).join('');
    }).catch(function (err) {
      var note = $('#d-note');
      note.hidden = false;
      note.textContent = /404|Not Found/i.test(err.message)
        ? 'O servidor ainda está na versão antiga: feche pelo "Desligar BotBene" e abra de novo para ver o desempenho das ordens.'
        : 'Não deu para carregar o desempenho: ' + err.message;
    });
  }

  function groupRow(cells, g, be) {
    var good = g.n >= MIN_SAMPLE && g.ci_low != null && be != null && g.ci_low > be;
    return '<tr' + (good ? ' class="good-row" title="Intervalo de confiança inteiro acima do mínimo para empatar"' : '') + '>' + cells +
      '<td class="num">' + intFmt.format(g.n) + '</td><td class="num">' + fmtPct(g.winrate) + '</td><td class="num">' +
      (g.n ? fmtPct(g.ci_low) + '–' + fmtPct(g.ci_high) : '—') + '</td><td class="num ' + signClass(g.profit) + '">' + fmtMoney(g.profit, true) + '</td></tr>';
  }

  function renderCols(tl) {
    var el = $('#d-cols');
    var any = tl.some(function (b) { return b.n + b.draws > 0; });
    if (!tl.length || !any) { el.innerHTML = '<div class="empty-state">Nenhuma ordem no período.</div>'; return; }
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
      var val = function (h) { return '<span class="col-val" style="--h:' + h.toFixed(1) + 'px">' + fmtMoney(b.profit, true) + '</span>'; };
      return '<div class="col" tabindex="0" data-i="' + i + '">' +
        '<div class="col-pos" style="height:' + posH + 'px">' + (ph ? '<div class="col-bar pos" style="height:' + ph.toFixed(1) + 'px"></div>' : '') + (i === iMax ? val(ph) : '') + '</div>' +
        '<div class="col-neg" style="height:' + negH + 'px">' + (nh ? '<div class="col-bar neg" style="height:' + nh.toFixed(1) + 'px"></div>' : '') + (i === iMin ? val(nh) : '') + '</div>' +
        '</div>';
    }).join('') + '</div>';
    html += '<div class="cols-axis">' + tl.map(function (b, i) { return '<span>' + (i % step === 0 ? esc(b.label) : '') + '</span>'; }).join('') + '</div>';
    el.innerHTML = html;
    Array.prototype.forEach.call(el.querySelectorAll('.col'), function (c) {
      var b = tl[parseInt(c.dataset.i, 10)];
      tipData.set(c, '<div class="t-title">' + esc(b.label) + '</div>Resultado <strong>' + fmtMoney(b.profit, true) + '</strong><br>' +
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
    if (!groups.length) { el.innerHTML = '<div class="empty-state">Nenhuma ordem no período.</div>'; return; }
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
        'Mínimo para empatar ' + fmtPct(g.breakeven) + '<br>Resultado ' + fmtMoney(g.profit, true));
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
    retracao_comando_v2: 'nova (08/11) · igual à v1, mas pula pernada esticada (3ª vela seguida da mesma cor, pág. 131) · melhor que a v1 nos 4 testes, ainda no empate fora da amostra · em validação',
    retracao_comando: '~54% sozinha · é a base do score',
    ldp_apostila: '~51% na pesquisa · sem vantagem · recomendado desligar',
    retracao_lote: '~50% na pesquisa e ao vivo · sem vantagem · recomendado desligar',
    reversao_forca: '~51% na pesquisa · entra na abertura (cara ou coroa) · só observar',
    reversao_indecisao: '~51% na pesquisa · sem vantagem · recomendado desligar',
    esticao: 'nova (08/11), dos dados · depois de vela grande, o preço dispara 1,5 ATR nos 10 s iniciais e entra contra · 73% no estudo, 44-61% na conferência (poucas entradas) · vale nos pares normais, não no OTC · só observar',
    deeplob_iq: 'nova (08/11) · rede DeepLOB lendo as últimas 100 velas de 5 s · reprovada no estudo: 48,2% em 1.787 nos pares normais; OTC sem sinal (fica em silêncio) · observando ao vivo com limiar 0,52 · só observar',
    bb_rci: 'nova (09/11) · Bollinger 20/2 tocada com RCI 9 em ±80, entra contra no início da vela seguinte · cara ou coroa no estudo: 50,0% (33.841) nos pares normais e 50,1% (33.388) no OTC; martingale aumentou o prejuízo · dispara ~1 vez a cada 8 min por par',
    bb_rci_v2: 'nova (09/11) · a v1 só quando o Gator está dormindo, o MACD virando a favor e, nos pares normais, a onda do Weis Wave mais fraca que a anterior (no OTC não há volume) · medindo no ao vivo: vira Operar se fizer 5 pontos a mais que a v1 em 150+ entradas · só observar'
  };
  var STATE_LABELS = { off: 'Desligada', observe: 'Observar', operate: 'Operar' };
  function renderStrategyChoices(cfg) {
    $('#cfg-strats').innerHTML = (cfg.strategy_names || []).map(function (name) {
      var current = (cfg.strategies && cfg.strategies[name]) || 'off';
      var note = STRATEGY_NOTES[name];
      return '<tr><th scope="row">' + dotHtml(name) + esc(label(name)) + (note ? '<div class="muted small">' + esc(note) + '</div>' : '') + '</th>' +
        Object.keys(STATE_LABELS).map(function (st) {
          var locked = st === 'operate' && OBSERVE_ONLY.indexOf(name) >= 0;
          return '<td><input type="radio" name="cfg-strat-' + esc(name) + '" value="' + st + '"' + (st === current ? ' checked' : '') +
            (locked ? ' disabled title="Em validação: só pode observar"' : '') +
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
    $('#cfg-max-cycles-row').hidden = cfg.max_lost_cycles === undefined;  // servidor antigo: sem stop de ciclo
    $('#cfg-max-lost-cycles').value = cfg.max_lost_cycles == null ? '' : cfg.max_lost_cycles;
    $('#cfg-auto-market-row').hidden = cfg.auto_market == null;  // servidor antigo: sem a opção
    $('#cfg-auto-market').checked = cfg.auto_market === true;
    $('#cfg-option-row').hidden = cfg.option_type == null;
    Array.prototype.forEach.call(document.querySelectorAll('input[name="cfg-option"]'), function (r) { r.checked = r.value === cfg.option_type; });
    $('#cfg-max-assets').textContent = maxAssets();
    renderGaleStrategies(cfg);
    renderGaleExample();
    setResult('#cfg-test-result', null, '');
  }

  function renderGaleStrategies(cfg) {
    var row = $('#cfg-gale-strats-row');
    row.hidden = cfg.gale_strategies == null;  // servidor antigo: o martingale vale para todas
    if (row.hidden) return;
    $('#cfg-gale-strats').innerHTML = (cfg.strategy_names || []).map(function (name) {
      var on = cfg.gale_strategies.indexOf(name) >= 0;
      return '<label><input type="checkbox" name="cfg-gale-strat" value="' + esc(name) + '"' + (on ? ' checked' : '') + '>' +
        '<span>' + dotHtml(name) + esc(label(name)) + '</span></label>';
    }).join('');
  }
  function galeStake(base, cycleLoss, payout) { return Math.ceil((cycleLoss + base * payout) / payout * 100) / 100; }
  function renderGaleExample() {
    var on = $('#cfg-martingale').checked;
    $('#cfg-gale-levels').disabled = !on;
    $('#cfg-max-lost-cycles').disabled = !on;
    Array.prototype.forEach.call(document.querySelectorAll('input[name="cfg-gale-strat"]'), function (c) { c.disabled = !on; });
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
  function maxAssets() { return (state.config && state.config.max_assets) || 8; }
  function togglePair(p) {
    var i = state.cfgPairs.indexOf(p);
    if (i >= 0) state.cfgPairs.splice(i, 1);
    else if (state.cfgPairs.length >= maxAssets()) { setResult('#cfg-save-result', false, 'No máximo ' + maxAssets() + ' pares ao mesmo tempo.'); return; }
    else state.cfgPairs.push(p);
    renderPairChips();
  }
  // Sugestões ao digitar "outro par": todos os pares da IQ que têm binária ou digital.
  function fillPairSuggestions() {
    var el = $('#cfg-asset-list');
    if (!el) return;
    var html = state.pairList.filter(function (p) { return p.binary !== false || p.digital; })
      .map(function (p) { return p.asset; }).sort().map(function (a) { return '<option value="' + esc(a) + '">'; }).join('');
    if (el.dataset.html !== html) { el.innerHTML = html; el.dataset.html = html; }
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
    if (!$('#cfg-auto-market-row').hidden) patch.auto_market = $('#cfg-auto-market').checked;
    if (!$('#cfg-max-cycles-row').hidden) patch.max_lost_cycles = numField('#cfg-max-lost-cycles');
    if (!$('#cfg-gale-strats-row').hidden) {
      patch.gale_strategies = Array.prototype.map.call(document.querySelectorAll('input[name="cfg-gale-strat"]:checked'),
        function (c) { return c.value; });
    }
    var opt = document.querySelector('input[name="cfg-option"]:checked');
    if (!$('#cfg-option-row').hidden && opt) patch.option_type = opt.value;
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
        if (state.status && e.risk) { state.status.risk = e.risk; renderGaleChip(state.status); }  // aviso do ciclo na hora
        if (state.status) { renderApprovals(state.status); renderArmed(state.status); }  // cartão de resultado na hora
        if (state.page === 'painel') refreshOrders();
        if (e.order && state.chartData && e.order.asset === state.chartData.asset) refreshChart();  // marca de ENTRADA na hora
        renderManual();
        if (['win', 'loss', 'empate'].indexOf(e.order && e.order.status) >= 0) refreshAccount();  // saldo mudou
      }
      else if (e.type === 'signal' || e.type === 'result') { if (state.page === 'painel') refreshTodaySoon(); }
      else if (e.type === 'reload') { refreshSoon(); refreshPairs(); }  // pares carregados ou trocados: aberto/fechado e payout
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
      var arrow = e.target.closest('.pt-arrow');
      if (arrow) {
        var sc = $('#pt-scroll');
        sc.scrollBy({ left: Number(arrow.dataset.scroll) * Math.max(120, sc.clientWidth * 0.7), behavior: 'smooth' });
        return;
      }
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
    $('#pp-market').addEventListener('click', function (e) {
      var b = e.target.closest('[data-market]');
      if (!b) return;
      state.pickerMarket = b.dataset.market;
      renderPickerCats();
      renderPicker();
    });
    $('#pp-type').addEventListener('click', function (e) {
      var b = e.target.closest('[data-type]');
      if (!b) return;
      state.pickerType = b.dataset.type;
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
    $('#m-kind').addEventListener('click', function (e) {
      var b = e.target.closest('button[data-kind]');
      if (!b || b.disabled) return;
      state.manualKind = b.dataset.kind;
      saveStored('botbene-manual-tipo', state.manualKind);
      state.manualError = null;
      renderManual();
    });
    ['pointerdown', 'wheel'].forEach(function (ev) {  // mexeu no gráfico: está analisando este par
      $('#chart-box').addEventListener(ev, function () { state.lastChartTouch = Date.now(); }, { passive: true });
    });
    $('#m-call').addEventListener('click', function () { sendManual('call'); });
    $('#m-put').addEventListener('click', function () { sendManual('put'); });
    $('#approvals').addEventListener('click', function (e) {
      var btn = e.target.closest('button[data-act]');
      if (btn) { decideApproval(btn.dataset.id, btn.dataset.act, btn); return; }
      var go = e.target.closest('[data-goto]');
      if (go) { state.lastChartTouch = 0; goToChart(go.dataset.goto); return; }
      var stay = e.target.closest('[data-stay]');
      if (stay) { state.focusAsk[stay.dataset.stay] = 'ficou'; renderApprovals(state.status); }
    });
    // Configuração → Sons: volume (só neste computador) e botões para ouvir cada aviso.
    renderVolume();
    $('#snd-volume').addEventListener('input', function () {
      state.soundVolume = Number(this.value) / 100;
      saveStored('botbene-volume', state.soundVolume);
      renderVolume();
    });
    $('#snd-volume').addEventListener('change', function () { unlockAudio(); playSound('card'); });
    Array.prototype.forEach.call(document.querySelectorAll('button[data-sound]'), function (b) {
      b.addEventListener('click', function () { unlockAudio(); playSound(b.dataset.sound); });
    });
    $('#snd-demo').addEventListener('click', showDemoApproval);
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
    $('#draw-tools').addEventListener('click', function (e) {
      var b = e.target.closest('button');
      if (!b) return;
      if (b.dataset.tool === 'clear') clearDrawings();
      else setDrawTool(state.drawTool === b.dataset.tool ? null : b.dataset.tool);
    });
    $('#market-clock').addEventListener('click', function (e) {
      var b = e.target.closest('[data-mc]');
      if (!b) return;
      state.marketClockOpen = b.dataset.mc === '1';
      saveStored('botbene-mercado-detalhes', state.marketClockOpen);
      renderMarketClock();
    });
    var chartMenu = $('#chart-menu');
    chartMenu.addEventListener('click', function () { setTimeout(updateChartMenu, 0); });  // depois de cada opção mudar
    chartMenu.addEventListener('change', function () { setTimeout(updateChartMenu, 0); });
    document.addEventListener('click', function (e) {  // clique fora fecha o menu
      if (chartMenu.open && !chartMenu.contains(e.target)) chartMenu.open = false;
    });
    window.addEventListener('resize', updatePairArrows);
    document.addEventListener('keydown', function (e) {
      if (e.key !== 'Escape') return;
      if (chartMenu.open) { chartMenu.open = false; return; }
      if (state.drawTool) { setDrawTool(null); return; }  // primeiro solta a ferramenta de desenho
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
    $('#p-scope').addEventListener('change', function (e) {
      if (e.target.id === 'p-cycle') {
        state.byCycle = e.target.checked;
        saveStored('botbene-painel-ciclo', state.byCycle);
        renderOrderStats();
        return;
      }
      if (e.target.id !== 'p-session') return;
      state.sessionOnly = e.target.checked;
      saveStored('botbene-painel-sessao', state.sessionOnly);
      refreshToday();
      refreshOrders();
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
    ['strategy', 'result', 'origin', 'order'].forEach(function (k) { $('#e-' + k).addEventListener('change', refreshEntradas); });
    $('#d-account').addEventListener('change', function () { state.dAccountTouched = true; });  // antes de atualizar a tela
    ['strategy', 'asset', 'account'].forEach(function (k) { $('#d-' + k).addEventListener('change', refreshDesempenho); });

    api('/api/strategies').then(function (list) {
      list.forEach(function (s) { LABELS[s.name] = s.label; });
      var opts = '<option value="">Todas</option>' + list.map(function (s) {
        return '<option value="' + esc(s.name) + '">' + esc(s.label) + '</option>';
      }).join('');
      $('#e-strategy').innerHTML = opts;
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
    setInterval(function () { updateCountdowns(); updateApprovalClocks(); updateManualClock(); renderMarketClock(); }, 1000);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
