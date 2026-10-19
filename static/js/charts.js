/**
 * charts.js - High-Performance 60FPS Interactive Canvas Order Flow & CVD Engine
 * Features:
 * 1. Full X-Axis Time Scale with hours, minutes, dates, and grid lines.
 * 2. Interactive Mouse Wheel Zoom (centered on cursor).
 * 3. Interactive Click-and-Drag Pan (smooth horizontal scrolling through history).
 * 4. Dual-Axis Crosshair with Time Badge on bottom X-axis & Price Badge on right Y-axis.
 * 5. Aggressor Volume Split (Buy vs Sell volume), Delta Histogram, and Cumulative Volume Delta (CVD).
 * 6. Dynamic viewport resizing with high DPI / Retina scale support.
 */

class OrderflowCanvasChart {
  constructor(canvasId) {
    this.canvas = document.getElementById(canvasId);
    if (!this.canvas) return;
    this.ctx = this.canvas.getContext('2d');
    this.bars = [];
    this.symbol = 'KOTAKBANK';

    // Interactive Viewport State
    this.visibleBarsCount = 80; // Default visible candle count
    this.offsetRight = 0;       // Bars offset from the latest bar (0 = rightmost)
    this.minVisibleBars = 15;
    this.maxVisibleBars = 400;

    // Mouse & Pan State
    this.isDragging = false;
    this.dragStartX = 0;
    this.dragStartOffset = 0;
    this.hoverX = -1;
    this.hoverY = -1;
    this.hoverIndex = -1;

    this.setupListeners();
    this.resize();
  }

  resize() {
    if (!this.canvas) return;
    const rect = this.canvas.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    this.width = rect.width;
    this.height = rect.height;
    this.canvas.width = rect.width * dpr;
    this.canvas.height = rect.height * dpr;
    this.ctx.setTransform(1, 0, 0, 1, 0, 0); // Reset transform before scaling
    this.ctx.scale(dpr, dpr);
    this.render();
  }

  setupListeners() {
    window.addEventListener('resize', () => this.resize());

    // Mouse Move (Hover & Pan)
    this.canvas.addEventListener('mousemove', (e) => {
      const rect = this.canvas.getBoundingClientRect();
      const x = e.clientX - rect.left;
      const y = e.clientY - rect.top;
      this.hoverX = x;
      this.hoverY = y;

      if (this.isDragging) {
        const pad = { left: 50, right: 75 };
        const chartW = this.width - pad.left - pad.right;
        const barStep = chartW / this.visibleBarsCount;
        const deltaX = x - this.dragStartX;
        const deltaBars = Math.round(deltaX / barStep);
        const maxOffset = Math.max(0, this.bars.length - this.visibleBarsCount);
        this.offsetRight = Math.max(0, Math.min(maxOffset, this.dragStartOffset + deltaBars));
        this.render();
      } else {
        this.handleHover(x, y);
      }
    });

    // Mouse Down (Start Pan)
    this.canvas.addEventListener('mousedown', (e) => {
      this.isDragging = true;
      const rect = this.canvas.getBoundingClientRect();
      this.dragStartX = e.clientX - rect.left;
      this.dragStartOffset = this.offsetRight;
      this.canvas.style.cursor = 'grabbing';
    });

    // Mouse Up (End Pan)
    window.addEventListener('mouseup', () => {
      if (this.isDragging) {
        this.isDragging = false;
        if (this.canvas) this.canvas.style.cursor = 'crosshair';
      }
    });

    // Mouse Leave
    this.canvas.addEventListener('mouseleave', () => {
      this.hoverX = -1;
      this.hoverY = -1;
      this.hoverIndex = -1;
      this.render();
    });

    // Mouse Wheel (Zoom In / Zoom Out)
    this.canvas.addEventListener('wheel', (e) => {
      e.preventDefault();
      if (!this.bars.length) return;

      const zoomFactor = e.deltaY < 0 ? 0.85 : 1.15;
      const newVisible = Math.round(this.visibleBarsCount * zoomFactor);
      const clampedVisible = Math.max(this.minVisibleBars, Math.min(Math.min(this.maxVisibleBars, this.bars.length), newVisible));

      if (clampedVisible !== this.visibleBarsCount) {
        // Keep focus roughly centered
        const delta = clampedVisible - this.visibleBarsCount;
        this.visibleBarsCount = clampedVisible;
        const maxOffset = Math.max(0, this.bars.length - this.visibleBarsCount);
        this.offsetRight = Math.max(0, Math.min(maxOffset, this.offsetRight - Math.round(delta / 2)));
        this.render();
      }
    }, { passive: false });

    // Double Click to Reset View
    this.canvas.addEventListener('dblclick', () => {
      this.resetView();
    });
  }

