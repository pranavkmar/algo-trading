// Use DOM text nodes for headlines, symbols and upstream messages.
(() => {
  let busy = false;
  const form = document.getElementById('watchlistControls');
  const status = document.getElementById('wlStatus');
  const results = document.getElementById('wlResults');
  function group(title, rows, columns) {
    const heading = document.createElement('h3');
    heading.textContent = `${title} (${rows.length})`;
    results.append(heading);
    if (!rows.length) {
      const empty = document.createElement('p');
      empty.textContent = 'No matches available.';
      results.append(empty);
      return;
    }
    const wrap = document.createElement('div');
    wrap.style.overflowX = 'auto';
    const table = document.createElement('table');
    table.className = 'quant-table';
    const head = table.createTHead().insertRow();
    columns.forEach(([label]) => {
      const cell = document.createElement('th'); cell.textContent = label; head.append(cell);
    });
    const body = table.createTBody();
    rows.forEach(row => {
      const tr = body.insertRow();
      columns.forEach(([, key]) => {
        const cell = tr.insertCell();
        const value = row[key];
        cell.textContent = typeof value === 'number' ? value.toLocaleString('en-IN', {maximumFractionDigits: 2}) : value ?? '—';
        if (key === 'headline' && /^https?:\/\//.test(row.url)) {
          const link = document.createElement('a');
          link.href = row.url; link.target = '_blank'; link.rel = 'noopener noreferrer';
          link.textContent = value; cell.replaceChildren(link);
        }
      });
    });
    wrap.append(table); results.append(wrap);
  }
  async function refresh() {
    if (busy || !form.reportValidity()) return;
    busy = true;
    status.textContent = 'Refreshing watchlists…';
    try {
      const query = new URLSearchParams({min_delivery: document.getElementById('wlDelivery').value,
        volume_multiplier: document.getElementById('wlVolume').value, live: document.getElementById('wlLive').checked});
      const response = await fetch(`/api/watchlists?${query}`);
      if (!response.ok) throw new Error('Watchlist refresh failed');
      const data = await response.json();
      status.textContent = `Session: ${data.session_date} · Reference: ${data.reference_date ?? 'unavailable'} · Prices: ${data.quote_status} · Retrieved: ${data.quotes_retrieved_at ?? '—'}`;
      document.getElementById('wlWarnings').textContent = data.warnings.join(' · ');
      results.replaceChildren();
      group('Daily: Delivery + volume', data.daily.delivery_volume,
        [['Symbol','symbol'],['Delivery %','delivery_pct'],['Volume ×','volume_ratio'],['Reference session','reference_date']]);
      group('Daily: News / results', data.daily.news_results,
        [['Symbol','symbol'],['Category','category'],['Headline / source','headline'],['Published','published_at']]);
      const columns = [['Symbol','symbol'],['Last price','ltp'],['Previous high','previous_high'],['Previous low','previous_low']];
      group('Intraday: Above previous high', data.intraday.above_previous_high, columns);
      group('Intraday: Below previous low', data.intraday.below_previous_low, columns);
      group('Intraday: Within previous range', data.intraday.within_range, columns);
      if (data.intraday.unavailable.length) {
        const missing = document.createElement('p'); missing.textContent = `Prices unavailable: ${data.intraday.unavailable.join(', ')}`; results.append(missing);
      }
    } catch (error) {
      status.textContent = error.message;
      results.replaceChildren(); // Never leave old price groups looking current after a failure.
    } finally { busy = false; }
  }
  form.addEventListener('submit', event => {event.preventDefault(); refresh();});
  document.querySelector('[data-tab="watchlists"]').addEventListener('click', refresh);
  setInterval(() => {
    if (document.getElementById('tab-watchlists').classList.contains('active') && document.getElementById('wlLive').checked) refresh();
  }, 30000);
})();
