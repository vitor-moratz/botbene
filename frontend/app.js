/* BotBene · painel (JavaScript simples, sem build). Fala com o backend em /api e /ws/live. */
(function () {
  'use strict';

  // Ordem fixa: a cor segue o script, nunca a posição na lista.
  var STRATEGY_ORDER = ['ldp_v13', 'ldp_v13_linhas', 'wiki_pro_v21', 'ldp_apostila', 'retracao_comando'];
  var LABELS = {
    ldp_v13: 'LDP v1.3', ldp_v13_linhas: 'LDP v1.3 + regra das linhas', wiki_pro_v21: 'WIKI PRO V2.1',
    ldp_apostila: 'Apostila · marcações', retracao_comando: 'Apostila · retração no comando'
  };
  var TRIGGER_LABELS = { retracao: 'Retração', reversao: 'Reversão', throwback: 'Throwback', comando: 'Retração no comando' };
  var CONF_LABELS = {
    gatilho: 'gatilho', forca: 'marcação forte', contexto: 'nova alta/baixa + nova posição',
    espaco: 'espaço até a barreira', tendencia: 'tendência EMA'
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
    rodando: { icon: '●', text: 'Rodando' }, erro: { icon: '✗', text: 'Erro' }
  };
  var PAGE_TITLES = { painel: 'Painel', entradas: 'Entradas', desempenho: 'Desempenho', config: 'Configuração' };
  var PAGES = ['painel', 'entradas', 'desempenho', 'config'];
  var TF_TEXT = { 60: '1 minuto', 120: '2 minutos', 300: '5 minutos' };
  var MODE_TEXT = {
    sinais: 'Modo: só sinais (sem ordens)', aprovacao: 'Modo: aprovação',
    automatico: 'Modo: automático', automatico_veto: 'Modo: automático com veto'
  };
  var REAL_WARNING = 'CONTA REAL: as ordens passam a usar DINHEIRO DE VERDADE.\n\n' +
    'A retração no comando ainda não tem vantagem comprovada: em dados que ela nunca viu ficou em ~54%, ' +
    'igual ao empate (54,3%). A recomendação é continuar na demo até ~200 entradas ao vivo.\n\n' +
    'Para usar a conta real mesmo assim, digite REAL:';
  // Na IQ, a binária dos pares normais é o instrumento com sufixo "-op".
  var DEFAULT_PAIRS = ['EURUSD-op', 'GBPUSD-op', 'USDJPY-op', 'AUDUSD-op', 'EURJPY-op', 'EURGBP-op', 'AUDJPY-op', 'NZDUSD-op'];
  var OPEN_APPROVAL = ['aguardando', 'aprovado', 'disparou'];
  var APPROVAL_STATE = {
    aguardando: { cls: 'warn', icon: '●', text: 'Aguardando sua decisão' },
    aprovado: { cls: 'ok', icon: '✓', text: 'Aprovado: a ordem sai quando o gatilho disparar' },
    disparou: { cls: 'warn', icon: '▲', text: 'O gatilho disparou! Aprovar agora entra no preço do momento' },
    'ordem enviada': { cls: 'ok', icon: '✓', text: 'Ordem enviada na conta demo' },
    rejeitado: { cls: '', icon: '—', text: 'Rejeitado: sem ordem' },
    'não disparou': { cls: '', icon: '—', text: 'O recuo não veio nos 15 s: sem ordem (é o normal, ~92% dos pedidos terminam assim)' },
    'expirou sem resposta': { cls: 'bad', icon: '✗', text: 'A janela fechou sem resposta: sem ordem' },
    bloqueada: { cls: 'bad', icon: '✗', text: 'Bloqueada pela gestão de risco' },
    'exemplo concluído': { cls: 'ok', icon: '✓', text: 'Exemplo: aprovado e o preço tocou o gatilho. Num pedido de verdade, a ordem iria agora para a conta demo; aqui nada foi enviado' }
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
    var i = STRATEGY_ORDER.indexOf(name);
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
    showComparison: false, uiVersion: null, ordersById: {}, resolvedAt: {}, apInit: false
  };
  try { state.showComparison = localStorage.getItem('botbene-comparacao') === '1'; } catch (e) { /* sem armazenamento */ }
  // Estratégias principais = as que pedem aprovação na Configuração; o resto é comparação.
  function mainStrategies() {
    var list = state.config && state.config.order_strategies && state.config.order_strategies.length
      ? state.config.order_strategies : ['retracao_comando'];
    return list.slice();
  }
  function isMain(name) { return mainStrategies().indexOf(name) >= 0; }
  function scopeQuery() {
    var all = state.showComparison && comparisonOn();
    return all ? '' : '&strategy=' + encodeURIComponent(mainStrategies().join(','));
  }
  function syncVisible() {
    STRATEGY_ORDER.forEach(function (n) { state.visible[n] = state.showComparison || isMain(n); });
  }
  syncVisible();
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
    // Alta vazada, baixa preenchida: a direção não depende só da cor.
    return { upColor: 'rgba(0,0,0,0)', downColor: down, borderUpColor: up, borderDownColor: down, wickUpColor: up, wickDownColor: down };
  }
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
  function initCharts() {
    if (!LWC) {
      $('#chart').innerHTML = '<p class="empty-state">Não foi possível carregar a biblioteca do gráfico (precisa de internet).</p>';
      return;
    }
    mainChart = makeChart($('#chart'));
    candleSeries = mainChart.addCandlestickSeries(candleColors());
    var lineOpts = { lineWidth: 1, lineType: LWC.LineType.WithSteps, priceLineVisible: false, lastValueVisible: false, crosshairMarkerVisible: false };
    buySeries = mainChart.addLineSeries(Object.assign({ color: cssVar('--line-buy') }, lineOpts));
    sellSeries = mainChart.addLineSeries(Object.assign({ color: cssVar('--line-sell') }, lineOpts));
    mainChart.subscribeCrosshairMove(onCrosshair);

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
    if (state.abChart) { state.abChart.applyOptions(themeOptions()); state.abSeries.applyOptions(candleColors()); }
    if (state.chartData) renderChart(state.chartData);
    if (state.page === 'desempenho') refreshDesempenho();
  }

  // ------------------------------------------------------------------ status e controle do bot
  function renderStatus(s) {
    state.status = s;
    if (s.server_time && s.status === 'rodando') state.clockOffset = s.server_time - Date.now() / 1000;
    var info = STATUS_INFO[s.status] || { icon: '?', text: s.status };
    var chip = $('#status-chip');
    chip.dataset.status = s.status;
    chip.querySelector('.status-icon').textContent = info.icon;
    chip.querySelector('.status-text').textContent = info.text;
    updateStatusSub();
    if (s.chosen_account && s.chosen_account !== state.chosenAccount) { state.chosenAccount = s.chosen_account; renderAccount(state.accountInfo); }
    $('#mode-text').textContent = MODE_TEXT[s.mode] || 'Modo: só sinais (sem ordens)';

    var busy = s.status === 'rodando' || s.status === 'conectando';
    var btn = $('#btn-toggle');
    btn.textContent = busy ? 'Parar bot' : 'Iniciar bot';
    btn.classList.toggle('stop', busy);
    btn.disabled = false;
    renderToolbarAssets();

    if (s.status === 'erro' && s.error) showBanner(s.error);
    else if (state.connected) hideBanner();

    var price = s.forming ? s.forming.close : (s.last_candle ? s.last_candle.close : null);
    if (price != null) $('#p-price').textContent = fmtPrice(price);
    if (s.payout) $('#p-be-sub').textContent = 'payout de ' + fmtPct(s.payout) + (s.asset ? ' no ' + s.asset : '');
    renderFocus(s);
    renderArmed(s);
    renderApprovals(s);
    renderRisk(s.risk);
  }

  function renderToolbarAssets() {
    var s = state.status, cfg = state.config;
    var busy = s && (s.status === 'rodando' || s.status === 'conectando');
    var assets = busy && s.assets && s.assets.length ? s.assets.map(function (a) { return a.asset; }) : (cfg ? cfg.assets : []);
    var tf = busy ? s.timeframe : (cfg ? cfg.timeframe : 60);
    $('#assets-text').textContent = assets.length ? assets.join(' · ') : '—';
    $('#tf-text').textContent = TF_TEXT[tf] || (tf / 60) + ' min';
  }

  function renderFocus(s) {
    var field = $('#focus-field');
    var running = s.status === 'rodando' && s.assets && s.assets.length > 1;
    field.hidden = !running;
    if (!running) return;
    var sel = $('#focus-asset');
    var opts = s.assets.map(function (a) {
      var extra = a.error ? ' (fora: ' + a.error.slice(0, 30) + ')'
        : (a.tradable === false ? ' · fechado p/ binária' : '') + (a.armed ? ' · ' + a.armed + ' armado' : '');
      return '<option value="' + esc(a.asset) + '"' + (a.error ? ' disabled' : '') + '>' + esc(a.asset + extra) + '</option>';
    }).join('');
    if (sel.dataset.opts !== opts) { sel.innerHTML = opts; sel.dataset.opts = opts; }
    if (document.activeElement !== sel) sel.value = s.asset;
  }

  // ------------------------------------------------------------------ próxima entrada (apostila)
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
      html = '<p class="armed-none">Nenhuma entrada armada para esta vela' + (multi ? ' em nenhum par' : '') + '.</p>' +
        (reasons.length ? (multi ? '<div class="muted small">Por que não armou no ' + esc(s.asset) + ':</div>' : '') +
          '<ul class="reasons">' + reasons.map(function (r) { return '<li>' + esc(r) + '</li>'; }).join('') + '</ul>' : '');
    } else {
      html = list.map(function (a) {
        var head = '<div class="armed" style="border-left-color:' + strategyColor(a.strategy) + '">' +
          '<div class="armed-top">' + dirHtml(a.direction) + (multi ? '<strong>' + esc(a.asset) + '</strong>' : '') +
            '<span>' + esc(TRIGGER_LABELS[a.trigger] || a.trigger) + '</span>' +
            '<span class="countdown" data-start="' + a.target_ts + '" data-end="' + a.window_end + '"></span></div>';
        if (a.strategy === 'retracao_comando') {
          return head +
            '<div class="armed-level">Gatilho <strong>' + fmtPrice(a.level_price) + '</strong> <span class="muted">· ' +
              esc(a.level_sources[0] || '') + ' a partir da abertura</span></div>' +
            '<div class="muted small">A vela anterior fechou forte. Entra ' + (a.direction === 'call' ? 'CALL' : 'PUT') +
              ' se a vela das ' + fmtTime(a.target_ts) + ' recuar até o gatilho nos primeiros ' + a.window_seconds + ' s.</div>' +
          '</div>';
        }
        var conf = Object.keys(CONF_LABELS).map(function (k) {
          return '<span class="chip ' + (a.confluences[k] ? 'ok' : 'no') + '">' + CONF_LABELS[k] + '</span>';
        }).join('');
        return head +
          '<div class="armed-level">Marcação <strong>' + fmtPrice(a.level_price) + '</strong> <span class="muted">· força ' + a.level_strength +
            ' · ' + esc(a.level_sources.slice(0, 2).map(sourceLabel).join(' · ')) + '</span></div>' +
          '<div class="armed-conf">' + conf + '</div>' +
          '<div class="muted small">' + esc(LABELS[a.strategy] || '') + ': ' + a.score + ' confluências. Entra se o preço tocar a marcação nos primeiros ' +
            a.window_seconds + ' s da vela das ' + fmtTime(a.target_ts) + '.</div>' +
        '</div>';
      }).join('');
    }
    // Com ordens ligadas: cada pedido com um selo claro (ordem enviada / sem ordem / não enviada).
    var closed = (s.approvals || []).filter(function (a) { return !isOpenApproval(a) && !a.demo; }).slice().reverse();
    var log = s.armed_log || [];
    if (closed.length) {
      html += '<div class="armed-log"><div class="muted">Últimos pedidos</div>' + closed.slice(0, 8).map(function (a) {
        var oc = approvalOutcome(a);
        var pill = oc.kind === 'sent' ? 'Enviada' : oc.kind === 'fail' ? 'Não enviada' : 'Sem ordem';
        var res = oc.kind === 'sent' && oc.result ? '<span class="oc-res ' + oc.result.cls + '">' + esc(shortResult(oc.result.text)) + '</span>' : '';
        return '<div class="row" title="' + esc(oc.title + ': ' + oc.reason) + '"><span class="when">' + fmtTime(a.target_ts) + '</span>' +
          dirHtml(a.direction) + '<span class="oc-asset">' + esc(a.asset) + '</span>' +
          '<span class="oc-side"><span class="oc-pill ' + oc.kind + '">' + pill + '</span>' + res + '</span></div>';
      }).join('') + '<div class="muted small">Passe o mouse para ver o motivo.</div></div>';
    } else if (log.length) {
      html += '<div class="armed-log"><div class="muted">Últimos setups armados' + (s.mode === 'sinais' ? ' · modo só sinais: nenhuma ordem é enviada' : '') +
        '</div>' + log.slice(0, 6).map(function (l) {
        return '<div class="row"><span class="when">' + fmtTime(l.target_ts) + '</span>' + dotHtml(l.strategy) + dirHtml(l.direction) +
          (multi ? '<span>' + esc(l.asset) + '</span>' : '') + '<span>' + esc(l.outcome) + '</span></div>';
      }).join('') + '</div>';
    }
    el.innerHTML = html;
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
      'não disparou': 'o preço não chegou ao gatilho nos 15 s. É o normal: ~92% dos pedidos terminam assim',
      'rejeitado': 'você rejeitou', 'cancelado por você': 'você cancelou',
      'expirou sem resposta': 'a janela de 15 s fechou sem aprovação'
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
        '<div class="ab-chart-wrap"><div class="ab-chart-head" id="ab-chart-head"></div><div id="ab-chart" class="ab-chart"></div>' +
          '<div class="ab-legend" id="ab-legend"></div></div>' +
        '<div class="ab-side" id="ab-side"></div>' +
      '</div>' +
      '<div class="ab-done" id="ab-done"></div>';
    if (LWC) {
      state.abChart = makeChart($('#ab-chart'));
      state.abSeries = state.abChart.addCandlestickSeries(candleColors());
      state.abLines = [];
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
    $('#ab-chart-head').innerHTML = '<strong>' + esc(a.asset) + ' · M1</strong> <span class="muted small">últimas ' + bars.length +
      ' velas · vela de comando marcada · a vela da entrada se mexe ao vivo</span>';
    $('#ab-legend').innerHTML =
      '<span class="key"><span class="line-key dashed" style="border-color:' + color + '"></span>Gatilho ' + fmtPrice(a.level_price) + '</span>' +
      (a.open_price != null ? '<span class="key"><span class="dotted-key"></span>Abertura da vela da entrada ' + fmtPrice(a.open_price) + '</span>' : '') +
      '<span class="key">' + (a.direction === 'call' ? '▲' : '▼') + ' vela de comando (' + fmtTime(a.target_ts - (a.timeframe || 60)) + ')</span>';
    if (!state.abSeries || !bars.length) return;
    var prec = precision(bars[bars.length - 1].close);
    state.abSeries.applyOptions({ priceFormat: { type: 'price', precision: prec, minMove: Math.pow(10, -prec) } });
    state.abSeries.setData(bars);
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
    state.abSeries.setMarkers(bars.some(function (b) { return b.time === cmdTime; }) ? [{
      time: cmdTime, position: a.direction === 'call' ? 'belowBar' : 'aboveBar', color: color,
      shape: a.direction === 'call' ? 'arrowUp' : 'arrowDown', text: 'comando'
    }] : []);
    if (state.abKey !== String(a.id)) {
      state.abKey = String(a.id);
      state.abChart.timeScale().setVisibleLogicalRange({ from: bars.length - 48, to: bars.length + 3 });
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
    var verb = a.strategy === 'retracao_comando' ? (call ? 'recuar (descer) até o gatilho' : 'recuar (subir) até o gatilho') : 'tocar a marcação';
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
    var candles = data && data.candles && data.candles.length >= 15 ? data.candles.slice(-60) : syntheticCandles();
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
      deadline: serverNow() + 45, window_seconds: 15, status: 'aguardando', excerpt: candles, trigger_price: null, note: null,
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
    var mini = $('#acct-mini');
    mini.textContent = real ? 'R' : 'D';
    mini.className = 'acct-mini' + (real ? ' real' : '');
    $('#side-mini').title = (real ? 'Conta REAL' : 'Conta demo') + (info && info.balance != null ? ' · saldo ' + fmtMoney(info.balance) : '') +
      (state.connected ? ' · servidor conectado' : ' · sem conexão');
    $('#orders-title').textContent = real ? 'Ordens na conta REAL' : 'Ordens na conta demo';
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
    if (s && (s.status === 'rodando' || s.status === 'conectando')) { showBanner('Pare o bot antes de trocar de conta.'); return; }
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
      ['Resultado da sessão', '<span class="' + signClass(risk.pnl) + '">' + fmtMoney(risk.pnl, true) + '</span>'],
      ['Ordens', intFmt.format(risk.trades) + (risk.open_orders ? ' + ' + risk.open_orders + ' aberta' + (risk.open_orders > 1 ? 's' : '') : '')],
      ['W · L', risk.wins + ' · ' + risk.losses]
    ];
    var html = cells.map(function (x) { return '<div class="cell"><div class="v">' + x[1] + '</div><div class="l">' + x[0] + '</div></div>'; }).join('');
    html += '<div class="risk-line muted small">Entrada ' + fmtMoney(c.stake) + ' · stop win ' + (c.stop_win ? fmtMoney(c.stop_win) : 'desligado') +
      ' · stop loss ' + (c.stop_loss ? fmtMoney(c.stop_loss) : 'desligado') +
      (c.martingale ? ' · martingale até ' + c.gale_levels + ' gale' + (c.gale_levels > 1 ? 's' : '') : '') + '</div>';
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

  function refreshOrders() {
    api('/api/orders?period=hoje&limit=100').then(function (rows) {
      rows.forEach(function (o) { state.ordersById[o.id] = o; });
      var el = $('#orders');
      if (!rows.length) {
        el.innerHTML = '<li class="empty">Nenhuma ordem enviada hoje. Quando o gatilho disparar e a ordem sair, ela aparece aqui.</li>';
        return;
      }
      el.innerHTML = rows.map(function (o) {
        var st = orderState(o);
        var money = o.profit != null && st.kind !== 'fail' ? ' ' + fmtMoney(o.profit, true) : '';
        var profit = st.detail ? '<div class="oc-res ' + (st.cls || '') + '">' + esc(st.detail + money) + '</div>' : '';
        return '<li title="' + esc(o.error || '') + '"><span class="when">' + fmtTime(o.requested_at) + '</span>' +
          '<div class="what"><div class="line1">' + dirHtml(o.direction) + ' <span class="muted small">' + esc(o.asset) + '</span></div>' +
          '<div class="line2">' + fmtMoney(o.amount) + (o.account === 'REAL' ? ' · <span class="acct-real">REAL</span>' : ' · demo') +
            (o.gale ? ' · gale ' + o.gale : '') + (st.kind === 'fail' && o.error ? ' · ' + esc(o.error) : '') + '</div></div>' +
          '<div class="right"><span class="oc-pill ' + st.kind + '">' + esc(st.label) + '</span>' + profit + '</div></li>';
      }).join('');
      if (state.status) { renderApprovals(state.status); renderArmed(state.status); }
    }).catch(function () {});
  }

  function updateStatusSub() {
    var s = state.status;
    var el = $('#status-sub');
    if (!s || (s.status !== 'rodando' && s.status !== 'conectando')) { el.textContent = ''; return; }
    if (s.progress) { el.textContent = s.progress; return; }
    var n = (s.assets || []).length;
    var what = n > 1 ? n + ' pares' : (s.asset || '');
    el.textContent = what + ' · M' + (s.timeframe / 60) + (s.status === 'rodando' && s.started_at ? ' · ' + elapsed(s.started_at) : '');
  }
  function toggleBot() {
    var s = state.status;
    var busy = s && (s.status === 'rodando' || s.status === 'conectando');
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
  function showBanner(msg) { var b = $('#banner'); b.textContent = msg; b.hidden = false; }
  function hideBanner() { $('#banner').hidden = true; }

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
      if (!st.total.n && !st.total.draws) {
        $('#p-profit-sub').textContent = state.showComparison ? 'nenhuma entrada ao vivo hoje'
          : 'a estratégia principal ainda não entrou hoje (ela é seletiva: só entra quando a vela forte é seguida do recuo nos 15 s)';
      } else $('#p-profit-sub').textContent = 'em entradas · ganho = +payout, perda = −1';
    }).catch(function () {});
    // O placar mostra sempre todas, para comparar.
    api('/api/stats?period=hoje&origin=ao_vivo').then(function (st) { renderBoard(st.by_strategy); }).catch(function () {});
    api('/api/signals?period=hoje&origin=ao_vivo&limit=200' + scopeQuery()).then(renderFeed).catch(function () {});
  }

  // Scripts de comparação rodando? (Configuração; vale a partir do início do bot.)
  function comparisonOn() {
    var s = state.status;
    if (s && (s.status === 'rodando' || s.status === 'conectando') && s.comparison != null) return !!s.comparison;
    return !!(state.config && state.config.comparison);
  }
  function renderScope() {
    if (!comparisonOn()) {
      $('#p-scope').innerHTML = '<span>Números e entradas de hoje: ' + mainStrategies().map(stratHtml).join(' ') + '</span>' +
        '<span class="muted small">Scripts de comparação desligados: só a estratégia que opera é avaliada. Dá para ligar na Configuração.</span>';
      return;
    }
    var who = state.showComparison ? '<span class="key">todas as estratégias</span>'
      : mainStrategies().map(stratHtml).join(' ');
    $('#p-scope').innerHTML = '<span>Números e entradas de hoje: ' + who + '</span>' +
      '<label class="check"><input type="checkbox" id="show-comparison"' + (state.showComparison ? ' checked' : '') +
      '> incluir os scripts de comparação (LDP v1.3, regra das linhas, WIKI PRO: ~49% na pesquisa)</label>';
  }
  function shownStrategies() {
    return comparisonOn() ? STRATEGY_ORDER : STRATEGY_ORDER.filter(isMain);
  }

  function renderBoard(groups) {
    var byKey = {};
    groups.forEach(function (g) { byKey[g.key] = g; });
    $('#p-board').innerHTML = shownStrategies().map(function (name) {
      var g = byKey[name] || { n: 0, draws: 0, wins: 0, losses: 0, winrate: null, profit: 0 };
      return '<tr><td>' + stratHtml(name) + (isMain(name) ? '<span class="tag">principal</span>' : '<span class="tag">comparação</span>') +
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

  function refreshChart() {
    return api('/api/chart?limit=240').then(renderChart).catch(function () {});
  }

  function renderChart(data) {
    state.chartData = data;
    if (!mainChart) return;
    $('#chart-title').textContent = data.asset ? data.asset + ' · M' + ((data.timeframe || 60) / 60) : 'Gráfico';
    if (!data.candles || !data.candles.length) {
      candleSeries.setData([]); buySeries.setData([]); sellSeries.setData([]); candleSeries.setMarkers([]);
      $('#p-price').textContent = '—';
      $('#p-price-sub').textContent = 'inicie o bot para ver o gráfico';
      renderReading(null);
      return;
    }
    var last = data.candles[data.candles.length - 1];
    var prec = precision(last.close);
    candleSeries.applyOptions({ priceFormat: { type: 'price', precision: prec, minMove: Math.pow(10, -prec) } });
    var bars = data.candles.slice();
    if (data.forming && data.forming.time > last.time) bars.push(data.forming);
    candleSeries.setData(bars);
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
      mainChart.timeScale().setVisibleLogicalRange({ from: bars.length - 90, to: bars.length + 3 });
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
    var markers = [];
    d.markers.forEach(function (m) {
      if (!state.visible[m.strategy]) return;
      if (m.origin === 'backtest' && !state.showBacktest) return;
      (state.markersByTime[m.time] = state.markersByTime[m.time] || []).push(m);
      markers.push({
        time: m.time, position: m.direction === 'call' ? 'belowBar' : 'aboveBar',
        color: strategyColor(m.strategy), shape: m.direction === 'call' ? 'arrowUp' : 'arrowDown',
        text: (RESULT_INFO[m.result] || { icon: '' }).icon
      });
    });
    candleSeries.setMarkers(markers);
  }

  function onCrosshair(param) {
    var out = $('#readout');
    if (!param || param.time == null || !param.seriesData) {
      out.textContent = 'Passe o mouse sobre uma vela para ver os detalhes.';
      return;
    }
    var bar = param.seriesData.get(candleSeries);
    if (!bar) return;
    var html = '<strong>' + fmtDateTime(param.time) + '</strong> · A ' + fmtPrice(bar.open) + ' · M ' + fmtPrice(bar.high) +
      ' · m ' + fmtPrice(bar.low) + ' · F ' + fmtPrice(bar.close);
    (state.markersByTime[param.time] || []).forEach(function (s) {
      html += ' &nbsp;|&nbsp; ' + stratHtml(s.strategy) + ' ' + dirHtml(s.direction) + ' ' + esc(s.setup) + ' ' + resHtml(s.result);
    });
    out.innerHTML = html;
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
      '<span class="key"><span class="line-key" style="background:' + cssVar('--line-buy') + '"></span>Linha verde · 50% do último comando de alta</span>' +
      '<span class="key"><span class="line-key" style="background:' + cssVar('--line-sell') + '"></span>Linha vermelha · 50% do último comando de baixa</span>' +
      '<span class="key"><span class="dotted-key"></span>Suporte / resistência mais próximos (apostila · F = força 1–3)</span>' +
      '<span class="key">▲▼ sinal · ✓ win · ✗ loss · … pendente</span>';
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
      state.config = cfg;
      renderToolbarAssets();
      syncVisible();
      renderToggles();
      applyMarkers();
      if (state.page === 'painel') refreshToday();
      if (fillForm) fillConfigForm(cfg);
      return cfg;
    }).catch(function (e) { if (fillForm) setResult('#cfg-save-result', false, 'Erro ao carregar: ' + e.message); });
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
    Array.prototype.forEach.call(document.querySelectorAll('input[name="cfg-strat"]'), function (c) {
      c.checked = cfg.order_strategies.indexOf(c.value) >= 0;
    });
    state.cfgPairs = cfg.assets.slice();
    renderPairChips();
    $('#cfg-timeframe').value = String(cfg.timeframe);
    $('#cfg-stake').value = cfg.stake;
    $('#cfg-stop-win').value = cfg.stop_win == null ? '' : cfg.stop_win;
    $('#cfg-stop-loss').value = cfg.stop_loss == null ? '' : cfg.stop_loss;
    $('#cfg-max-trades').value = cfg.max_trades == null ? '' : cfg.max_trades;
    $('#cfg-max-losses').value = cfg.max_consecutive_losses == null ? '' : cfg.max_consecutive_losses;
    $('#cfg-comparison').checked = !!cfg.comparison;
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
    var all = DEFAULT_PAIRS.slice();
    state.cfgPairs.forEach(function (p) { if (all.indexOf(p) < 0) all.push(p); });
    $('#cfg-assets').innerHTML = all.map(function (p) {
      return '<button type="button" class="toggle" data-pair="' + esc(p) + '" aria-pressed="' + (state.cfgPairs.indexOf(p) >= 0 ? 'true' : 'false') + '">' + esc(p) + '</button>';
    }).join('');
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
      order_strategies: Array.prototype.map.call(document.querySelectorAll('input[name="cfg-strat"]:checked'), function (c) { return c.value; }),
      assets: state.cfgPairs.slice(),
      timeframe: parseInt($('#cfg-timeframe').value, 10),
      stop_win: numField('#cfg-stop-win'),
      stop_loss: numField('#cfg-stop-loss'),
      max_trades: numField('#cfg-max-trades'),
      max_consecutive_losses: numField('#cfg-max-losses'),
      comparison: $('#cfg-comparison').checked,
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
      state.config = cfg;
      fillConfigForm(cfg);
      renderToolbarAssets();
      var changedRun = before && (before.assets.join() !== cfg.assets.join() || before.timeframe !== cfg.timeframe);
      setResult('#cfg-save-result', true, 'Configuração salva.' +
        (cfg.applies_next_start && changedRun ? ' Os pares e a vela valem no próximo início do bot (pare e inicie de novo).' : ''));
    }).catch(function (err) {
      setResult('#cfg-save-result', false, err.message);
    }).then(function () { btn.disabled = false; });
  }

  function testConnection() {
    var btn = $('#cfg-test');
    btn.disabled = true;
    setResult('#cfg-test-result', null, 'Entrando na IQ Option…');
    var email = $('#cfg-email').value.trim(), pw = $('#cfg-password').value;
    var creds = {};
    if (pw) { creds.iq_password = pw; if (email) creds.iq_email = email; }
    var first = pw ? putConfig(creds).then(function (cfg) { state.config = cfg; fillConfigForm(cfg); }) : Promise.resolve();
    first.then(function () { return api('/api/config/test', { method: 'POST' }); }).then(function (r) {
      setResult('#cfg-test-result', true, 'Conectado · ' + (r.account === 'PRACTICE' ? 'conta demo' : 'conta ' + r.account) + ' · saldo ' + fmtMoney(r.balance));
    }).catch(function (err) {
      setResult('#cfg-test-result', false, err.message);
    }).then(function () { btn.disabled = false; });
  }

  function resetHistory() {
    var s = state.status;
    if (s && (s.status === 'rodando' || s.status === 'conectando')) {
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
      if (reconnect) api('/api/status').then(checkVersion).catch(function () {});  // servidor reiniciou: painel novo?
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
    $('#focus-asset').addEventListener('change', function (e) {
      api('/api/bot/focus', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ asset: e.target.value }) })
        .then(function (s) { renderStatus(s); state.chartKey = null; refreshChart(); })
        .catch(function (err) { showBanner(err.message); });
    });
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
    });
    $('#btn-shutdown').addEventListener('click', shutdown);
    $('#script-toggles').addEventListener('click', function (e) {
      var btn = e.target.closest('.toggle');
      if (!btn) return;
      var n = btn.dataset.s;
      state.visible[n] = !state.visible[n];
      btn.setAttribute('aria-pressed', state.visible[n] ? 'true' : 'false');
      applyMarkers();
    });
    $('#show-backtest').addEventListener('change', function (e) { state.showBacktest = e.target.checked; applyMarkers(); });
    $('#p-scope').addEventListener('change', function (e) {
      if (e.target.id !== 'show-comparison') return;
      state.showComparison = e.target.checked;
      try { localStorage.setItem('botbene-comparacao', state.showComparison ? '1' : '0'); } catch (err) { /* sem armazenamento */ }
      syncVisible();
      renderToggles();
      applyMarkers();
      refreshToday();
    });
    bindSegmented('#e-period', 'ePeriod', refreshEntradas);
    bindSegmented('#d-period', 'dPeriod', refreshDesempenho);
    ['strategy', 'result', 'origin'].forEach(function (k) { $('#e-' + k).addEventListener('change', refreshEntradas); });
    ['strategy', 'asset', 'origin'].forEach(function (k) { $('#d-' + k).addEventListener('change', refreshDesempenho); });

    api('/api/strategies').then(function (list) {
      list.forEach(function (s) { LABELS[s.name] = s.label; });
      var opts = '<option value="">Todos</option>' + list.map(function (s) {
        return '<option value="' + esc(s.name) + '">' + esc(s.label) + '</option>';
      }).join('');
      $('#e-strategy').innerHTML = opts;
      $('#d-strategy').innerHTML = opts;
      renderToggles();
    }).catch(function () {});

    var fromHash = location.hash.replace('#', '');
    loadConfig(fromHash === 'config');
    refreshAccount();
    refreshOrders();  // o cartão de resultado precisa saber das ordens mesmo fora do Painel
    setInterval(refreshAccount, 60000);
    api('/api/status').then(function (s) {
      checkVersion(s);
      renderStatus(s);
      if (PAGE_TITLES[fromHash]) setPage(fromHash); else refreshCurrent();
      // Endereço terminado em #exemplo abre um pedido de exemplo (só na tela, não envia nada): usado para conferir o visual.
      if (fromHash === 'exemplo') setTimeout(showDemoApproval, 2500);
    }).catch(function () { setConnected(false); });
    connectWs();
    setInterval(function () {
      updateStatusSub();
      api('/api/status').then(function (s) { checkVersion(s); renderStatus(s); }).catch(function () {});
    }, 30000);
    setInterval(function () { updateCountdowns(); updateApprovalClocks(); }, 1000);
  }

  document.addEventListener('DOMContentLoaded', init);
})();