  resetView() {
    this.offsetRight = 0;
    this.visibleBarsCount = Math.min(80, this.bars.length || 80);
    this.render();
  }

  zoomIn() {
    this.visibleBarsCount = Math.max(this.minVisibleBars, Math.round(this.visibleBarsCount * 0.8));
    this.render();
  }

  zoomOut() {
    this.visibleBarsCount = Math.min(Math.min(this.maxVisibleBars, this.bars.length), Math.round(this.visibleBarsCount * 1.25));
    this.render();
  }

  setData(symbol, bars) {
    this.symbol = symbol;
    this.bars = bars || [];
    this.offsetRight = 0;
    this.visibleBarsCount = Math.min(80, Math.max(this.minVisibleBars, this.bars.length || 80));
    this.render();
  }

  getVisibleSlice() {
    if (!this.bars || !this.bars.length) return { slice: [], startIndex: 0, endIndex: 0 };
    const total = this.bars.length;
    const count = Math.min(this.visibleBarsCount, total);
    const endIndex = Math.max(count, total - this.offsetRight);
    const startIndex = Math.max(0, endIndex - count);
    return {
      slice: this.bars.slice(startIndex, endIndex),
      startIndex,
      endIndex
    };
  }

  handleHover(mouseX, mouseY) {
    const { slice, startIndex } = this.getVisibleSlice();
    if (!slice.length) return;

    const pad = { left: 50, right: 75 };
    const chartW = this.width - pad.left - pad.right;
    const barStep = chartW / slice.length;

    if (mouseX >= pad.left && mouseX <= this.width - pad.right) {
      const relIdx = Math.floor((mouseX - pad.left) / barStep);
      if (relIdx >= 0 && relIdx < slice.length) {
        this.hoverIndex = startIndex + relIdx;
        this.render();
        return;
      }
    }

    if (this.hoverIndex !== -1) {
      this.hoverIndex = -1;
      this.render();
    }
  }

  render() {
    if (!this.ctx || !this.bars || !this.bars.length) {
      this.drawEmptyState();
      return;
    }

    const ctx = this.ctx;
    const w = this.width;
    const h = this.height;

    ctx.clearRect(0, 0, w, h);

    // Layout Partitioning:
    // Top pad: 32px (header/stats legend)
    // Bottom pad: 32px (dedicated X-Axis Time Scale)
    // Left pad: 50px
    // Right pad: 75px (Y-Axis price & delta scale)
    const pad = { top: 32, bottom: 32, left: 50, right: 75 };
    const chartH = h - pad.top - pad.bottom;
    const chartW = w - pad.left - pad.right;

    // Sub-pane heights
    const priceH = chartH * 0.58;
    const volH = chartH * 0.20;
    const deltaH = chartH * 0.22;

    const priceY = pad.top;
    const volY = priceY + priceH;
    const deltaY = volY + volH;
    const timeScaleY = h - pad.bottom;

    // Get visible bars
    const { slice, startIndex } = this.getVisibleSlice();
    if (!slice.length) return;

    // Extents across VISIBLE slice
    let minPrice = Infinity, maxPrice = -Infinity;
    let maxVol = 0, maxDelta = 0;
    let minCvd = Infinity, maxCvd = -Infinity;

    for (const b of slice) {
      minPrice = Math.min(minPrice, b.low);
      maxPrice = Math.max(maxPrice, b.high);
      maxVol = Math.max(maxVol, b.volume);
      maxDelta = Math.max(maxDelta, Math.abs(b.delta));
      minCvd = Math.min(minCvd, b.cvd);
      maxCvd = Math.max(maxCvd, b.cvd);
    }

    const pricePadding = (maxPrice - minPrice) * 0.06 || 1.0;
    minPrice -= pricePadding;
    maxPrice += pricePadding;
    if (maxVol === 0) maxVol = 1000;
    if (maxDelta === 0) maxDelta = 1000;

    const barStep = chartW / slice.length;
    const candleW = Math.max(2, Math.min(18, barStep * 0.72));

    // -------------------------------------------------------------
    // 1. HORIZONTAL PANE SEPARATORS & GRID
    // -------------------------------------------------------------
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.06)';
    ctx.lineWidth = 1;

