/**
 * terminal.js - Institutional Algo-Trading & Screening Web Engine
 * Manages WebSocket feeds, screener queries, committee floor debates,
 * GoCharting integration, and paper trading executions.
 */

class AlgoTerminalApp {
  constructor() {
    this.activeSymbol = 'KOTAKBANK';
    this.symbols = [];
    this.chart = null;
    this.socket = null;
    this.tapeHistory = [];
    this.maxTapeItems = 25;
    this.screenerData = [];
    this.currentChartMode = 'canvas'; // 'canvas', 'gocharting-sdk', or 'gocharting-cloud'
    this.gcController = null;
    this.simEnabled = false;

    this.init();
  }

  async init() {
    this.setupClock();
    this.setupTabs();
    this.setupSearch();
    this.setupScreenerControls();
    this.setupOrderPanel();
    this.setupWebhookTester();
    this.setupSyncButtons();
    this.setupSimulatorToggle();

    // Initialize Canvas Chart
    this.chart = new OrderflowCanvasChart('orderflowCanvas');

    // Initialize GoCharting SDK Controller
    if (window.GoChartingController) {
      this.gcController = new GoChartingController('gochartingSdkContainer', {
        activeSymbol: this.activeSymbol,
        onOrderPlaced: (res) => {
          this.loadPortfolio();
          const ord = res.order || {};
          alert(`Order Executed via GoCharting Trade-from-Chart:\n${ord.transaction_type || 'BUY'} ${ord.quantity || 50} ${ord.symbol || this.activeSymbol} @ ₹${ord.price || 0.0}`);
        }
      });
    }

    // Fetch initial system status and symbols
    await this.fetchStatus();
    await this.fetchSymbols();

    // Load initial screener and committee view
    await this.runScreener();
    await this.loadCommittee(this.activeSymbol);
    await this.loadOrderflow(this.activeSymbol);
    await this.loadPortfolio();

    // Establish WebSocket Connection
    this.connectLiveWebSocket();

    // Periodic portfolio refresh
    setInterval(() => this.loadPortfolio(), 4000);
    setInterval(() => this.fetchStatus(), 10000);
  }

  setupClock() {
    const clockEl = document.getElementById('marketClock');
    const updateTime = () => {
      const now = new Date();
      // IST is UTC + 5:30
      const istOptions = { timeZone: 'Asia/Kolkata', hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' };
      if (clockEl) {
        clockEl.textContent = now.toLocaleTimeString('en-GB', istOptions) + ' IST';
      }
    };
    updateTime();
    setInterval(updateTime, 1000);
  }

  setupTabs() {
    const tabBtns = document.querySelectorAll('.tab-btn');
    tabBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        tabBtns.forEach(b => b.classList.remove('active'));
        document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));

        btn.classList.add('active');
        const targetTab = btn.getAttribute('data-tab');
        const content = document.getElementById(`tab-${targetTab}`);
        if (content) {
          content.classList.add('active');
        }