    // Pane Divider Lines
    [volY, deltaY, timeScaleY].forEach(y => {
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();
    });

    // Price Horizontal Grid Lines
    for (let i = 0; i <= 4; i++) {
      const y = priceY + (priceH / 4) * i;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(w - pad.right, y);
      ctx.stroke();

      const pVal = maxPrice - ((maxPrice - minPrice) / 4) * i;
      ctx.fillStyle = '#64748b';
      ctx.font = '10px JetBrains Mono';
      ctx.textAlign = 'left';
      ctx.fillText(`₹${pVal.toFixed(2)}`, w - pad.right + 6, y + 3);
    }

    // Volume Axis Label
    ctx.fillText(`${(maxVol / 1000).toFixed(0)}k`, w - pad.right + 6, volY + 12);

    // Delta Axis Zero Line
    const deltaZeroY = deltaY + deltaH / 2;
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.12)';
    ctx.beginPath();
    ctx.moveTo(pad.left, deltaZeroY);
    ctx.lineTo(w - pad.right, deltaZeroY);
    ctx.stroke();
    ctx.fillText(`+${(maxDelta / 1000).toFixed(0)}k`, w - pad.right + 6, deltaY + 10);
    ctx.fillText(`-${(maxDelta / 1000).toFixed(0)}k`, w - pad.right + 6, deltaY + deltaH - 2);

    // -------------------------------------------------------------
    // 2. CANDLES, VOLUME SPLIT & DELTA BARS
    // -------------------------------------------------------------
    for (let i = 0; i < slice.length; i++) {
      const b = slice[i];
      const cx = pad.left + i * barStep + barStep / 2;
      const isGreen = b.close >= b.open;

      const yOpen = priceY + ((maxPrice - b.open) / (maxPrice - minPrice)) * priceH;
      const yClose = priceY + ((maxPrice - b.close) / (maxPrice - minPrice)) * priceH;
      const yHigh = priceY + ((maxPrice - b.high) / (maxPrice - minPrice)) * priceH;
      const yLow = priceY + ((maxPrice - b.low) / (maxPrice - minPrice)) * priceH;

      ctx.strokeStyle = isGreen ? '#00e676' : '#ff1744';
      ctx.fillStyle = isGreen ? '#00e676' : '#ff1744';

      // Candle Wick
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(cx, yHigh);
      ctx.lineTo(cx, yLow);
      ctx.stroke();

      // Candle Body
      const top = Math.min(yOpen, yClose);
      const bodyH = Math.max(2, Math.abs(yClose - yOpen));
      ctx.fillRect(cx - candleW / 2, top, candleW, bodyH);

      // Volume Split Bar (Vol Pane)
      const bVolH = (b.buy_volume / maxVol) * volH;
      const sVolH = (b.sell_volume / maxVol) * volH;
      const volBaseY = volY + volH;

      // Sell portion (bottom)
      ctx.fillStyle = 'rgba(255, 23, 68, 0.65)';
      ctx.fillRect(cx - candleW / 2, volBaseY - sVolH, candleW, sVolH);

      // Buy portion (stacked above)
      ctx.fillStyle = 'rgba(0, 230, 118, 0.65)';
      ctx.fillRect(cx - candleW / 2, volBaseY - sVolH - bVolH, candleW, bVolH);

      // Delta Histogram (Delta Pane)
      const dBarH = (Math.abs(b.delta) / maxDelta) * (deltaH / 2);
      if (b.delta >= 0) {
        ctx.fillStyle = '#00e676';
        ctx.fillRect(cx - candleW / 2, deltaZeroY - dBarH, candleW, dBarH);
      } else {
        ctx.fillStyle = '#ff1744';
        ctx.fillRect(cx - candleW / 2, deltaZeroY, candleW, dBarH);
      }
    }

    // -------------------------------------------------------------
    // 3. CVD (CUMULATIVE VOLUME DELTA) OVERLAY LINE
    // -------------------------------------------------------------
    if (maxCvd !== minCvd) {
      ctx.beginPath();
      ctx.strokeStyle = '#00f2fe';
      ctx.lineWidth = 1.5;
      for (let i = 0; i < slice.length; i++) {
        const b = slice[i];
        const cx = pad.left + i * barStep + barStep / 2;
        const cy = priceY + priceH - ((b.cvd - minCvd) / (maxCvd - minCvd)) * (priceH * 0.45);
        if (i === 0) ctx.moveTo(cx, cy);
        else ctx.lineTo(cx, cy);
      }
      ctx.stroke();
    }

    // -------------------------------------------------------------
    // 4. DEDICATED X-AXIS TIME SCALE (HOURS, MINUTES, DATES)
    // -------------------------------------------------------------
    const tickInterval = Math.max(6, Math.floor(slice.length / 8));
    ctx.textAlign = 'center';
    ctx.font = '10px JetBrains Mono';

    let lastRenderedDate = '';

    for (let i = 0; i < slice.length; i += tickInterval) {
      const b = slice[i];
      const cx = pad.left + i * barStep + barStep / 2;

      // Draw subtle vertical grid line across all panes
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.03)';
      ctx.beginPath();
      ctx.moveTo(cx, pad.top);
      ctx.lineTo(cx, timeScaleY);
      ctx.stroke();

      // Tick mark on time scale
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
      ctx.beginPath();
      ctx.moveTo(cx, timeScaleY);
      ctx.lineTo(cx, timeScaleY + 4);
      ctx.stroke();

      // Time label
      const parts = b.datetime.split(' ');
      const datePart = parts[0] || '';
      const timePart = parts[1] ? parts[1].substring(0, 5) : '';

      // Format date label if date changes
      if (datePart && datePart !== lastRenderedDate && i > 0) {
        lastRenderedDate = datePart;
        const dObj = new Date(datePart);
        const dayStr = !isNaN(dObj) ? dObj.toLocaleDateString('en-US', { day: 'numeric', month: 'short' }) : datePart;
        ctx.fillStyle = '#38bdf8';
        ctx.fillText(dayStr, cx, timeScaleY + 24);
      }

      ctx.fillStyle = '#94a3b8';
      ctx.fillText(timePart, cx, timeScaleY + 14);
    }

    // -------------------------------------------------------------
    // 5. PANE LABELS & HEADER STRIP
    // -------------------------------------------------------------
    ctx.fillStyle = '#64748b';
    ctx.font = '10px Inter';
    ctx.textAlign = 'left';
    ctx.fillText('Aggressor Split (Buy vs Sell)', pad.left + 8, volY + 12);
    ctx.fillText('Order Flow Delta (Net Lift vs Hit)', pad.left + 8, deltaY + 12);

    // Active Bar Stats Legend
    const activeBar = (this.hoverIndex >= 0 && this.hoverIndex < this.bars.length)
      ? this.bars[this.hoverIndex]
      : slice[slice.length - 1];

    if (activeBar) {
      const isUp = activeBar.close >= activeBar.open;
      const color = isUp ? '#00e676' : '#ff1744';

      // Header Legend Text
      ctx.font = '11px JetBrains Mono';
      let xPos = pad.left;

      ctx.fillStyle = '#fff';
      ctx.fillText(`${this.symbol} 1M`, xPos, pad.top - 12);
      xPos += ctx.measureText(`${this.symbol} 1M`).width + 12;

      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`O:`, xPos, pad.top - 12);
      xPos += 14;
      ctx.fillStyle = color;
      ctx.fillText(activeBar.open.toFixed(2), xPos, pad.top - 12);
      xPos += ctx.measureText(activeBar.open.toFixed(2)).width + 10;

      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`H:`, xPos, pad.top - 12);
      xPos += 14;
      ctx.fillStyle = color;
      ctx.fillText(activeBar.high.toFixed(2), xPos, pad.top - 12);
      xPos += ctx.measureText(activeBar.high.toFixed(2)).width + 10;

      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`L:`, xPos, pad.top - 12);
      xPos += 14;
      ctx.fillStyle = color;
      ctx.fillText(activeBar.low.toFixed(2), xPos, pad.top - 12);
      xPos += ctx.measureText(activeBar.low.toFixed(2)).width + 10;

      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`C:`, xPos, pad.top - 12);
      xPos += 14;
      ctx.fillStyle = color;
      ctx.fillText(activeBar.close.toFixed(2), xPos, pad.top - 12);
      xPos += ctx.measureText(activeBar.close.toFixed(2)).width + 14;

      ctx.fillStyle = '#94a3b8';
      ctx.fillText(`Vol:`, xPos, pad.top - 12);
      xPos += 28;
      ctx.fillStyle = '#e2e8f0';
      ctx.fillText(activeBar.volume.toLocaleString(), xPos, pad.top - 12);
      xPos += ctx.measureText(activeBar.volume.toLocaleString()).width + 14;

      ctx.fillStyle = '#00f2fe';
      ctx.fillText(`CVD:`, xPos, pad.top - 12);
      xPos += 28;
      ctx.fillText(`${activeBar.cvd >= 0 ? '+' : ''}${activeBar.cvd.toLocaleString()}`, xPos, pad.top - 12);
    }

    // -------------------------------------------------------------
    // 6. INTERACTIVE CROSSHAIR & DUAL AXIS BADGES
    // -------------------------------------------------------------
    if (this.hoverIndex >= 0 && this.hoverIndex < this.bars.length && this.hoverX >= pad.left && this.hoverX <= w - pad.right) {
      const relIdx = this.hoverIndex - startIndex;
      if (relIdx >= 0 && relIdx < slice.length) {
        const cx = pad.left + relIdx * barStep + barStep / 2;
        const b = slice[relIdx];

        // Vertical Crosshair Line
        ctx.strokeStyle = 'rgba(0, 242, 254, 0.4)';
        ctx.lineWidth = 1;
        ctx.setLineDash([3, 3]);
        ctx.beginPath();
        ctx.moveTo(cx, pad.top);
        ctx.lineTo(cx, timeScaleY);
        ctx.stroke();

        // Horizontal Crosshair Line
        if (this.hoverY >= pad.top && this.hoverY <= timeScaleY) {
          ctx.beginPath();
          ctx.moveTo(pad.left, this.hoverY);
          ctx.lineTo(w - pad.right, this.hoverY);
          ctx.stroke();

          // Y-Axis Price Badge (Right)
          const hoverPrice = maxPrice - ((this.hoverY - pad.top) / priceH) * (maxPrice - minPrice);
          const priceBadgeText = `₹${hoverPrice.toFixed(2)}`;
          ctx.fillStyle = '#00f2fe';
          ctx.fillRect(w - pad.right, this.hoverY - 10, pad.right - 2, 20);
          ctx.fillStyle = '#07090e';
          ctx.font = 'bold 10px JetBrains Mono';
          ctx.textAlign = 'left';
          ctx.fillText(priceBadgeText, w - pad.right + 6, this.hoverY + 4);
        }
        ctx.setLineDash([]);

        // X-Axis Time Badge (Bottom)
        const timeBadgeText = b.datetime;
        ctx.font = 'bold 10px JetBrains Mono';
        const tbw = ctx.measureText(timeBadgeText).width + 16;
        ctx.fillStyle = '#00f2fe';
        ctx.fillRect(Math.max(pad.left, cx - tbw / 2), timeScaleY, tbw, 20);
        ctx.fillStyle = '#07090e';
        ctx.textAlign = 'center';
        ctx.fillText(timeBadgeText, Math.max(pad.left + tbw / 2, cx), timeScaleY + 14);
      }
    }

    // -------------------------------------------------------------
    // 7. INTERACTIVE CONTROLS HUD (TOP RIGHT)
    // -------------------------------------------------------------
    ctx.textAlign = 'right';
    ctx.font = '10px Inter';
    ctx.fillStyle = '#64748b';
    ctx.fillText(`Scroll: Zoom | Drag: Pan | Dbl-Click: Reset`, w - pad.right - 10, pad.top - 12);
  }

  drawEmptyState() {
    const ctx = this.ctx;
    ctx.clearRect(0, 0, this.width, this.height);
    ctx.fillStyle = '#64748b';
    ctx.font = '13px Inter';
    ctx.textAlign = 'center';
    ctx.fillText(`No 1-minute orderflow bars loaded for ${this.symbol}. Run 'intraday_sync.py' to sync.`, this.width / 2, this.height / 2);
  }
}