        // Trigger chart resize if navigating to chart tab
        if (targetTab === 'orderflow' && this.chart) {
          setTimeout(() => this.chart.resize(), 50);
        }
      });
    });

    // Chart View Toggle (Native Canvas vs GoCharting Local SDK vs GoCharting Cloud Embed)
    const toggleBtns = document.querySelectorAll('.view-toggle-btn');
    toggleBtns.forEach(btn => {
      btn.addEventListener('click', () => {
        toggleBtns.forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
        const mode = btn.getAttribute('data-view');
        this.currentChartMode = mode;

        const canvasBox = document.getElementById('orderflowCanvas');
        const sdkBox = document.getElementById('gochartingSdkContainer');
        const cloudBox = document.getElementById('gochartingCloudBox');

        if (mode === 'canvas') {
          if (canvasBox) canvasBox.style.display = 'block';
          if (sdkBox) sdkBox.style.display = 'none';
          if (cloudBox) cloudBox.style.display = 'none';
          this.chart.resize();
        } else if (mode === 'gocharting-sdk') {
          if (canvasBox) canvasBox.style.display = 'none';
          if (sdkBox) sdkBox.style.display = 'flex';
          if (cloudBox) cloudBox.style.display = 'none';
          if (this.gcController) this.gcController.setSymbol(this.activeSymbol);
        } else {
          if (canvasBox) canvasBox.style.display = 'none';
          if (sdkBox) sdkBox.style.display = 'none';
          if (cloudBox) cloudBox.style.display = 'flex';
          this.updateGoChartingCloudPortal(this.activeSymbol);
        }
      });
    });

    // In-terminal quick mode switcher buttons in Cloud Gateway
    const btnSwitchCanvas = document.getElementById('btnSwitchToCanvas');
    const btnSwitchSdk = document.getElementById('btnSwitchToSdk');
    if (btnSwitchCanvas) {
      btnSwitchCanvas.addEventListener('click', () => {
        const toggle = document.querySelector('.view-toggle-btn[data-view="canvas"]');
        if (toggle) toggle.click();
      });
    }
    if (btnSwitchSdk) {
      btnSwitchSdk.addEventListener('click', () => {
        const toggle = document.querySelector('.view-toggle-btn[data-view="gocharting-sdk"]');
        if (toggle) toggle.click();
      });
    }
  }

  setupSearch() {
    const searchInput = document.getElementById('symbolSearch');
    const dropdown = document.getElementById('searchDropdown');

    searchInput.addEventListener('input', (e) => {
      const val = e.target.value.toUpperCase().trim();
      if (!val) {
        dropdown.classList.remove('active');
        return;
      }

      const matches = this.symbols.filter(s => s.symbol.includes(val)).slice(0, 8);
      if (matches.length > 0) {
        dropdown.innerHTML = matches.map(m => `
          <div class="search-item" data-sym="${m.symbol}">
            <span style="font-weight: 700; color: var(--neon-cyan);">${m.symbol}</span>
            <span style="font-family: var(--font-mono); font-size: 11px;">₹${m.close.toFixed(2)} (${m.change_pct >= 0 ? '+' : ''}${m.change_pct}%)</span>
          </div>
        `).join('');
        dropdown.classList.add('active');

        dropdown.querySelectorAll('.search-item').forEach(item => {
          item.addEventListener('click', () => {
            const sym = item.getAttribute('data-sym');
            this.selectSymbol(sym);
            searchInput.value = '';
            dropdown.classList.remove('active');
          });
        });
      } else {
        dropdown.classList.remove('active');
      }
    });

    document.addEventListener('click', (e) => {
      if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
        dropdown.classList.remove('active');
      }
    });
  }

  setupScreenerControls() {
    const delivSlider = document.getElementById('delivSlider');
    const delivVal = document.getElementById('delivVal');
    const spikeSlider = document.getElementById('spikeSlider');
    const spikeVal = document.getElementById('spikeVal');
    const modeSelect = document.getElementById('screenerMode');
    const btnScan = document.getElementById('btnRunScan');
    const btnExport = document.getElementById('btnExportScreener');

    if (delivSlider) {
      delivSlider.addEventListener('input', (e) => {
        delivVal.textContent = `${e.target.value}%`;
      });
    }

    if (spikeSlider) {
      spikeSlider.addEventListener('input', (e) => {
        spikeVal.textContent = `${parseFloat(e.target.value).toFixed(1)}x`;
      });
    }

    if (btnScan) {
      btnScan.addEventListener('click', () => this.runScreener());
    }

    if (btnExport) {
      btnExport.addEventListener('click', () => this.exportScreenerCSV());
    }
  }

  setupOrderPanel() {
    const btnBuy = document.getElementById('btnPlaceBuy');
    const btnSell = document.getElementById('btnPlaceSell');
    const orderQty = document.getElementById('orderQty');
    const orderType = document.getElementById('orderType');

    const handleOrder = async (side) => {
      const qty = parseInt(orderQty.value) || 50;
      const type = orderType.value;
      const res = await this.placeOrder({
        symbol: this.activeSymbol,
        quantity: qty,
        transaction_type: side,
        order_type: type,
        price: 0.0,
        tag: 'MANUAL_TERMINAL'
      });

      if (res && ['EXECUTED', 'SUCCESS', 'success'].includes(res.status)) {
        this.showToast(res.broker === 'OpenAlgo' ? `OpenAlgo accepted submission: ${side} ${qty} ${this.activeSymbol}. Check fills in OpenAlgo.` : `Order Executed: ${side} ${qty} ${this.activeSymbol}`);
        await this.loadPortfolio();
      } else if (res) {
        this.showToast(res.reason || res.detail || 'Order was not accepted');
      }
    };

    if (btnBuy) btnBuy.addEventListener('click', () => handleOrder('BUY'));
    if (btnSell) btnSell.addEventListener('click', () => handleOrder('SELL'));
  }

  setupWebhookTester() {
    const btnSendWebhook = document.getElementById('btnTestWebhook');
    if (btnSendWebhook) {
      btnSendWebhook.addEventListener('click', async () => {
        const action = document.getElementById('whAction').value;
        const sym = this.activeSymbol;
        const res = await fetch('/api/broker/webhook', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            symbol: sym,
            action: action,
            price: 0.0,
            indicator: 'GoCharting OrderFlow Alert',
            quantity: 50
          })
        });
        const data = await res.json();
        this.showToast(`GoCharting Webhook Dispatched: ${action} ${sym}`);
        await this.loadPortfolio();
      });
    }
  }

  setupSimulatorToggle() {
    const btn = document.getElementById('btnToggleSim');
    if (!btn) return;
    btn.addEventListener('click', () => {
      this.simEnabled = !this.simEnabled;
      btn.textContent = this.simEnabled ? '⏸ Pause Sim' : '▶ Test Sim';
      btn.style.background = this.simEnabled ? 'var(--neon-gold)' : 'rgba(0,242,254,0.1)';
      btn.style.color = this.simEnabled ? '#07090e' : 'var(--neon-cyan)';
      
      const badge = document.getElementById('feedModeBadge');
      if (badge) {
        badge.textContent = this.simEnabled ? 'OFF-HOURS TEST SIMULATOR' : 'REAL EOD TAPE';
        badge.style.color = this.simEnabled ? 'var(--neon-gold)' : 'var(--neon-green)';
        badge.style.borderColor = this.simEnabled ? 'rgba(255,214,0,0.4)' : 'rgba(0,230,118,0.4)';
      }

      if (this.socket && this.socket.readyState === WebSocket.OPEN) {
        this.socket.send(JSON.stringify({
          action: 'TOGGLE_SIMULATOR',
          enabled: this.simEnabled
        }));
      }
    });
  }

  setupSyncButtons() {
    const btnAmiExport = document.getElementById('btnDownloadAmiBroker');
    if (btnAmiExport) {
      btnAmiExport.addEventListener('click', () => {
        window.location.href = `/api/orderflow/${this.activeSymbol}/export`;
      });
    }
  }

  async fetchStatus() {
    try {
      const res = await fetch('/api/status');
      const data = await res.json();
      document.getElementById('statSymbolsCount').textContent = `${data.cached_symbols} F&O`;
      document.getElementById('statDbBars').textContent = `${data.db_bars_count.toLocaleString()} Bars`;
      document.getElementById('statBrokerName').textContent = data.active_broker.toUpperCase();
      document.getElementById('statCash').textContent = data.cash_balance == null ? 'View broker' : `₹${data.cash_balance.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

      const statusEl = document.getElementById('marketSessionStatus');
      if (statusEl) {
        statusEl.textContent = data.market_open ? 'LIVE MARKET OPEN' : 'MARKET CLOSED';
        statusEl.style.color = data.market_open ? 'var(--neon-green)' : 'var(--neon-gold)';
        statusEl.style.background = data.market_open ? 'rgba(0,230,118,0.12)' : 'rgba(255,214,0,0.12)';
      }
    } catch (e) {
      console.warn('Status fetch error:', e);
    }
  }

  async fetchSymbols() {
    try {
      const res = await fetch('/api/symbols');
      this.symbols = await res.json();
    } catch (e) {
      console.warn('Symbols fetch error:', e);
    }
  }

  async selectSymbol(symbol) {
    this.activeSymbol = symbol.toUpperCase().trim();
    document.getElementById('activeSymbolBadge').textContent = this.activeSymbol;
    const orderSymInput = document.getElementById('orderSymbol');
    if (orderSymInput) orderSymInput.value = this.activeSymbol;

    const candleTitle = document.getElementById('candleSymbolTitle');
    if (candleTitle) candleTitle.textContent = `PRIMARY: ${this.activeSymbol} (CONNECTING...)`;

    const tapeEl = document.getElementById('tapeStream');
    if (tapeEl) {
      tapeEl.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 25px 10px; font-size: 11px;">Streaming live market tape for ${this.activeSymbol}...</div>`;
    }
    this.tapeHistory = [];

    // Notify WebSocket of subscription
    if (this.socket && this.socket.readyState === WebSocket.OPEN) {
      this.socket.send(JSON.stringify({ action: 'SUBSCRIBE', symbol: this.activeSymbol }));
    }

    // Refresh Committee & Orderflow Views
    await this.loadCommittee(this.activeSymbol);
    await this.loadOrderflow(this.activeSymbol);

    // Sync GoCharting Controller & Cloud Gateway
    if (this.gcController) {
      this.gcController.setSymbol(this.activeSymbol);
    }
    this.updateGoChartingCloudPortal(this.activeSymbol);
  }

  updateGoChartingCloudPortal(symbol) {
    const btn = document.getElementById('btnLaunchGoChartingCloud');
    const targetUrlSpan = document.getElementById('gcDiagTargetUrl');
    const udfStatusSpan = document.getElementById('gcDiagUdfStatus');
    const cloudUrl = `https://gocharting.com/terminal?symbol=NSE:${symbol}&theme=dark`;
    if (btn) {
      btn.href = cloudUrl;
      btn.innerHTML = `🚀 Launch Full GoCharting Cloud Terminal for NSE:${symbol} in New Tab ↗`;
    }
    if (targetUrlSpan) {
      targetUrlSpan.textContent = cloudUrl;
    }
    if (udfStatusSpan) {
      udfStatusSpan.textContent = `Active (/api/gocharting/history?symbol=${symbol}&resolution=1)`;
    }
  }

  // --------------------------------------------------------------------------
  // REAL-TIME WEBSOCKET (Time & Sales tape and forming candle)
  // --------------------------------------------------------------------------
  connectLiveWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/live`;
    this.socket = new WebSocket(wsUrl);

    this.socket.onopen = () => {
      console.log('[WS] Connected to high-speed stream');
      const connDot = document.getElementById('wsStatusDot');
      if (connDot) connDot.style.background = 'var(--neon-green)';
    };

    this.socket.onmessage = (event) => {
      const msg = JSON.parse(event.data);

      if (msg.type === 'CONNECTION_ESTABLISHED' || msg.type === 'SYMBOL_SNAPSHOT') {
        const isMarketOpen = (msg.market_open !== undefined) ? msg.market_open : this.isMarketOpen;
        this.isMarketOpen = isMarketOpen;

        const statusEl = document.getElementById('marketSessionStatus');
        if (statusEl) {
          statusEl.textContent = isMarketOpen ? 'LIVE MARKET OPEN (NSE 09:15 - 15:30 IST)' : 'MARKET CLOSED (NSE 09:15 - 15:30 IST)';
          statusEl.style.color = isMarketOpen ? 'var(--neon-green)' : 'var(--neon-gold)';
          statusEl.style.background = isMarketOpen ? 'rgba(0,230,118,0.12)' : 'rgba(255,214,0,0.12)';
        }

        const badge = document.getElementById('feedModeBadge');
        if (badge) {
          if (isMarketOpen) {
            badge.textContent = '⚡ LIVE NSE MARKET TAPE';
            badge.style.color = 'var(--neon-green)';
            badge.style.background = 'rgba(0, 230, 118, 0.15)';
            badge.style.border = '1px solid rgba(0, 230, 118, 0.3)';
          } else if (this.simEnabled) {
            badge.textContent = 'OFF-HOURS TEST SIMULATOR';
            badge.style.color = 'var(--neon-gold)';
            badge.style.background = 'rgba(255, 214, 0, 0.15)';
            badge.style.border = '1px solid rgba(255, 214, 0, 0.3)';
          } else {
            badge.textContent = 'REAL EOD TAPE (SESSION CLOSED)';
            badge.style.color = 'var(--text-secondary)';
            badge.style.background = 'rgba(255, 255, 255, 0.05)';
            badge.style.border = '1px solid rgba(255, 255, 255, 0.1)';
          }
        }

        const candleHeader = document.getElementById('candleSectionHeader');
        if (candleHeader) {
          candleHeader.textContent = isMarketOpen ? '⚡ Live Forming 1-Minute Candle (Real Market Feed)' : '⚡ Session Close 1-Minute Candle (Real EOD Data)';
        }

        if (msg.last_eod_candle) {
          this.updateFormingCandleCard(msg.last_eod_candle);
          if (this.gcController && this.gcController.datafeed) {
            this.gcController.datafeed.handleIncomingCandle(msg.last_eod_candle);
          }
          const title = document.getElementById('candleSymbolTitle');
          if (title) {
            const timeStr = msg.last_eod_candle.datetime ? msg.last_eod_candle.datetime.split(' ')[1] : 'LIVE';
            title.textContent = `PRIMARY: ${msg.last_eod_candle.symbol} (${timeStr} IST)`;
          }
        }

        if (msg.recent_eod_ticks && msg.recent_eod_ticks.length > 0) {
          this.renderRecordedTicks(msg.recent_eod_ticks);
        }
      }

      if (msg.type === 'SIMULATOR_STATE') {
        const badge = document.getElementById('feedModeBadge');
        if (badge) {
          if (msg.feed_mode === 'LIVE_MARKET') {
            badge.textContent = '⚡ LIVE NSE MARKET TAPE';
            badge.style.color = 'var(--neon-green)';
          } else {
            badge.textContent = msg.enabled ? 'OFF-HOURS TEST SIMULATOR' : 'REAL EOD TAPE (SESSION CLOSED)';
            badge.style.color = msg.enabled ? 'var(--neon-gold)' : 'var(--neon-green)';
          }
        }
      }

      if (msg.type === 'TICK' && msg.tick) {
        this.handleIncomingTick(msg.tick);
      }
      if (msg.forming_candle) {
        this.updateFormingCandleCard(msg.forming_candle);
        if (this.gcController && this.gcController.datafeed) {
          this.gcController.datafeed.handleIncomingCandle(msg.forming_candle);
        }
      }
    };

    this.socket.onclose = () => {
      console.warn('[WS] Stream closed. Reconnecting in 2s...');
      const connDot = document.getElementById('wsStatusDot');
      if (connDot) connDot.style.background = 'var(--neon-red)';
      setTimeout(() => this.connectLiveWebSocket(), 2000);
    };
  }

  renderRecordedTicks(ticks) {
    const tapeEl = document.getElementById('tapeStream');
    if (!tapeEl) return;
    tapeEl.innerHTML = '';
    this.tapeHistory = [];
    ticks.forEach(tick => {
      this.tapeHistory.push(tick);
      const row = document.createElement('div');
      const isBuy = tick.side === 'BUY';
      row.className = `tape-row ${isBuy ? 'buy' : 'sell'} ${tick.is_block ? 'block' : ''}`;
      row.innerHTML = `
        <span class="mono" style="color: var(--text-muted);">${tick.timestamp.substring(0, 8)}</span>
        <span class="mono" style="font-weight: 700; color: ${isBuy ? 'var(--neon-green)' : 'var(--neon-red)'};">₹${tick.price.toFixed(2)}</span>
        <span class="mono" style="color: var(--text-highlight);">${tick.size.toLocaleString()}</span>
        <span class="mono" style="font-size: 10px; color: var(--text-secondary);">${tick.symbol} ${tick.is_block ? '⚡BLOCK' : ''}</span>
      `;
      tapeEl.appendChild(row);
    });
  }

  handleIncomingTick(tick) {
    if (tick.symbol && tick.symbol !== this.activeSymbol) {
      return; // Filter out ticks not matching active symbol
    }

    this.tapeHistory.unshift(tick);
    if (this.tapeHistory.length > this.maxTapeItems) {
      this.tapeHistory.pop();
    }

    const tapeEl = document.getElementById('tapeStream');
    if (!tapeEl) return;

    const row = document.createElement('div');
    const isBuy = tick.side === 'BUY';
    row.className = `tape-row ${isBuy ? 'buy' : 'sell'} ${tick.is_block ? 'block' : ''} ${isBuy ? 'tape-flash-buy' : 'tape-flash-sell'}`;
    row.innerHTML = `
      <span class="mono" style="color: var(--text-muted);">${tick.timestamp.substring(0, 8)}</span>
      <span class="mono" style="font-weight: 700; color: ${isBuy ? 'var(--neon-green)' : 'var(--neon-red)'};">₹${tick.price.toFixed(2)}</span>
      <span class="mono" style="color: var(--text-highlight);">${tick.size.toLocaleString()}</span>
      <span class="mono" style="font-size: 10px; color: var(--text-secondary);">${tick.symbol} ${tick.is_block ? '⚡BLOCK' : ''}</span>
    `;

    tapeEl.insertBefore(row, tapeEl.firstChild);
    if (tapeEl.children.length > this.maxTapeItems) {
      tapeEl.removeChild(tapeEl.lastChild);
    }
  }

  updateFormingCandleCard(c) {
    if (c.symbol && c.symbol !== this.activeSymbol) {
      return;
    }

    const elO = document.getElementById('liveOpen');
    const elH = document.getElementById('liveHigh');
    const elL = document.getElementById('liveLow');
    const elC = document.getElementById('liveClose');
    const elV = document.getElementById('liveVol');
    const elDelta = document.getElementById('liveDelta');

    if (elO) elO.textContent = `₹${c.open.toFixed(2)}`;
    if (elH) elH.textContent = `₹${c.high.toFixed(2)}`;
    if (elL) elL.textContent = `₹${c.low.toFixed(2)}`;
    if (elC) elC.textContent = `₹${c.close.toFixed(2)}`;
    if (elV) elV.textContent = c.volume.toLocaleString();
    if (elDelta) {
      elDelta.textContent = (c.delta >= 0 ? '+' : '') + c.delta.toLocaleString();
      elDelta.className = `number ${c.delta >= 0 ? 'delta-positive' : 'delta-negative'}`;
    }
  }

  // --------------------------------------------------------------------------
  // INSTITUTIONAL SCREENER
  // --------------------------------------------------------------------------
  async runScreener() {
    const deliv = parseFloat(document.getElementById('delivSlider')?.value || 70.0);
    const spike = parseFloat(document.getElementById('spikeSlider')?.value || 2.0);
    const mode = document.getElementById('screenerMode')?.value || 'both';

    try {
      const url = `/api/screener?min_delivery=${deliv}&volume_spike=${spike}&mode=${mode}&limit=40`;
      const res = await fetch(url);
      const data = await res.json();
      this.screenerData = data.results || [];
      document.getElementById('screenerCountBadge').textContent = `${data.matched_count} Setups (${data.query_duration_ms}ms)`;

      this.renderScreenerTable(this.screenerData);
    } catch (e) {
      console.warn('Screener error:', e);
    }
  }

  renderScreenerTable(items) {
    const tbody = document.getElementById('screenerTableBody');
    if (!tbody) return;

    if (!items || items.length === 0) {
      tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 30px;">No institutional setups matched current thresholds. Try reducing Delivery % or Volume Spike.</td></tr>`;
      return;
    }

    tbody.innerHTML = items.map(r => `
      <tr>
        <td>
          <a href="javascript:void(0)" onclick="app.selectSymbol('${r.symbol}')" style="color: var(--neon-cyan); font-weight: 700; text-decoration: none;">
            ${r.symbol}
          </a>
        </td>
        <td class="mono" style="color: var(--text-muted);">${r.date}</td>
        <td class="mono" style="font-weight: 700;">₹${r.close.toFixed(2)}</td>
        <td class="mono" style="color: ${r.change_pct >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'}; font-weight: 600;">
          ${r.change_pct >= 0 ? '+' : ''}${r.change_pct}%
        </td>
        <td class="mono">${r.volume.toLocaleString()}</td>
        <td class="mono" style="color: var(--text-muted);">${r.vol_sma.toLocaleString()}</td>
        <td><span class="badge-spike mono">${r.vol_spike.toFixed(2)}x</span></td>
        <td class="mono">${r.deliv_qty.toLocaleString()}</td>
        <td><span class="badge-deliv mono">${r.delivery_pct.toFixed(1)}%</span></td>
        <td>
          <button class="btn-action-sm" onclick="app.selectSymbol('${r.symbol}'); app.switchToTab('committee');">
            Debate
          </button>
        </td>
      </tr>
    `).join('');
  }

  switchToTab(tabName) {
    const btn = document.querySelector(`.tab-btn[data-tab="${tabName}"]`);
    if (btn) btn.click();
  }

  exportScreenerCSV() {
    if (!this.screenerData.length) return;
    const headers = ['Symbol,Date,Close,ChangePct,TradedQty,VolSMA,VolSpike,DelivQty,DeliveryPct'];
    const rows = this.screenerData.map(r => 
      `${r.symbol},${r.date},${r.close},${r.change_pct},${r.volume},${r.vol_sma},${r.vol_spike},${r.deliv_qty},${r.delivery_pct}`
    );
    const blob = new Blob([headers.concat(rows).join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `institutional_signals_${new Date().toISOString().slice(0,10)}.csv`;
    a.click();
  }

  // --------------------------------------------------------------------------
  // 5-PERSONA INVESTMENT COMMITTEE
  // --------------------------------------------------------------------------
  async loadCommittee(symbol) {
    try {
      const res = await fetch(`/api/committee/${symbol}`);
      if (!res.ok) return;
      const data = await res.json();
      this.renderCommitteeUI(data);
    } catch (e) {
      console.warn('Committee load error:', e);
    }
  }

  renderCommitteeUI(report) {
    const m = report.metrics;
    const funds = m.fundamentals || {};
    const pMom = report.momentum;
    const pDel = report.delivery;
    const pVal = report.value;
    const pRisk = report.risk;

    // Header & CIO Dial
    document.getElementById('cioSymbolName').textContent = `${m.symbol} (${funds.company_name || m.symbol})`;
    document.getElementById('cioDatePrice').textContent = `Date: ${m.date} | Close: ₹${m.close.toFixed(2)} (${m.ret_1d >= 0 ? '+' : ''}${m.ret_1d.toFixed(2)}%) | VWAP: ₹${m.vwap.toFixed(2)}`;
    
    const scoreNum = document.getElementById('cioScoreNum');
    scoreNum.textContent = (report.composite_score >= 0 ? '+' : '') + report.composite_score.toFixed(1);
    
    const verdictEl = document.getElementById('cioVerdictBadge');
    verdictEl.textContent = report.consensus;
    verdictEl.className = 'verdict-tag ' + (
      report.composite_score >= 4.0 ? 'verdict-strong-buy' :
      report.composite_score >= 1.5 ? 'verdict-accumulate' :
      report.composite_score >= -1.5 ? 'verdict-neutral' : 'verdict-avoid'
    );

    document.getElementById('cioActionText').textContent = report.action;

    // Screener.in Fundamentals Strip
    document.getElementById('fundMcap').textContent = funds.market_cap_cr ? `₹${funds.market_cap_cr.toLocaleString()} Cr` : '-';
    document.getElementById('fundPE').textContent = funds.pe ? `${funds.pe}x` : '-';
    document.getElementById('fundPB').textContent = funds.pb ? `${funds.pb}x` : '-';
    document.getElementById('fundROCE').textContent = funds.roce ? `${funds.roce}%` : '-';
    document.getElementById('fundROE').textContent = funds.roe ? `${funds.roe}%` : '-';
    document.getElementById('fundProfitCAGR').textContent = funds.profit_cagr_5y ? `${funds.profit_cagr_5y}%` : '-';

    // 1. Momentum Card
    this.renderPersonaCard('pMom', pMom, `
      <div style="font-size: 11px; margin-top: 8px; background: rgba(0,0,0,0.25); padding: 8px; border-radius: 4px;" class="mono">
        Setup: Entry: <b>₹${pMom.entry.toFixed(2)}</b> | SL: <b>₹${pMom.stop_loss.toFixed(2)}</b><br>
        T1: <b>₹${pMom.target_1.toFixed(2)}</b> | T2: <b>₹${pMom.target_2.toFixed(2)}</b> (R:R ${pMom.rr_ratio})
      </div>
    `);

    // 2. Delivery Tracker Card
    this.renderPersonaCard('pDel', pDel, `
      <div style="font-size: 11px; margin-top: 8px; color: var(--neon-green);" class="mono">
        📊 Institutional Absorption: ${pDel.deliv_pct} delivered (${pDel.deliv_percentile}th percentile)
      </div>
    `);

    // 3. Value Investor Card
    this.renderPersonaCard('pVal', pVal, `
      <div style="font-size: 11px; margin-top: 8px; color: var(--neon-purple);">
        🏛 Screener Multiples: P/E ${funds.pe || '-'}x | ROCE ${funds.roce || '-'}% | 5Y CAGR ${funds.profit_cagr_5y || '-'}%
      </div>
    `);

    // 4. Quantitative Risk Card
    this.renderPersonaCard('pRisk', pRisk, `
      <div style="font-size: 11px; margin-top: 8px; background: rgba(0,242,254,0.06); padding: 8px; border-radius: 4px; border: 1px solid rgba(0,242,254,0.2);" class="mono">
        ⚡ 1% Portfolio Risk Sizing: <b>${pRisk.recommended_sizing}</b>
      </div>
    `);
  }

  renderPersonaCard(prefix, persona, extraHtml = '') {
    const voteEl = document.getElementById(`${prefix}Vote`);
    if (voteEl) {
      voteEl.textContent = `${persona.score >= 0 ? '+' : ''}${persona.score}/10 | ${persona.verdict}`;
      voteEl.className = `persona-vote-chip ${persona.score >= 0 ? 'vote-pos' : 'vote-neg'}`;
    }

    const listEl = document.getElementById(`${prefix}Signals`);
    if (listEl) {
      listEl.innerHTML = persona.signals.map(s => `<li>${s}</li>`).join('') + (extraHtml ? `<li>${extraHtml}</li>` : '');
    }
  }

  // --------------------------------------------------------------------------
  // ORDER FLOW & GOCHARTING
  // --------------------------------------------------------------------------
  async loadOrderflow(symbol) {
    try {
      const res = await fetch(`/api/orderflow/${symbol}?limit=250`);
      const data = await res.json();
      if (this.chart) {
        this.chart.setData(symbol, data.bars);
      }
    } catch (e) {
      console.warn('Orderflow fetch error:', e);
    }
  }

  // --------------------------------------------------------------------------
  // PORTFOLIO & ORDERS
  // --------------------------------------------------------------------------
  async loadPortfolio() {
    try {
      const res = await fetch('/api/portfolio');
      const data = await res.json();

      if (data.status === 'view_in_openalgo') {
        ['pCash', 'pInvested', 'pEquity', 'pPnl'].forEach(id => { document.getElementById(id).textContent = 'View OpenAlgo'; });
        document.getElementById('positionsTableBody').textContent = data.message;
        document.getElementById('ordersTableBody').textContent = 'Order status and fills are available in OpenAlgo.';
        return;
      }

      document.getElementById('pCash').textContent = `₹${data.cash.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
      document.getElementById('pInvested').textContent = `₹${data.total_invested.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
      document.getElementById('pEquity').textContent = `₹${data.total_equity.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;

      const pnlEl = document.getElementById('pPnl');
      pnlEl.textContent = `${data.unrealized_pnl >= 0 ? '+' : ''}₹${data.unrealized_pnl.toLocaleString('en-IN', { maximumFractionDigits: 2 })}`;
      pnlEl.className = `v mono ${data.unrealized_pnl >= 0 ? 'delta-positive' : 'delta-negative'}`;

      // Sync GoCharting broker state
      if (this.gcController) {
        this.gcController.syncBrokerState(data);
      }

      // Render Positions Table
      const posBody = document.getElementById('positionsTableBody');
      if (posBody) {
        if (!data.positions.length) {
          posBody.innerHTML = `<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 20px;">No open positions in active account.</td></tr>`;
        } else {
          posBody.innerHTML = data.positions.map(p => `
            <tr>
              <td><span style="font-weight: 700; color: var(--neon-cyan);">${p.symbol}</span></td>
              <td class="mono">${p.quantity}</td>
              <td class="mono">₹${p.avg_price.toFixed(2)}</td>
              <td class="mono">₹${p.current_price.toFixed(2)}</td>
              <td class="mono">₹${p.market_value.toLocaleString()}</td>
              <td class="mono" style="font-weight: 700; color: ${p.pnl >= 0 ? 'var(--neon-green)' : 'var(--neon-red)'};">
                ${p.pnl >= 0 ? '+' : ''}₹${p.pnl.toFixed(2)} (${p.pnl_pct >= 0 ? '+' : ''}${p.pnl_pct}%)
              </td>
              <td>
                <button class="btn-action-sm" onclick="app.placeOrder({symbol: '${p.symbol}', quantity: ${p.quantity}, transaction_type: 'SELL', order_type: 'MARKET'})">
                  Exit
                </button>
              </td>
            </tr>
          `).join('');
        }
      }

      // Render Orders Table
      const ordersBody = document.getElementById('ordersTableBody');
      if (ordersBody) {
        ordersBody.innerHTML = (data.orders || []).slice(-10).reverse().map(o => `
          <tr>
            <td class="mono" style="font-size: 11px; color: var(--text-muted);">${o.timestamp}</td>
            <td style="font-weight: 700;">${o.symbol}</td>
            <td class="mono" style="color: ${o.type === 'BUY' ? 'var(--neon-green)' : 'var(--neon-red)'}; font-weight: 700;">${o.type}</td>
            <td class="mono">${o.quantity}</td>
            <td class="mono">₹${o.price.toFixed(2)}</td>
            <td><span class="badge-deliv mono">${o.tag || 'ALGO'}</span></td>
            <td><span class="mono" style="color: var(--neon-cyan);">${o.status}</span></td>
          </tr>
        `).join('');
      }
    } catch (e) {
      console.warn('Portfolio load error:', e);
    }
  }

  async placeOrder(orderPayload) {
    try {
      const res = await fetch('/api/order', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(orderPayload)
      });
      return await res.json();
    } catch (e) {
      console.warn('Place order error:', e);
      return null;
    }
  }

  showToast(message) {
    const toast = document.createElement('div');
    toast.style.position = 'fixed';
    toast.style.bottom = '20px';
    toast.style.right = '20px';
    toast.style.background = 'rgba(22, 30, 49, 0.95)';
    toast.style.border = '1px solid var(--neon-cyan)';
    toast.style.boxShadow = '0 0 20px var(--neon-cyan-glow)';
    toast.style.color = 'var(--text-highlight)';
    toast.style.padding = '12px 18px';
    toast.style.borderRadius = '8px';
    toast.style.fontSize = '12px';
    toast.style.fontFamily = 'var(--font-mono)';
    toast.style.zIndex = '9999';
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3500);
  }
}

// Global App Instance
let app = null;
window.addEventListener('DOMContentLoaded', () => {
  app = new AlgoTerminalApp();
});
